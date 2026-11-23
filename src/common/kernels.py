"""Regra de transição de uma linha, usada pelas três versões.

A linha ``i`` da próxima geração depende só das linhas ``i - 1``, ``i`` e
``i + 1`` (vizinhança de Moore). Cada linha é ``bytes`` com um estado por
byte; ``None`` em ``acima``/``abaixo`` é a borda da matriz.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Union

from .estados import ESPALHADOR, IGNORANTE, INATIVO

Kernel = Callable[[Optional[bytes], bytes, Optional[bytes], int], bytes]

_SO_ESPALHADORES = bytes.maketrans(
    bytes((IGNORANTE, ESPALHADOR, INATIVO)),
    bytes((0, 1, 0)),
)


def linha_referencia(
    acima: Optional[bytes], linha: bytes, abaixo: Optional[bytes], limiar: int
) -> bytes:
    """Célula a célula, como o código original."""
    colunas = len(linha)
    trio = (acima, linha, abaixo)
    nova = bytearray(colunas)

    for j in range(colunas):
        if linha[j] == IGNORANTE:
            vizinhos = 0
            for di in range(3):
                vizinha = trio[di]
                if vizinha is None:
                    continue
                for dj in (-1, 0, 1):
                    if di == 1 and dj == 0:
                        continue
                    nj = j + dj
                    if 0 <= nj < colunas and vizinha[nj] == ESPALHADOR:
                        vizinhos += 1
            nova[j] = ESPALHADOR if vizinhos >= limiar else IGNORANTE
        else:
            nova[j] = INATIVO

    return bytes(nova)


def linha_otimizada(
    acima: Optional[bytes], linha: bytes, abaixo: Optional[bytes], limiar: int
) -> bytes:
    """Soma os espalhadores por coluna e desliza uma janela de 3 colunas.

    A própria célula entra na janela, mas só é avaliada quando é ignorante
    (vale 0), então a soma é exatamente o número de vizinhos espalhadores.
    Os zeros nas pontas substituem o teste de limites.
    """
    vazia = bytes(len(linha))
    e_acima = vazia if acima is None else acima.translate(_SO_ESPALHADORES)
    e_meio = linha.translate(_SO_ESPALHADORES)
    e_abaixo = vazia if abaixo is None else abaixo.translate(_SO_ESPALHADORES)

    colunas_somadas = [0]
    colunas_somadas += [a + b + c for a, b, c in zip(e_acima, e_meio, e_abaixo)]
    colunas_somadas.append(0)

    return bytes(
        [
            INATIVO
            if estado != IGNORANTE
            else (ESPALHADOR if esquerda + centro + direita >= limiar else IGNORANTE)
            for estado, esquerda, centro, direita in zip(
                linha, colunas_somadas, colunas_somadas[1:], colunas_somadas[2:]
            )
        ]
    )


KERNELS: Dict[str, Kernel] = {
    "referencia": linha_referencia,
    "otimizado": linha_otimizada,
}

KERNEL_PADRAO = "referencia"


def obter_kernel(kernel: Union[str, Kernel]) -> Kernel:
    if callable(kernel):
        return kernel
    try:
        return KERNELS[kernel]
    except KeyError:
        raise ValueError(
            f"kernel deve ser um de {sorted(KERNELS)}, não {kernel!r}."
        ) from None
