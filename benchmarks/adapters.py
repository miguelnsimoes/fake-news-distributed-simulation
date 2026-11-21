"""Adaptadores sem impressão para medir as implementações.

``tempo_externo_s`` cobre só a chamada da implementação, sem a cópia defensiva
da entrada nem a normalização do resultado. ``modelo`` e ``tipos`` (de
``core.preparar_inicio``) ligam as extensões do modelo nas três versões.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

_SRC = Path(__file__).resolve().parents[1] / "src"
for _caminho in (str(_SRC / "sequential"), str(_SRC / "parallel"), str(_SRC)):
    if _caminho not in sys.path:
        sys.path.insert(0, _caminho)

import fake_news as sequencial  # noqa: E402  (código original do professor)
import fake_news_paralelo as paralelo  # noqa: E402
from common import core  # noqa: E402
from common.kernels import KERNELS  # noqa: E402
from common.modelo import Modelo  # noqa: E402
from distributed import server as distribuido  # noqa: E402

# "professor" é o código original (com deepcopy).
KERNELS_SEQUENCIAIS = ("professor",) + tuple(sorted(KERNELS))

Contagem = tuple[int, int, int]
Tipos = Optional[Sequence[Sequence[int]]]


@dataclass
class ResultadoBenchmark:
    """Contagens na ordem (ignorantes, espalhadores, inativos).

    ``tempo_total_s`` segue o escopo de cada implementação (na paralela e na
    distribuída inclui iniciar e encerrar os workers). ``overhead_s`` é o tempo
    fora do cálculo do worker mais lento: sincronização ou comunicação.
    """

    grade_final: list[list[int]]
    historico: list[Contagem]
    tempo_externo_s: float
    tempo_geracoes_s: float
    tempo_total_s: float
    backend: str
    workers: int
    kernel: str
    divisao: str | None = None
    pedaco: int | None = None
    caminho_critico_s: float | None = None
    celulas_halo: int | None = None

    @property
    def geracoes_executadas(self) -> int:
        return len(self.historico)

    @property
    def overhead_s(self) -> float | None:
        if self.caminho_critico_s is None:
            return None
        return max(0.0, self.tempo_geracoes_s - self.caminho_critico_s)


def _copiar_grade(
    grade_inicial: Sequence[Sequence[int]], geracoes: int,
) -> list[list[int]]:
    if geracoes < 0:
        raise ValueError("O número de gerações não pode ser negativo.")
    grade = [list(linha) for linha in grade_inicial]
    if not grade or not grade[0]:
        raise ValueError("A grade precisa ter pelo menos 1 linha e 1 coluna.")
    if any(len(linha) != len(grade[0]) for linha in grade):
        raise ValueError("Todas as linhas da grade precisam ter o mesmo tamanho.")
    if any(celula not in (0, 1, 2) for linha in grade for celula in linha):
        raise ValueError("Os estados da grade devem ser 0, 1 ou 2.")
    return grade


def _simular_sequencial(
    grade: list[list[int]], geracoes: int, limiar_convencimento: int,
    kernel: str = "professor", modelo: Modelo | None = None, tipos: Tipos = None,
) -> tuple[list[list[int]], list[Contagem], float]:
    if kernel != "professor":
        final, registros, tempo = core.evoluir(grade, geracoes, limiar_convencimento, kernel,
                                               modelo=modelo, tipos=tipos)
        historico = [(r["ignorantes"], r["espalhadores"], r["inativos"]) for r in registros]
        return final, historico, tempo
    inicio = time.perf_counter()
    historico: list[Contagem] = []
    for _ in range(geracoes):
        grade = sequencial.proxima_geracao(grade, limiar_convencimento)
        contagem = sequencial.contar_estados(grade)
        historico.append((
            contagem[sequencial.IGNORANTE],
            contagem[sequencial.ESPALHADOR],
            contagem[sequencial.INATIVO],
        ))
        if contagem[sequencial.ESPALHADOR] == 0:
            break
    return grade, historico, time.perf_counter() - inicio


def executar_sequencial(
    grade_inicial: Sequence[Sequence[int]],
    geracoes: int,
    limiar_convencimento: int = 2,
    *,
    kernel: str = "professor",
    modelo: Modelo | None = None,
    tipos: Tipos = None,
) -> ResultadoBenchmark:
    """``"professor"`` usa o código original, que não tem as extensões."""
    if kernel not in KERNELS_SEQUENCIAIS:
        raise ValueError(f"kernel deve ser um de {KERNELS_SEQUENCIAIS}, não {kernel!r}.")
    if kernel == "professor" and (modelo is not None or tipos is not None):
        raise ValueError("O código original não suporta as extensões do modelo.")
    grade = _copiar_grade(grade_inicial, geracoes)
    inicio = time.perf_counter()
    final, historico, tempo = _simular_sequencial(grade, geracoes, limiar_convencimento, kernel,
                                                  modelo, tipos)
    externo = time.perf_counter() - inicio
    return ResultadoBenchmark(
        grade_final=final, historico=historico, tempo_externo_s=externo,
        tempo_geracoes_s=tempo, tempo_total_s=tempo,
        backend="sequencial", workers=1, kernel=kernel, caminho_critico_s=tempo,
    )


def executar_paralelo(
    grade_inicial: Sequence[Sequence[int]],
    geracoes: int,
    limiar_convencimento: int = 2,
    *,
    workers: int = 4,
    backend: str = "threads",
    kernel: str = "otimizado",
    divisao: str = "estatica",
    pedaco: int | None = None,
    modelo: Modelo | None = None,
    tipos: Tipos = None,
) -> ResultadoBenchmark:
    """Com o backend de processos, chame sob ``if __name__ == "__main__":`` (spawn)."""
    grade = _copiar_grade(grade_inicial, geracoes)
    inicio = time.perf_counter()
    resultado = paralelo.simular_paralelo(
        grade, geracoes, limiar_convencimento=limiar_convencimento,
        workers=workers, backend=backend, kernel=kernel,
        divisao=divisao, pedaco=pedaco, modelo=modelo, tipos=tipos,
    )
    externo = time.perf_counter() - inicio
    return ResultadoBenchmark(
        grade_final=resultado.grade_final, historico=resultado.historico,
        tempo_externo_s=externo,
        tempo_geracoes_s=resultado.tempo_geracoes_s,
        tempo_total_s=resultado.tempo_total_s,
        backend=resultado.backend, workers=resultado.workers,
        kernel=resultado.kernel, divisao=resultado.divisao, pedaco=resultado.pedaco,
        caminho_critico_s=resultado.tempo_caminho_critico_s,
    )


def executar_distribuido(
    grade_inicial: Sequence[Sequence[int]],
    geracoes: int,
    limiar_convencimento: int = 2,
    *,
    workers: int = 2,
    kernel: str = "otimizado",
    tempo_limite: float = distribuido.TEMPO_LIMITE,
    modelo: Modelo | None = None,
    tipos: Tipos = None,
) -> ResultadoBenchmark:
    """Workers locais via TCP iniciados pelo coordenador (modo automático)."""
    grade = _copiar_grade(grade_inicial, geracoes)
    config = core.Config(
        linhas=len(grade), colunas=len(grade[0]), geracoes=geracoes,
        limiar_convencimento=limiar_convencimento, num_processos=workers, kernel=kernel,
    )
    inicio = time.perf_counter()
    resultado = distribuido.executar_servidor(
        config, porta=0, automaticos=True, tempo_limite=tempo_limite, grade_inicial=grade,
        tipos=tipos, modelo=modelo,
    )
    externo = time.perf_counter() - inicio
    metricas = resultado.metricas
    return ResultadoBenchmark(
        grade_final=resultado.grade_final,
        historico=[(h["ignorantes"], h["espalhadores"], h["inativos"])
                   for h in resultado.historico],
        tempo_externo_s=externo,
        tempo_geracoes_s=resultado.tempo_s,
        # Com zero gerações não há workers e total_s fica 0.
        tempo_total_s=metricas["total_s"] or resultado.tempo_s,
        backend="distribuida", workers=workers, kernel=kernel,
        caminho_critico_s=metricas["caminho_critico_calculo_s"],
        celulas_halo=metricas["celulas_halo_enviadas"],
    )
