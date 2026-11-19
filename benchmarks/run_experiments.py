"""Executa cenários reproduzíveis das três versões; --piloto usa padrões pequenos.

Da raiz: py benchmarks/run_experiments.py --piloto
Exemplo: py benchmarks/run_experiments.py --linhas 500 1000 --colunas 500 1000
         --geracoes 30 --espalhadores 0.01 0.02 0.05 --limiar 2 --workers 1 2 4 8

Tamanhos, gerações, espalhadores e limiares formam um produto cartesiano.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import multiprocessing
import os
import platform
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

if __package__:
    from . import adapters
else:
    import adapters


CAMPOS = [
    "experimento", "cenario", "fase", "repeticao", "backend", "workers",
    "kernel", "divisao", "linhas", "colunas", "geracoes_pedidas",
    "espalhadores", "limiar", "semente", "geracoes_executadas",
    "tempo_externo_s", "tempo_geracoes_s", "tempo_total_s",
    "caminho_critico_s", "overhead_s", "celulas_halo",
    "matriz_identica", "historico_identico", "status", "erro",
]
BACKENDS = ("threads", "processos", "distribuida")
KERNELS = tuple(k for k in adapters.KERNELS_SEQUENCIAIS if k != "professor")


def argumentos(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--piloto", action="store_true", help="Padrões: 12x12, 4 gerações, workers 1 e 2, 2 repetições.")
    parser.add_argument("--linhas", type=int, nargs="+")
    parser.add_argument("--colunas", type=int, nargs="+")
    parser.add_argument("--geracoes", type=int, nargs="+")
    parser.add_argument("--espalhadores", type=float, nargs="+", default=[0.02],
                        help="Frações de 0 a 1; 0.02 = 2%%.")
    parser.add_argument("--limiar", type=int, nargs="+", default=[2])
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--workers", type=int, nargs="+")
    parser.add_argument("--backends", nargs="+", choices=BACKENDS, default=list(BACKENDS),
                        help="Versões medidas além do sequencial (padrão: todas).")
    parser.add_argument("--kernel", choices=KERNELS, default="otimizado",
                        help="Kernel comum (common/kernels.py) usado por TODAS as versões medidas.")
    parser.add_argument("--repeticoes", type=int)
    parser.add_argument("--saida", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args(argv)
    args.linhas = args.linhas if args.linhas is not None else ([12] if args.piloto else [100])
    args.colunas = args.colunas if args.colunas is not None else ([12] if args.piloto else [100])
    args.geracoes = args.geracoes if args.geracoes is not None else ([4] if args.piloto else [30])
    args.workers = args.workers if args.workers is not None else ([1, 2] if args.piloto else [1, 2, 4])
    args.repeticoes = args.repeticoes if args.repeticoes is not None else (2 if args.piloto else 5)
    if any(n < 1 for n in args.linhas + args.colunas + args.workers):
        parser.error("Linhas, colunas e workers devem ser positivos.")
    if any(n < 0 for n in args.geracoes) or args.repeticoes < 1:
        parser.error("Gerações devem ser não negativas e repetições positivas.")
    if (any(not 0 <= p <= 1 for p in args.espalhadores)
            or any(not 0 <= t <= 8 for t in args.limiar)):
        parser.error("Espalhadores devem estar entre 0 e 1; limiar entre 0 e 8.")
    return args


def _executar(grade, geracoes, limiar, backend, workers, kernel):
    if backend == "sequencial":
        return adapters.executar_sequencial(grade, geracoes, limiar, kernel=kernel)
    if backend == "distribuida":
        return adapters.executar_distribuido(
            grade, geracoes, limiar, workers=workers, kernel=kernel,
        )
    return adapters.executar_paralelo(
        grade, geracoes, limiar, workers=workers, backend=backend,
        kernel=kernel, divisao="estatica",
    )


def _opcional(valor):
    """Campos que não existem em todas as versões ficam vazios no CSV."""
    return "" if valor is None else valor


def executar_experimento(args):
    """Grava aquecimento e medições em CSVs separados; retorna (diretório, sucesso).

    O primeiro sequencial do aquecimento é a referência de correção de todo o cenário.
    """
    identificador = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid4().hex[:8]
    pasta = args.saida / identificador
    pasta.mkdir(parents=True, exist_ok=False)
    metadata = {
        "experimento": identificador, "inicio_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "executavel": sys.executable,
        "plataforma": platform.platform(), "cpus_logicas": os.cpu_count(),
        "gil_ativo": adapters.paralelo.gil_ativo(),
        "configuracao": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "kernel": args.kernel, "divisao_paralela": "estatica",
        "distribuida": "processos locais via TCP (127.0.0.1), workers iniciados pelo coordenador",
        "overhead_s": "tempo_geracoes_s - caminho_critico_s (sincronização/comunicação)",
        "escopo_tempo_externo": "Chamada do adaptado, sem cópia defensiva, validação, CSV ou impressão.",
        "energia": "Executor não altera a política de energia; processos filhos seguem a implementação original.",
        "ordem": "Aquecimento sequencial primeiro; medições embaralhadas por repetição com semente fixa.",
    }
    (pasta / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    # (backend, workers, kernel); o primeiro é a referência de correção.
    configuracoes = [("sequencial", 1, "professor"), ("sequencial", 1, args.kernel)] + [
        (backend, n, args.kernel)
        for backend in dict.fromkeys(args.backends) for n in sorted(set(args.workers))
    ]
    sucesso = True
    # Arquivos distintos impedem agregar aquecimento como medição por engano.
    with (pasta / "raw.csv").open("w", newline="", encoding="utf-8") as raw, \
         (pasta / "warmup.csv").open("w", newline="", encoding="utf-8") as warmup:
        escritores = {"medicao": csv.DictWriter(raw, fieldnames=CAMPOS),
                      "aquecimento": csv.DictWriter(warmup, fieldnames=CAMPOS)}
        for escritor in escritores.values():
            escritor.writeheader()
        cenarios = itertools.product(
            dict.fromkeys(args.linhas), dict.fromkeys(args.colunas), dict.fromkeys(args.geracoes),
            dict.fromkeys(args.espalhadores), dict.fromkeys(args.limiar),
        )
        for cenario, (linhas, colunas, geracoes, espalhadores, limiar) in enumerate(cenarios, 1):
            grade = adapters.sequencial.criar_grade(linhas, colunas, espalhadores, args.semente)
            referencia = None
            for fase, repeticoes in (("aquecimento", 1), ("medicao", args.repeticoes)):
                for repeticao in range(1, repeticoes + 1):
                    ordem = list(configuracoes)
                    if fase == "medicao":
                        random.Random(args.semente + repeticao).shuffle(ordem)
                    for backend, workers, kernel in ordem:
                        registro = dict.fromkeys(CAMPOS, "")
                        registro.update(
                            experimento=identificador, cenario=cenario, fase=fase,
                            repeticao=repeticao, backend=backend, workers=workers,
                            kernel=kernel,
                            divisao="estatica" if backend in ("threads", "processos") else "",
                            linhas=linhas, colunas=colunas, geracoes_pedidas=geracoes,
                            espalhadores=espalhadores, limiar=limiar, semente=args.semente,
                        )
                        try:
                            resultado = _executar(grade, geracoes, limiar, backend, workers, kernel)
                            if referencia is None:
                                referencia = resultado
                            matriz = resultado.grade_final == referencia.grade_final
                            historico = resultado.historico == referencia.historico
                            registro.update(
                                geracoes_executadas=resultado.geracoes_executadas,
                                tempo_externo_s=resultado.tempo_externo_s,
                                tempo_geracoes_s=resultado.tempo_geracoes_s,
                                tempo_total_s=resultado.tempo_total_s,
                                caminho_critico_s=_opcional(resultado.caminho_critico_s),
                                overhead_s=_opcional(resultado.overhead_s),
                                celulas_halo=_opcional(resultado.celulas_halo),
                                matriz_identica=matriz, historico_identico=historico,
                                status="ok" if matriz and historico else "divergente",
                            )
                        except Exception as erro:
                            registro.update(status="erro", erro=f"{type(erro).__name__}: {erro}")
                        escritores[fase].writerow(registro)
                        (raw if fase == "medicao" else warmup).flush()
                        if registro["status"] != "ok":
                            sucesso = False
                        if referencia is None:
                            break
                    if referencia is None:
                        break
                if referencia is None:
                    break
            print(f"Cenário {cenario}: {linhas}x{colunas}, até {geracoes} gerações, "
                  f"{espalhadores:.0%} espalhadores, limiar {limiar} concluído.")
    return pasta, sucesso


def main(argv=None):
    args = argumentos(argv)
    pasta, sucesso = executar_experimento(args)
    print(f"Resultados: {pasta}")
    print("Validação: " + ("todas as execuções equivalentes" if sucesso else "há falhas; consulte os CSVs"))
    return 0 if sucesso else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
