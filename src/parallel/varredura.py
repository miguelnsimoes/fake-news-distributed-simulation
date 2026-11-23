"""Mede a versão paralela variando o número de workers (threads/processos).

Exemplo (da raiz do repositório):
    python src/parallel/varredura.py --linhas 1000 --colunas 1000 \
        --geracoes 30 --limiar 2 --espalhadores 0.02 \
        --backend threads processos --divisao estatica dinamica \
        --workers 1 2 4 6 8 12 16 --repeticoes 3 --sequencial \
        --csv benchmarks/results/paralelo.csv

Com --sequencial também roda o código original, confere a equivalência e
mostra o ganho em relação a ele. Use limiar 2: com 3, a propagação morre em
poucas gerações.
"""

from __future__ import annotations

import argparse
import csv
import os
import platform
import random
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import fake_news_paralelo as paralelo  # coloca src e src/sequential no sys.path
from common.energia import desligar_economia_de_energia
from common.kernels import KERNELS
from fake_news import (
    ESPALHADOR,
    IGNORANTE,
    INATIVO,
    contar_estados,
    criar_grade,
    proxima_geracao,
)

CAMPOS_CSV = [
    "data", "python", "gil", "cpus", "backend", "kernel", "divisao", "pedaco",
    "linhas", "colunas", "geracoes_pedidas", "geracoes_executadas", "espalhadores",
    "limiar", "semente", "workers", "repeticao", "tempo_geracoes_s", "tempo_total_s",
    "caminho_critico_s", "calculo_medio_s", "desbalanceamento", "sincronizacao_s",
    "identico",
]


def rodar_professor(grade, geracoes, limiar):
    """Laço de ``executar_simulacao`` do original, sem os prints."""
    comeco = time.perf_counter()
    historico = []
    for _ in range(geracoes):
        grade = proxima_geracao(grade, limiar)
        contagem = contar_estados(grade)
        historico.append((contagem[IGNORANTE], contagem[ESPALHADOR], contagem[INATIVO]))
        if contagem[ESPALHADOR] == 0:
            break
    return grade, historico, time.perf_counter() - comeco


