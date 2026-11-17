"""Adaptadores sem impressão para as implementações existentes.

As entradas são copiadas e validadas antes da medição. ``tempo_externo_s``
cobre a chamada da implementação, sem a cópia defensiva nem a normalização
do resultado. Não configura energia, não cria grades e não gera arquivos.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# Os módulos existentes usam imports locais, sem um pacote src instalado.
_SRC = Path(__file__).resolve().parents[1] / "src"
for _pasta in ("sequential", "parallel"):
    _caminho = str(_SRC / _pasta)
    if _caminho not in sys.path:
        sys.path.insert(0, _caminho)

import fake_news as sequencial  # noqa: E402
import fake_news_paralelo as paralelo  # noqa: E402

Contagem = tuple[int, int, int]


@dataclass
class ResultadoBenchmark:
    """Contagens na ordem (ignorantes, espalhadores, inativos).

    ``historico[0]`` corresponde à primeira geração calculada, sem incluir a
    grade inicial. ``tempo_total_s`` preserva o escopo interno da implementação:
    no sequencial é o laço; no paralelo inclui criação/encerramento dos workers,
    mas não todas as conversões da chamada pública. Para comparar chamadas
    completas, use ``tempo_externo_s``. Tempos são segundos de parede.
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

    @property
    def geracoes_executadas(self) -> int:
        return len(self.historico)


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
) -> tuple[list[list[int]], list[Contagem], float]:
    # Mesmo laço de varredura.rodar_professor, usando as regras originais.
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
) -> ResultadoBenchmark:
    """Executa regras originais até o limite ou a primeira geração sem espalhadores.

    Usa as funções originais em vez de ``executar_simulacao``, que cria outra
    entrada, imprime resultados e não retorna a matriz final.
    """
    grade = _copiar_grade(grade_inicial, geracoes)
    inicio = time.perf_counter()
    final, historico, tempo = _simular_sequencial(grade, geracoes, limiar_convencimento)
    externo = time.perf_counter() - inicio
    return ResultadoBenchmark(
        grade_final=final, historico=historico, tempo_externo_s=externo,
        tempo_geracoes_s=tempo, tempo_total_s=tempo,
        backend="sequencial", workers=1, kernel="professor",
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
) -> ResultadoBenchmark:
    """Chama ``simular_paralelo`` sem alterar seus critérios de parada.

    Aceita os backends threads/processos, kernels otimizado/referencia e
    divisões estatica/dinamica existentes. Em programas com processos, execute
    a chamada sob ``if __name__ == '__main__':`` (necessário com spawn).
    """
    grade = _copiar_grade(grade_inicial, geracoes)
    inicio = time.perf_counter()
    resultado = paralelo.simular_paralelo(
        grade, geracoes, limiar_convencimento=limiar_convencimento,
        workers=workers, backend=backend, kernel=kernel,
        divisao=divisao, pedaco=pedaco,
    )
    externo = time.perf_counter() - inicio
    return ResultadoBenchmark(
        grade_final=resultado.grade_final, historico=resultado.historico,
        tempo_externo_s=externo,
        tempo_geracoes_s=resultado.tempo_geracoes_s,
        tempo_total_s=resultado.tempo_total_s,
        backend=resultado.backend, workers=resultado.workers,
        kernel=resultado.kernel, divisao=resultado.divisao, pedaco=resultado.pedaco,
    )
