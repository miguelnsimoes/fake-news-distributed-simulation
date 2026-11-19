"""Núcleo comum às versões sequencial, paralela e distribuída.

Contrato de todas as versões: ``simular(config: Config) -> Resultado``.
"""

import hashlib
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from .estados import ESPALHADOR, IGNORANTE, INATIVO
from .kernels import KERNEL_PADRAO, KERNELS, Kernel, obter_kernel

__all__ = [
    "IGNORANTE", "ESPALHADOR", "INATIVO", "KERNELS", "KERNEL_PADRAO", "Grade",
    "Config", "Resultado", "criar_grade", "calcular_faixa", "proxima_geracao",
    "contar_estados", "somar_contagens", "registro_historico", "hash_grade",
    "dividir_linhas", "simular", "calcular_linhas", "contar_linhas", "evoluir",
]

# Formato interno: uma linha em bytes (1 byte por pessoa), o mesmo dos kernels.
Linhas = List[bytes]

Grade = List[List[int]]


@dataclass
class Config:
    linhas: int = 100
    colunas: int = 100
    geracoes: int = 50
    percentual_espalhadores: float = 0.05
    limiar_convencimento: int = 3
    semente: int = 42
    kernel: str = KERNEL_PADRAO
    # Ignorados pela versão sequencial.
    num_threads: int = 1
    num_processos: int = 1


@dataclass
class Resultado:
    versao: str
    config: Config
    # Um registro_historico por geração.
    historico: List[Dict[str, int]] = field(default_factory=list)
    geracoes_executadas: int = 0
    tempo_s: float = 0.0
    grade_final: Optional[Grade] = None
    hash_grade: str = ""

    def contagem_final(self) -> Dict[str, int]:
        return self.historico[-1] if self.historico else {}

    def para_dict(self, incluir_grade: bool = False) -> dict:
        d = {
            "versao": self.versao,
            "config": asdict(self.config),
            "geracoes_executadas": self.geracoes_executadas,
            "tempo_s": self.tempo_s,
            "hash_grade": self.hash_grade,
            "historico": self.historico,
        }
        if incluir_grade:
            d["grade_final"] = self.grade_final
        return d


def criar_grade(linhas: int, colunas: int,
                percentual_espalhadores: float = 0.02,
                semente: int = 42) -> Grade:
    """Mesma grade do código original, mas com gerador local em vez do global."""
    rng = random.Random(semente)
    grade = [[IGNORANTE] * colunas for _ in range(linhas)]

    total_espalhadores = int(linhas * colunas * percentual_espalhadores)
    for _ in range(total_espalhadores):
        i = rng.randint(0, linhas - 1)
        j = rng.randint(0, colunas - 1)
        grade[i][j] = ESPALHADOR

    return grade


def calcular_faixa(grade: Grade, linha_ini: int, linha_fim: int,
                   limiar_convencimento: int,
                   kernel: Union[str, Kernel] = KERNEL_PADRAO) -> Grade:
    """Próxima geração das linhas [linha_ini, linha_fim), sem alterar ``grade``.

    Linhas fora de ``grade`` são tratadas como borda da matriz, o que permite
    passar uma fatia com halo.
    """
    if linha_ini >= linha_fim:
        return []
    base = max(0, linha_ini - 1)
    janela = [bytes(linha) for linha in grade[base:linha_fim + 1]]
    novas = calcular_linhas(janela, linha_ini - base, linha_fim - base,
                            limiar_convencimento, kernel)
    return [list(linha) for linha in novas]


def calcular_linhas(linhas: Sequence[bytes], linha_ini: int, linha_fim: int,
                    limiar_convencimento: int,
                    kernel: Union[str, Kernel] = KERNEL_PADRAO) -> Linhas:
    """``calcular_faixa`` no formato interno, sem conversões."""
    calcular = obter_kernel(kernel)
    total = len(linhas)
    novas: Linhas = []
    if linha_ini >= linha_fim:
        return novas

    acima = linhas[linha_ini - 1] if linha_ini > 0 else None
    atual = linhas[linha_ini]
    for i in range(linha_ini, linha_fim):
        abaixo = linhas[i + 1] if i + 1 < total else None
        novas.append(calcular(acima, atual, abaixo, limiar_convencimento))
        acima, atual = atual, abaixo

    return novas


