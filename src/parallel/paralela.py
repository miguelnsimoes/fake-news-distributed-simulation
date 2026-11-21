"""``simular(config) -> Resultado`` da versão paralela (contrato de common/core.py).

``tempo_s`` mede só o laço de gerações; o custo de criar os workers está em
``simular_paralelo(...).tempo_total_s``.
"""

from __future__ import annotations

import sys
from typing import Optional
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
_PASTA_PARALELA = _SRC / "parallel"
for _pasta in (_SRC, _PASTA_PARALELA):
    if str(_pasta) not in sys.path:
        sys.path.insert(0, str(_pasta))

from common.core import (  # noqa: E402
    Config,
    Resultado,
    hash_grade,
    preparar_inicio,
)
from fake_news_paralelo import BACKENDS, simular_paralelo  # noqa: E402


def simular(
    config: Config,
    backend: str = "threads",
    kernel: Optional[str] = None,
    divisao: str = "estatica",
) -> Resultado:
    """Usa ``config.num_threads`` ou ``config.num_processos`` conforme o backend."""
    if backend not in BACKENDS:
        raise ValueError(f"backend deve ser um de {BACKENDS}, não {backend!r}.")
    workers = config.num_threads if backend == "threads" else config.num_processos

    grade, tipos, modelo = preparar_inicio(config)
    saida = simular_paralelo(
        grade,
        config.geracoes,
        limiar_convencimento=config.limiar_convencimento,
        workers=workers,
        backend=backend,
        kernel=kernel or config.kernel,
        divisao=divisao,
        modelo=modelo,
        tipos=tipos,
    )

    historico = [
        {"geracao": g, "ignorantes": ign, "espalhadores": esp, "inativos": ina}
        for g, (ign, esp, ina) in enumerate(saida.historico, start=1)
    ]
    return Resultado(
        versao=f"paralela-{backend}",
        config=config,
        historico=historico,
        geracoes_executadas=saida.geracoes_executadas,
        tempo_s=saida.tempo_geracoes_s,
        grade_final=saida.grade_final,
        hash_grade=hash_grade(saida.grade_final),
    )