def _argumentos(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--linhas", type=int, default=1000)
    parser.add_argument("--colunas", type=int, default=1000)
    parser.add_argument("--geracoes", type=int, default=30)
    parser.add_argument("--espalhadores", type=float, default=0.02)
    parser.add_argument("--limiar", type=int, default=2)
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("-w", "--workers", "--threads", dest="workers", type=int,
                        nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--backend", nargs="+", choices=paralelo.BACKENDS,
                        default=["threads", "processos"])
    parser.add_argument("--kernel", nargs="+", choices=sorted(KERNELS),
                        default=["otimizado"])
    parser.add_argument("--divisao", nargs="+", choices=paralelo.DIVISOES,
                        default=["estatica"])
    parser.add_argument("--pedaco", type=int,
                        help="Linhas por pedaço na divisão dinâmica (padrão: automático).")
    parser.add_argument("--repeticoes", type=int, default=3,
                        help="Execuções por configuração; a tabela usa a mediana.")
    parser.add_argument("--sequencial", action="store_true",
                        help="Roda também o código original do professor (lento).")
    parser.add_argument("--csv", type=Path, help="Acrescenta cada execução neste CSV.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _argumentos(argv)
    sem_economia = desligar_economia_de_energia()
    workers = sorted(set(args.workers) | {1})  # 1 worker é a base do speedup
    gil = "ativo" if paralelo.gil_ativo() else "desligado"
    ambiente = {
        "data": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "gil": gil,
        "cpus": os.cpu_count(),
    }
    print(f"Python {platform.python_version()} ({sys.executable}) | GIL {gil} | "
          f"{os.cpu_count()} CPUs lógicas | {platform.platform()}")
    if sys.platform == "win32":
        print("Economia de energia do Windows (EcoQoS): "
              + ("desligada" if sem_economia else "NÃO foi possível desligar"))
    print(f"Grade {args.linhas}x{args.colunas} | até {args.geracoes} gerações | "
          f"{args.espalhadores:.0%} espalhadores | limiar {args.limiar} | "
          f"{args.repeticoes} repetição(ões)\n")

    grade = criar_grade(args.linhas, args.colunas, args.espalhadores, args.semente)
    registros: list[dict] = []
    referencia = None
    tempo_professor = None

    if args.sequencial:
        grade_prof, historico_prof, tempo_professor = rodar_professor(
            grade, args.geracoes, args.limiar)
        referencia = (grade_prof, historico_prof)
        print(f"Professor (sequencial original): {tempo_professor:.3f} s, "
              f"{len(historico_prof)} gerações\n")
        registros.append({**ambiente, "backend": "sequencial-professor",
                          "kernel": "professor", "divisao": "-", "pedaco": 0,
                          "workers": 1, "repeticao": 1,
                          "geracoes_executadas": len(historico_prof),
                          "tempo_geracoes_s": tempo_professor,
                          "tempo_total_s": tempo_professor,
                          "caminho_critico_s": tempo_professor,
                          "calculo_medio_s": tempo_professor,
                          "desbalanceamento": 1.0, "sincronizacao_s": 0.0,
                          "identico": True})

    combinacoes = [(backend, kernel, divisao, n)
                   for backend in args.backend for kernel in args.kernel
                   for divisao in args.divisao for n in workers]
    execucoes: dict[tuple, list] = {combinacao: [] for combinacao in combinacoes}
    total_execucoes = len(combinacoes) * args.repeticoes
    feitas = 0

    # Ordem embaralhada por repetição: aquecimento e perda de turbo não favorecem sempre as mesmas variantes.
    for repeticao in range(1, args.repeticoes + 1):
        ordem = list(combinacoes)
        random.Random(repeticao).shuffle(ordem)
        for backend, kernel, divisao, n in ordem:
            r = paralelo.simular_paralelo(grade, args.geracoes, args.limiar, n,
                                          backend, kernel, divisao, args.pedaco)
            if referencia is None:
                referencia = (r.grade_final, r.historico)
            identico = (r.grade_final, r.historico) == referencia
            execucoes[(backend, kernel, divisao, n)].append((r, identico))
            registros.append({
                **ambiente, "backend": backend, "kernel": kernel,
                "divisao": divisao, "pedaco": r.pedaco, "workers": n,
                "repeticao": repeticao,
                "geracoes_executadas": r.geracoes_executadas,
                "tempo_geracoes_s": r.tempo_geracoes_s,
                "tempo_total_s": r.tempo_total_s,
                "caminho_critico_s": r.tempo_caminho_critico_s,
                "calculo_medio_s": sum(r.tempo_calculo_s) / n,
                "desbalanceamento": r.desbalanceamento,
                "sincronizacao_s": r.tempo_sincronizacao_s,
                "identico": identico,
            })
            feitas += 1
            print(f"\r{feitas}/{total_execucoes} execuções", end="", flush=True)
    print("\n")

    cabecalho = (f"{'backend':<10} {'kernel':<10} {'divisão':<9} {'workers':>7} "
                 f"{'gerações(s)':>11} {'total(s)':>9} {'speedup':>8} {'eficiência':>10} "
                 f"{'vs prof.':>8} {'desbal.':>8} {'sinc.(s)':>8} {'ok':>3}")
    print(cabecalho)
    print("-" * len(cabecalho))
    tempo_base: dict[tuple, float] = {}
    for backend, kernel, divisao, n in combinacoes:
        rodadas = execucoes[(backend, kernel, divisao, n)]
        tempo = statistics.median(r.tempo_geracoes_s for r, _ in rodadas)
        total = statistics.median(r.tempo_total_s for r, _ in rodadas)
        desbal = statistics.median(r.desbalanceamento for r, _ in rodadas)
        sinc = statistics.median(r.tempo_sincronizacao_s for r, _ in rodadas)
        base = tempo_base.setdefault((backend, kernel, divisao), tempo)  # n = 1 vem primeiro
        speedup = base / tempo
        vs_prof = f"{tempo_professor / tempo:8.2f}" if tempo_professor else f"{'-':>8}"
        ok = "sim" if all(identico for _, identico in rodadas) else "NÃO"
        print(f"{backend:<10} {kernel:<10} {divisao:<9} {n:>7} {tempo:>11.3f} "
              f"{total:>9.3f} {speedup:>8.2f} {speedup / n:>10.0%} {vs_prof} "
              f"{desbal:>8.2f} {sinc:>8.3f} {ok:>3}")

    print("\nspeedup = T(1 worker) / T(N); eficiência = speedup / N; "
          "vs prof. = T(professor) / T(N);\n"
          "desbal. = cálculo do worker mais lento / média, geração a geração "
          "(1,00 = equilibrado);\n"
          "sinc. = tempo das gerações - soma do worker mais lento de cada geração "
          "(barreiras e coordenação;\ncom GIL inclui a espera pelo GIL).")

    if args.csv:
        novo = not args.csv.exists()
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fixos = {"linhas": args.linhas, "colunas": args.colunas,
                 "geracoes_pedidas": args.geracoes, "espalhadores": args.espalhadores,
                 "limiar": args.limiar, "semente": args.semente}
        with args.csv.open("a", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS_CSV)
            if novo:
                escritor.writeheader()
            for registro in registros:
                escritor.writerow({**fixos, **registro})
        print(f"\n{len(registros)} execuções gravadas em {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