def proxima_geracao(grade: Grade, limiar_convencimento: int = 2,
                    kernel: Union[str, Kernel] = KERNEL_PADRAO) -> Grade:
    return calcular_faixa(grade, 0, len(grade), limiar_convencimento, kernel)


def contar_estados(grade: Grade) -> Dict[int, int]:
    contagem = {IGNORANTE: 0, ESPALHADOR: 0, INATIVO: 0}
    for linha in grade:
        for celula in linha:
            contagem[celula] += 1
    return contagem


def contar_linhas(linhas: Sequence[bytes]) -> Dict[int, int]:
    """``contar_estados`` no formato interno."""
    ignorantes = sum(linha.count(IGNORANTE) for linha in linhas)
    espalhadores = sum(linha.count(ESPALHADOR) for linha in linhas)
    total = sum(len(linha) for linha in linhas)
    return {IGNORANTE: ignorantes, ESPALHADOR: espalhadores,
            INATIVO: total - ignorantes - espalhadores}


def somar_contagens(contagens: List[Dict[int, int]]) -> Dict[int, int]:
    total = {IGNORANTE: 0, ESPALHADOR: 0, INATIVO: 0}
    for c in contagens:
        for estado in total:
            total[estado] += c[estado]
    return total


def registro_historico(geracao: int, contagem: Dict[int, int]) -> Dict[str, int]:
    return {
        "geracao": geracao,
        "ignorantes": contagem[IGNORANTE],
        "espalhadores": contagem[ESPALHADOR],
        "inativos": contagem[INATIVO],
    }


def hash_grade(grade: Grade) -> str:
    """SHA-256 da grade, para comparar o estado final entre versões."""
    h = hashlib.sha256()
    h.update(f"{len(grade)}x{len(grade[0])}".encode())
    for linha in grade:
        h.update(bytes(linha))
    return h.hexdigest()


def dividir_linhas(total_linhas: int, partes: int) -> List[range]:
    """Faixas contíguas cujos tamanhos diferem em no máximo 1 (podem ser vazias)."""
    base, resto = divmod(total_linhas, partes)
    faixas = []
    inicio = 0
    for k in range(partes):
        tamanho = base + (1 if k < resto else 0)
        faixas.append(range(inicio, inicio + tamanho))
        inicio += tamanho
    return faixas


def simular(config: Config,
            ao_final_de_geracao: Optional[Callable[[int, Grade, Dict[int, int]], None]] = None
            ) -> Resultado:
    """Simulação sequencial; o gancho entra no tempo medido (não use em benchmarks)."""
    grade = criar_grade(config.linhas, config.colunas,
                        config.percentual_espalhadores, config.semente)
    grade, historico, tempo = evoluir(grade, config.geracoes, config.limiar_convencimento,
                                      config.kernel, ao_final_de_geracao)
    return Resultado(
        versao="sequencial",
        config=config,
        historico=historico,
        geracoes_executadas=len(historico),
        tempo_s=tempo,
        grade_final=grade,
        hash_grade=hash_grade(grade),
    )


def evoluir(grade: Grade, geracoes: int, limiar_convencimento: int,
            kernel: Union[str, Kernel] = KERNEL_PADRAO,
            ao_final_de_geracao: Optional[Callable[[int, Grade, Dict[int, int]], None]] = None
            ) -> Tuple[Grade, List[Dict[str, int]], float]:
    """Laço de gerações a partir de uma grade pronta: (grade_final, historico, tempo_s).

    Para como o original: após ``geracoes`` ou na primeira geração sem espalhadores.
    """
    calcular = obter_kernel(kernel)
    linhas: Linhas = [bytes(linha) for linha in grade]
    historico: List[Dict[str, int]] = []

    inicio = time.perf_counter()

    for geracao in range(1, geracoes + 1):
        linhas = calcular_linhas(linhas, 0, len(linhas), limiar_convencimento, calcular)
        contagem = contar_linhas(linhas)
        historico.append(registro_historico(geracao, contagem))

        if ao_final_de_geracao is not None:
            ao_final_de_geracao(geracao, [list(linha) for linha in linhas], contagem)

        if contagem[ESPALHADOR] == 0:
            break

    tempo = time.perf_counter() - inicio
    return [list(linha) for linha in linhas], historico, tempo
