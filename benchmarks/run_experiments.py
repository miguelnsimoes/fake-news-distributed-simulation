"""Executa cenários reproduzíveis; --piloto usa padrões pequenos.

Da raiz: py benchmarks/run_experiments.py --piloto
Ou: py -m benchmarks.run_experiments --piloto
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
    "matriz_identica", "historico_identico", "status", "erro",
]


def argumentos(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--piloto", action="store_true", help="Padrões: 12x12, 4 gerações, workers 1 e 2, 2 repetições.")
    parser.add_argument("--linhas", type=int, nargs="+")
    parser.add_argument("--colunas", type=int, nargs="+")
    parser.add_argument("--geracoes", type=int, nargs="+")
    parser.add_argument("--espalhadores", type=float, default=0.02, help="Fração de 0 a 1; 0.02 = 2%%.")
    parser.add_argument("--limiar", type=int, default=2)
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--workers", type=int, nargs="+")
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
    if not 0 <= args.espalhadores <= 1 or not 0 <= args.limiar <= 8:
        parser.error("Espalhadores devem estar entre 0 e 1; limiar entre 0 e 8.")
    return args


def _executar(grade, geracoes, limiar, backend, workers):
    if backend == "sequencial":
        return adapters.executar_sequencial(grade, geracoes, limiar)
    return adapters.executar_paralelo(
        grade, geracoes, limiar, workers=workers, backend=backend,
        kernel="otimizado", divisao="estatica",
    )


def executar_experimento(args):
    """Grava aquecimento separado e medições; retorna (diretório, sucesso).

    Uma única grade é criada por cenário. O sequencial de aquecimento fornece
    a referência; todas as chamadas, inclusive sequenciais medidas, são
    comparadas com ela fora dos cronômetros. Falhas são registradas e resultam
    em código de saída não zero. Sem referência válida, aborta o cenário.
    Os tamanhos e gerações fornecidos formam um produto cartesiano.
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
        "kernel_paralelo": "otimizado", "divisao": "estatica",
        "escopo_tempo_externo": "Chamada do adaptado, sem cópia defensiva, validação, CSV ou impressão.",
        "energia": "Executor não altera a política de energia; processos filhos seguem a implementação original.",
        "ordem": "Aquecimento sequencial primeiro; medições embaralhadas por repetição com semente fixa.",
    }
    (pasta / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    configuracoes = [("sequencial", 1)] + [
        (backend, n) for backend in ("threads", "processos") for n in sorted(set(args.workers))
    ]
    sucesso = True
    # Arquivos distintos impedem agregar aquecimento como medição por engano.
    with (pasta / "raw.csv").open("w", newline="", encoding="utf-8") as raw, \
         (pasta / "warmup.csv").open("w", newline="", encoding="utf-8") as warmup:
        escritores = {"medicao": csv.DictWriter(raw, fieldnames=CAMPOS),
                      "aquecimento": csv.DictWriter(warmup, fieldnames=CAMPOS)}
        for escritor in escritores.values():
            escritor.writeheader()
        cenarios = itertools.product(dict.fromkeys(args.linhas), dict.fromkeys(args.colunas), dict.fromkeys(args.geracoes))
        for cenario, (linhas, colunas, geracoes) in enumerate(cenarios, 1):
            grade = adapters.sequencial.criar_grade(linhas, colunas, args.espalhadores, args.semente)
            referencia = None
            for fase, repeticoes in (("aquecimento", 1), ("medicao", args.repeticoes)):
                for repeticao in range(1, repeticoes + 1):
                    ordem = list(configuracoes)
                    if fase == "medicao":
                        random.Random(args.semente + repeticao).shuffle(ordem)
                    for backend, workers in ordem:
                        registro = dict.fromkeys(CAMPOS, "")
                        registro.update(
                            experimento=identificador, cenario=cenario, fase=fase,
                            repeticao=repeticao, backend=backend, workers=workers,
                            kernel="professor" if backend == "sequencial" else "otimizado",
                            divisao="" if backend == "sequencial" else "estatica",
                            linhas=linhas, colunas=colunas, geracoes_pedidas=geracoes,
                            espalhadores=args.espalhadores, limiar=args.limiar, semente=args.semente,
                        )
                        try:
                            resultado = _executar(grade, geracoes, args.limiar, backend, workers)
                            if referencia is None:
                                referencia = resultado
                            matriz = resultado.grade_final == referencia.grade_final
                            historico = resultado.historico == referencia.historico
                            registro.update(
                                geracoes_executadas=resultado.geracoes_executadas,
                                tempo_externo_s=resultado.tempo_externo_s,
                                tempo_geracoes_s=resultado.tempo_geracoes_s,
                                tempo_total_s=resultado.tempo_total_s,
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
            print(f"Cenário {cenario}: {linhas}x{colunas}, até {geracoes} gerações concluído.")
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
