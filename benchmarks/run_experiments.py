"""Executa cenários reproduzíveis das três versões; --piloto usa padrões pequenos.

Da raiz: py benchmarks/run_experiments.py --piloto
Exemplo: py benchmarks/run_experiments.py --linhas 500 1000 --colunas 500 1000
         --geracoes 30 --espalhadores 0.01 0.02 0.05 --limiar 2 --workers 1 2 4 8

Tamanhos, gerações, espalhadores, limiares e parâmetros das extensões
(--probabilidade, --influenciadores, --peso-influenciador, --bots) formam um
produto cartesiano. Cenários com extensões não têm a referência do código
original, que não as implementa: a referência passa a ser o sequencial do núcleo.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
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

from common.modelo import PESO_INFLUENCIADOR_PADRAO  # noqa: E402  (src/ no path via adapters)


CAMPOS = [
    "experimento", "cenario", "fase", "repeticao", "backend", "workers",
    "kernel", "divisao", "linhas", "colunas", "geracoes_pedidas",
    "espalhadores", "limiar", "semente",
    "probabilidade", "influenciadores", "peso_influenciador", "bots", "geracoes_executadas",
    "tempo_externo_s", "tempo_geracoes_s", "tempo_total_s",
    "caminho_critico_s", "overhead_s", "celulas_halo",
    "matriz_identica", "historico_identico", "status", "erro",
]
BACKENDS = ("threads", "processos", "distribuida")
KERNELS = tuple(k for k in adapters.KERNELS_SEQUENCIAIS if k != "professor")


def _modelo_cpu():
    """Obtém uma identificação legível sem dependências externas."""
    if os.name == "nt":
        try:
            import winreg
            caminho = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, caminho) as chave:
                return winreg.QueryValueEx(chave, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    return (platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER")
            or platform.machine() or "não identificado").strip()


def _memoria_total_bytes():
    """Retorna a RAM física total no Windows/POSIX ou ``None`` se indisponível."""
    if os.name == "nt":
        class EstadoMemoria(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        estado = EstadoMemoria()
        estado.dwLength = ctypes.sizeof(estado)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
            return int(estado.ullTotalPhys)
        return None
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, ValueError):
        return None


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
    extensoes = parser.add_argument_group("extensões do modelo (docs/extensoes-modelo.md)")
    extensoes.add_argument("--probabilidade", type=float, nargs="+", default=[1.0])
    extensoes.add_argument("--influenciadores", type=float, nargs="+", default=[0.0])
    extensoes.add_argument("--peso-influenciador", type=int, nargs="+",
                           default=[PESO_INFLUENCIADOR_PADRAO])
    extensoes.add_argument("--bots", type=float, nargs="+", default=[0.0])
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
    if (any(not 0 < p <= 1 for p in args.probabilidade)
            or any(not 0 <= f <= 1 for f in args.influenciadores + args.bots)
            or any(w < 1 for w in args.peso_influenciador)):
        parser.error("Probabilidade em (0, 1]; influenciadores e bots entre 0 e 1; peso >= 1.")
    return args


def cenarios(args):
    """Produto cartesiano dos parâmetros, sem repetir cenários equivalentes.

    Sem influenciadores o peso não tem efeito, então só o primeiro é usado.
    """
    vistos = {}
    for linhas, colunas, geracoes, espalhadores, limiar, p, influenciadores, peso, bots in (
            itertools.product(args.linhas, args.colunas, args.geracoes, args.espalhadores,
                              args.limiar, args.probabilidade, args.influenciadores,
                              args.peso_influenciador, args.bots)):
        if influenciadores == 0:
            peso = args.peso_influenciador[0]
        vistos.setdefault((linhas, colunas, geracoes, espalhadores, limiar, p,
                           influenciadores, peso, bots), None)
    return list(vistos)


def _executar(grade, geracoes, limiar, backend, workers, kernel, modelo=None, tipos=None):
    extensoes = dict(modelo=modelo, tipos=tipos)
    if backend == "sequencial":
        return adapters.executar_sequencial(grade, geracoes, limiar, kernel=kernel, **extensoes)
    if backend == "distribuida":
        return adapters.executar_distribuido(
            grade, geracoes, limiar, workers=workers, kernel=kernel, **extensoes,
        )
    return adapters.executar_paralelo(
        grade, geracoes, limiar, workers=workers, backend=backend,
        kernel=kernel, divisao="estatica", **extensoes,
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
        "plataforma": platform.platform(), "modelo_cpu": _modelo_cpu(),
        "cpus_logicas": os.cpu_count(), "memoria_ram_bytes": _memoria_total_bytes(),
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
    comparadas = [("sequencial", 1, args.kernel)] + [
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
        for cenario, parametros in enumerate(cenarios(args), 1):
            (linhas, colunas, geracoes, espalhadores, limiar,
             probabilidade, influenciadores, peso, bots) = parametros
            config = adapters.core.Config(
                linhas=linhas, colunas=colunas, percentual_espalhadores=espalhadores,
                semente=args.semente, probabilidade_convencimento=probabilidade,
                percentual_influenciadores=influenciadores, peso_influenciador=peso,
                percentual_bots=bots,
            )
            grade, tipos, modelo = adapters.core.preparar_inicio(config)
            configuracoes = comparadas if modelo else [("sequencial", 1, "professor")] + comparadas
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
                            probabilidade=probabilidade, influenciadores=influenciadores,
                            peso_influenciador=peso, bots=bots,
                        )
                        try:
                            resultado = _executar(grade, geracoes, limiar, backend, workers, kernel,
                                                  modelo, tipos)
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
            extras = "" if modelo is None else (
                f", probabilidade {probabilidade}, influenciadores {influenciadores:.1%} "
                f"(peso {peso}), bots {bots:.1%}")
            print(f"Cenário {cenario}: {linhas}x{colunas}, até {geracoes} gerações, "
                  f"{espalhadores:.0%} espalhadores, limiar {limiar}{extras} concluído.")
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
