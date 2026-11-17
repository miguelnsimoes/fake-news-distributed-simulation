"""Interface padrão do grupo para a versão paralela: ``simular(config) -> Resultado``.

É uma camada fina sobre ``fake_news_paralelo.simular_paralelo``. Recebe o
mesmo ``Config`` e devolve o mesmo ``Resultado`` de ``src/common/core.py``,
para que os testes de equivalência (``tests/test_equivalence.py``) e quem for
comparar as três versões chamem a paralela do mesmo jeito que a sequencial e
a distribuída.

Workers: ``config.num_threads`` no backend ``threads`` e
``config.num_processos`` no backend ``processos``.

Tempo: ``Resultado.tempo_s`` é o mesmo escopo do ``simular`` sequencial do
núcleo, só o laço de gerações (``tempo_geracoes_s``). A criação e o
encerramento das threads/processos ficam de fora; para o custo completo,
use ``simular_paralelo`` diretamente e leia ``tempo_total_s``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
_PASTA_PARALELA = _SRC / "parallel"
# Rodando como script ou importado como ``parallel.paralela``, o núcleo
# (``common``) e os módulos irmãos (``fake_news_paralelo``) precisam estar no path.
for _pasta in (_SRC, _PASTA_PARALELA):
    if str(_pasta) not in sys.path:
        sys.path.insert(0, str(_pasta))

from common.core import (  # noqa: E402
    Config,
    Resultado,
    criar_grade,
    hash_grade,
)
from fake_news_paralelo import BACKENDS, simular_paralelo  # noqa: E402


def simular(
    config: Config,
    backend: str = "threads",
    kernel: str = "otimizado",
    divisao: str = "estatica",
) -> Resultado:
    """Executa a simulação paralela com a mesma entrada e saída das outras versões.

    A grade inicial vem de ``core.criar_grade`` com a mesma semente, então o
    ponto de partida é idêntico ao da sequencial. A parada também é a mesma:
    ``config.geracoes`` gerações ou a primeira geração sem espalhadores.
    """
    if backend not in BACKENDS:
        raise ValueError(f"backend deve ser um de {BACKENDS}, não {backend!r}.")
    workers = config.num_threads if backend == "threads" else config.num_processos

    grade = criar_grade(config.linhas, config.colunas,
                        config.percentual_espalhadores, config.semente)
    saida = simular_paralelo(
        grade,
        config.geracoes,
        limiar_convencimento=config.limiar_convencimento,
        workers=workers,
        backend=backend,
        kernel=kernel,
        divisao=divisao,
    )

    # simular_paralelo devolve tuplas (ignorantes, espalhadores, inativos);
    # o contrato do grupo usa um dict por geração, numerado a partir de 1.
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
