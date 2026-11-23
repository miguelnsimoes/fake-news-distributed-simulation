"""Gera PNGs de summary.csv, sem recalcular estatísticas ou referências.

Uso: py benchmarks/plot_results.py benchmarks/results/<experimento>
Requer Matplotlib. Renderiza sem interface gráfica, inclusive no Windows.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter


CENARIO = ("experimento", "cenario", "linhas", "colunas", "geracoes_pedidas",
           "espalhadores", "limiar", "semente")
SERIE = ("implementacao", "backend", "kernel", "divisao")
METRICAS = ("mediana_tempo_externo_s", "speedup_vs_sequencial",
            "speedup_escalabilidade", "eficiencia_escalabilidade")
OBRIGATORIOS = set(CENARIO + SERIE + METRICAS + ("workers", "repeticoes_validas"))


def numero(valor):
    """Ausente, não finito ou não positivo permanece ausente, nunca vira zero."""
    try:
        valor = float(valor)
    except (ValueError, TypeError):
        return math.nan
    return valor if math.isfinite(valor) and valor > 0 else math.nan


def ler_cenarios(summary):
    grupos = defaultdict(list)
    vistos = set()
    with Path(summary).open(newline="", encoding="utf-8-sig") as arquivo:
        leitor = csv.DictReader(arquivo)
        ausentes = OBRIGATORIOS - set(leitor.fieldnames or [])
        if ausentes:
            raise ValueError("Colunas ausentes: " + ", ".join(sorted(ausentes)))
        for registro in leitor:
            registro = {k: v.strip() if v is not None else "" for k, v in registro.items()}
            cenario = tuple(registro[c] for c in CENARIO)
            registro["workers"] = int(registro["workers"])
            registro["repeticoes_validas"] = int(registro["repeticoes_validas"])
            if registro["workers"] < 1 or registro["repeticoes_validas"] < 0:
                raise ValueError("Workers ou repetições inválidos.")
            chave = cenario + tuple(registro[c] for c in SERIE) + (registro["workers"],)
            if chave in vistos:
                raise ValueError("Configuração duplicada no summary.csv; execute analyze.py novamente.")
            vistos.add(chave)
            for metrica in METRICAS:
                registro[metrica] = numero(registro[metrica]) if registro["repeticoes_validas"] else math.nan
            grupos[cenario].append(registro)
    return grupos


def rotulo(serie):
    implementacao, backend, kernel, divisao = serie
    return f"{implementacao} / {backend}\nkernel={kernel}; divisão={divisao or '—'}"


def _descrever_extensoes(registro):
    """Linha extra do título quando o cenário usa extensões do modelo."""
    p = registro.get("probabilidade") or "1.0"
    influenciadores = registro.get("influenciadores") or "0.0"
    bots = registro.get("bots") or "0.0"
    if float(p) == 1 and float(influenciadores) == 0 and float(bots) == 0:
        return ""
    return (f"\nExtensões: probabilidade={p}; influenciadores={influenciadores} "
            f"(peso {registro.get('peso_influenciador') or '-'}); bots={bots}")


def _figura(titulo):
    figura = Figure(figsize=(11, 7), layout="constrained")
    FigureCanvasAgg(figura)
    eixo = figura.subplots()
    eixo.set_title(titulo, fontsize=10)
    eixo.grid(axis="y", alpha=0.25)
    eixo.set_axisbelow(True)
    return figura, eixo


def _salvar(figura, caminho):
    figura.savefig(caminho, dpi=160, format="png")
    figura.clear()
    return caminho


def gerar_graficos(experimento):
    """Salva gráficos de tempo, speedup e eficiência por cenário; devolve os caminhos."""
    pasta = Path(experimento)
    cenarios = ler_cenarios(pasta / "summary.csv")
    destino = pasta / "figures"
    destino.mkdir(exist_ok=True)
    arquivos = []
    for indice, (cenario, registros) in enumerate(sorted(cenarios.items()), 1):
        exp, identificador, linhas, colunas, geracoes, espalhadores, limiar, semente = cenario
        titulo = (f"Experimento {exp} | cenário {identificador}\n"
                  f"Matriz {linhas}×{colunas}; gerações máximas={geracoes}; "
                  f"fração inicial={espalhadores}; limiar={limiar}; semente={semente}"
                  + _descrever_extensoes(registros[0]))
        registros.sort(key=lambda r: tuple(r[c] for c in SERIE) + (r["workers"],))
        validos = [r for r in registros if math.isfinite(r[METRICAS[0]])]
        figura, eixo = _figura("Tempo externo mediano\n" + titulo)
        if validos:
            tempos = [r[METRICAS[0]] for r in validos]
            labels = [rotulo(tuple(r[c] for c in SERIE)) +
                      f"\nworkers={r['workers']}; n={r['repeticoes_validas']}" for r in validos]
            eixo.bar(range(len(tempos)), tempos)
            eixo.set_xticks(range(len(tempos)), labels, rotation=25, ha="right", fontsize=8)
            if max(tempos) / min(tempos) > 100:
                eixo.set_yscale("log")
                eixo.set_ylabel("Tempo externo mediano (s; escala logarítmica)")
            else:
                eixo.set_ylabel("Tempo externo mediano (s)")
        else:
            eixo.text(0.5, 0.5, "Sem tempos válidos", transform=eixo.transAxes, ha="center")
            eixo.set_ylabel("Tempo externo mediano (s)")
        arquivos.append(_salvar(figura, destino / f"cenario_{indice:03d}_tempo.png"))

        series = defaultdict(list)
        for registro in registros:
            if registro["implementacao"] != "sequencial":
                series[tuple(registro[c] for c in SERIE)].append(registro)
        for metrica, nome, unidade in (
            ("speedup_vs_sequencial", "speedup_sequencial", "Speedup contra a sequencial (x)"),
            ("speedup_escalabilidade", "speedup", "Speedup de escalabilidade (×)"),
            ("eficiencia_escalabilidade", "eficiencia", "Eficiência de escalabilidade (%)"),
        ):
            figura, eixo = _figura(unidade + "\n" + titulo)
            presentes = False
            for serie, pontos in sorted(series.items()):
                pontos.sort(key=lambda r: r["workers"])
                valores = [r[metrica] for r in pontos]
                if any(math.isfinite(v) for v in valores):
                    eixo.plot([r["workers"] for r in pontos], valores, marker="o", label=rotulo(serie))
                    presentes = True
            if presentes:
                eixo.legend(fontsize=8)
                eixo.set_ylim(bottom=0)
            else:
                eixo.text(0.5, 0.5, "Sem valores válidos com referência de 1 worker",
                          transform=eixo.transAxes, ha="center")
            eixo.set_xticks(sorted({r["workers"] for r in registros}))
            eixo.set_xlabel("Quantidade de workers")
            eixo.set_ylabel(unidade)
            if nome == "eficiencia":
                eixo.yaxis.set_major_formatter(PercentFormatter(xmax=1))
            arquivos.append(_salvar(figura, destino / f"cenario_{indice:03d}_{nome}.png"))
    return arquivos


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experimento", type=Path)
    args = parser.parse_args(argv)
    try:
        arquivos = gerar_graficos(args.experimento)
    except (OSError, ValueError) as erro:
        parser.exit(1, f"Erro: {erro}\n")
    for arquivo in arquivos:
        print(arquivo)
    if not arquivos:
        print("summary.csv não contém cenários; nenhum gráfico gerado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
