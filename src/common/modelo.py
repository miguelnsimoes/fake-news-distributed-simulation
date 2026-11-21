"""Extensões do modelo: probabilidade de convencimento, influenciadores e bots.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from .estados import ESPALHADOR, IGNORANTE, INATIVO
from .kernels import Kernel, linha_otimizada, linha_referencia

COMUM = 0
INFLUENCIADOR = 1
BOT = 2

PESO_INFLUENCIADOR_PADRAO = 3

Trio = Tuple[Optional[bytes], bytes, Optional[bytes]]

_MASCARA_64 = (1 << 64) - 1
_SO_ESPALHADORES = bytes.maketrans(
    bytes((IGNORANTE, ESPALHADOR, INATIVO)),
    bytes((0, 1, 0)),
)


@dataclass(frozen=True)
class Modelo:
    probabilidade: float = 1.0
    peso_influenciador: int = 1
    semente: int = 42

    def __post_init__(self) -> None:
        if not isinstance(self.probabilidade, (int, float)) or not 0 < self.probabilidade <= 1:
            raise ValueError("A probabilidade de convencimento deve estar em (0, 1].")
        if type(self.peso_influenciador) is not int or self.peso_influenciador < 1:
            raise ValueError("O peso do influenciador deve ser um inteiro >= 1.")
        if type(self.semente) is not int:
            raise ValueError("A semente deve ser um inteiro.")


# (acima, linha, abaixo, limiar, tipos, modelo, geracao, i) -> nova linha
KernelEstendido = Callable[
    [Optional[bytes], bytes, Optional[bytes], int, Optional[Trio], Modelo, int, int], bytes
]


def validar_parametros(probabilidade: float, percentual_influenciadores: float,
                       peso_influenciador: int, percentual_bots: float) -> None:
    Modelo(probabilidade, peso_influenciador)
    for nome, valor in (("influenciadores", percentual_influenciadores),
                        ("bots", percentual_bots)):
        if not isinstance(valor, (int, float)) or not 0 <= valor <= 1:
            raise ValueError(f"O percentual de {nome} deve estar entre 0 e 1.")


def criar_modelo(probabilidade: float, percentual_influenciadores: float,
                 peso_influenciador: int, percentual_bots: float,
                 semente: int) -> Optional[Modelo]:
    """``None`` quando nenhuma extensão está ligada: vale o modelo original."""
    validar_parametros(probabilidade, percentual_influenciadores, peso_influenciador,
                       percentual_bots)
    if probabilidade == 1 and percentual_influenciadores == 0 and percentual_bots == 0:
        return None
    peso = peso_influenciador if percentual_influenciadores > 0 else 1
    return Modelo(float(probabilidade), peso, semente)


def criar_tipos(linhas: int, colunas: int, percentual_influenciadores: float,
                percentual_bots: float, semente: int) -> Optional[List[List[int]]]:
    """Mapa fixo do tipo de cada pessoa; ``None`` se não houver influenciadores nem bots.

    Usa um gerador próprio para não alterar a sequência de ``criar_grade``.
    Sorteios repetidos caem na mesma célula; bots são sorteados por último.
    """
    if percentual_influenciadores == 0 and percentual_bots == 0:
        return None
    rng = random.Random(f"tipos:{semente}")
    tipos = [[COMUM] * colunas for _ in range(linhas)]
    for tipo, percentual in ((INFLUENCIADOR, percentual_influenciadores), (BOT, percentual_bots)):
        for _ in range(int(linhas * colunas * percentual)):
            tipos[rng.randrange(linhas)][rng.randrange(colunas)] = tipo
    return tipos


def aplicar_bots(grade: List[List[int]], tipos: Optional[Sequence[Sequence[int]]]) -> None:
    """Bots começam espalhando (altera ``grade``)."""
    if tipos is None:
        return
    for linha, tipos_linha in zip(grade, tipos):
        for j, tipo in enumerate(tipos_linha):
            if tipo == BOT:
                linha[j] = ESPALHADOR


def sorteio(semente: int, geracao: int, i: int, j: int) -> float:
    """Número em [0, 1) que depende só de (semente, geração, linha, coluna).

    Por não depender da ordem de cálculo, a mesma célula recebe o mesmo
    número em qualquer divisão da matriz entre threads, processos ou máquinas.
    """
    x = (semente * 0x9E3779B97F4A7C15 + geracao * 0xBF58476D1CE4E5B9
         + i * 0x94D049BB133111EB + j * 0xD6E8FEB86659FD93) & _MASCARA_64
    # Finalizador do SplitMix64 (Steele et al., 2014).
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _MASCARA_64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _MASCARA_64
    x ^= x >> 31
    return (x >> 11) * (1.0 / (1 << 53))


def _convence(exposicao: int, limiar: int, modelo: Modelo, geracao: int, i: int, j: int) -> bool:
    if exposicao < limiar:
        return False
    if modelo.probabilidade == 1:
        return True
    chance = 1 - (1 - modelo.probabilidade) ** exposicao
    return sorteio(modelo.semente, geracao, i, j) < chance


def linha_estendida_referencia(
    acima: Optional[bytes], linha: bytes, abaixo: Optional[bytes], limiar: int,
    tipos: Optional[Trio], modelo: Modelo, geracao: int, i: int,
) -> bytes:
    """Especificação célula a célula das extensões."""
    colunas = len(linha)
    trio = (acima, linha, abaixo)
    nova = bytearray(colunas)

    for j in range(colunas):
        if tipos is not None and tipos[1][j] == BOT:
            nova[j] = ESPALHADOR
        elif linha[j] != IGNORANTE:
            nova[j] = INATIVO
        else:
            exposicao = 0
            for di in range(3):
                vizinha = trio[di]
                if vizinha is None:
                    continue
                for dj in (-1, 0, 1):
                    nj = j + dj
                    if (di == 1 and dj == 0) or not 0 <= nj < colunas:
                        continue
                    if vizinha[nj] == ESPALHADOR:
                        influente = tipos is not None and tipos[di][nj] == INFLUENCIADOR
                        exposicao += modelo.peso_influenciador if influente else 1
            nova[j] = ESPALHADOR if _convence(exposicao, limiar, modelo, geracao, i, j) else IGNORANTE

    return bytes(nova)


def _exposicao_por_coluna(linha: Optional[bytes], tipos_linha: Optional[bytes],
                          peso: int, colunas: int) -> Sequence[int]:
    if linha is None:
        return bytes(colunas)
    espalhadores = linha.translate(_SO_ESPALHADORES)
    if tipos_linha is None or peso == 1 or INFLUENCIADOR not in tipos_linha:
        return espalhadores
    return [e * (peso if t == INFLUENCIADOR else 1) for e, t in zip(espalhadores, tipos_linha)]


def linha_estendida_otimizada(
    acima: Optional[bytes], linha: bytes, abaixo: Optional[bytes], limiar: int,
    tipos: Optional[Trio], modelo: Modelo, geracao: int, i: int,
) -> bytes:
    """Mesma regra de ``linha_estendida_referencia`` com a janela de 3 colunas.

    O sorteio só é feito para quem passou do limiar, e os bots são ajustados
    no fim, procurando-os com ``bytes.find``.
    """
    colunas = len(linha)
    t_acima, t_meio, t_abaixo = tipos if tipos is not None else (None, None, None)
    peso = modelo.peso_influenciador
    somas = [0]
    somas += [a + b + c for a, b, c in zip(
        _exposicao_por_coluna(acima, t_acima, peso, colunas),
        _exposicao_por_coluna(linha, t_meio, peso, colunas),
        _exposicao_por_coluna(abaixo, t_abaixo, peso, colunas),
    )]
    somas.append(0)

    nova = bytearray(
        INATIVO
        if estado != IGNORANTE
        else (ESPALHADOR if esquerda + centro + direita >= limiar else IGNORANTE)
        for estado, esquerda, centro, direita in zip(linha, somas, somas[1:], somas[2:])
    )

    if modelo.probabilidade < 1:
        j = nova.find(ESPALHADOR)
        while j != -1:
            if linha[j] == IGNORANTE:
                exposicao = somas[j] + somas[j + 1] + somas[j + 2]
                if not _convence(exposicao, limiar, modelo, geracao, i, j):
                    nova[j] = IGNORANTE
            j = nova.find(ESPALHADOR, j + 1)

    if t_meio is not None:
        j = t_meio.find(BOT)
        while j != -1:
            nova[j] = ESPALHADOR
            j = t_meio.find(BOT, j + 1)

    return bytes(nova)


KERNELS_ESTENDIDOS: Dict[str, KernelEstendido] = {
    "referencia": linha_estendida_referencia,
    "otimizado": linha_estendida_otimizada,
}
_ESTENDIDO_POR_KERNEL = {
    linha_referencia: linha_estendida_referencia,
    linha_otimizada: linha_estendida_otimizada,
}


def obter_kernel_estendido(kernel: Union[str, Kernel, KernelEstendido]) -> KernelEstendido:
    """Versão com extensões do kernel pedido (por nome ou pela função base)."""
    if callable(kernel):
        if kernel in KERNELS_ESTENDIDOS.values():
            return kernel
        if kernel in _ESTENDIDO_POR_KERNEL:
            return _ESTENDIDO_POR_KERNEL[kernel]
        raise ValueError("Kernel personalizado não suporta as extensões do modelo.")
    try:
        return KERNELS_ESTENDIDOS[kernel]
    except KeyError:
        raise ValueError(
            f"kernel deve ser um de {sorted(KERNELS_ESTENDIDOS)}, não {kernel!r}."
        ) from None
