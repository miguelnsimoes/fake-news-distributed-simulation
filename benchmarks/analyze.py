"""Agrega raw.csv usando apenas medições equivalentes e tempos positivos finitos.

Uso: py benchmarks/analyze.py benchmarks/results/<experimento>
Também aceita o caminho de raw.csv. Somente summary.csv é escrito.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


CENARIO = (
    "experimento", "cenario", "linhas", "colunas", "geracoes_pedidas",
    "espalhadores", "limiar", "semente",
)
CONFIGURACAO = ("backend", "kernel", "divisao", "workers")
OBRIGATORIOS = set(CENARIO + CONFIGURACAO + (
    "fase", "tempo_externo_s", "matriz_identica", "historico_identico", "status",
))
CAMPOS = list(CENARIO) + ["implementacao"] + list(CONFIGURACAO) + [
    "repeticoes_validas", "repeticoes_invalidas", "mediana_tempo_externo_s",
    "media_tempo_externo_s", "desvio_padrao_tempo_externo_s",
    "minimo_tempo_externo_s", "maximo_tempo_externo_s",
    "ganho_vs_sequencial", "speedup_vs_sequencial", "eficiencia_vs_sequencial",
    "speedup_escalabilidade", "eficiencia_escalabilidade", "mediana_overhead_s",
]


def implementacao(backend):
    """Versão do enunciado a que cada backend pertence."""
    if backend == "sequencial":
        return "sequencial"
    if backend == "distribuida":
        return "distribuida"
    return "paralela"


def _numero(valor):
    try:
        numero = float(valor)
    except (ValueError, TypeError):
        return None
    return numero if math.isfinite(numero) and numero >= 0 else None


def _tempo_valido(registro):
    if (registro["status"].strip().lower() != "ok"
            or registro["matriz_identica"].strip().lower() != "true"
            or registro["historico_identico"].strip().lower() != "true"):
        return None
    try:
        tempo = float(registro["tempo_externo_s"])
    except (ValueError, TypeError):
        return None
    return tempo if math.isfinite(tempo) and tempo > 0 else None


def resumir(registros):
    """Uma linha por configuração, considerando só medições válidas.

    Referências:
      ganho_vs_sequencial     código original (kernel "professor"): ganho total.
      speedup_vs_sequencial   sequencial com o mesmo kernel: ganho só do paralelismo.
      speedup_escalabilidade  mesma configuração com 1 worker.
    """
    grupos = {}
    for registro in registros:
        if registro["fase"].strip() != "medicao":
            continue
        chave = tuple(registro[campo].strip() for campo in CENARIO + CONFIGURACAO)
        try:
            workers = int(chave[-1])
        except ValueError as erro:
            raise ValueError("Número de workers inválido no raw.csv.") from erro
        if workers < 1:
            raise ValueError("Número de workers deve ser positivo no raw.csv.")
        chave = chave[:-1] + (workers,)
        grupo = grupos.setdefault(chave, {"tempos": [], "invalidas": 0, "overheads": []})
        tempo = _tempo_valido(registro)
        if tempo is None:
            grupo["invalidas"] += 1
        else:
            grupo["tempos"].append(tempo)
            overhead = _numero(registro.get("overhead_s"))
            if overhead is not None:
                grupo["overheads"].append(overhead)

    linhas = []
    sequenciais = defaultdict(list)  # (cenário, kernel) -> medianas
    bases = {}
    for chave, grupo in grupos.items():
        linha = dict.fromkeys(CAMPOS, "")
        linha.update(zip(CENARIO + CONFIGURACAO, chave))
        linha["implementacao"] = implementacao(linha["backend"])
        tempos = grupo["tempos"]
        linha.update(repeticoes_validas=len(tempos), repeticoes_invalidas=grupo["invalidas"])
        if tempos:
            mediana = statistics.median(tempos)
            linha.update(
                mediana_tempo_externo_s=mediana,
                media_tempo_externo_s=statistics.mean(tempos),
                desvio_padrao_tempo_externo_s=statistics.stdev(tempos) if len(tempos) > 1 else "",
                minimo_tempo_externo_s=min(tempos), maximo_tempo_externo_s=max(tempos),
            )
            if grupo["overheads"]:
                linha["mediana_overhead_s"] = statistics.median(grupo["overheads"])
            cenario = chave[:len(CENARIO)]
            if linha["backend"] == "sequencial" and linha["workers"] == 1:
                sequenciais[(cenario, linha["kernel"])].append(mediana)
            if linha["workers"] == 1:
                bases[chave[:-1]] = mediana
        linhas.append((chave, linha))

    for chave, linha in linhas:
        mediana = linha["mediana_tempo_externo_s"]
        if mediana == "":
            continue
        cenario = chave[:len(CENARIO)]
        referencias = sequenciais.get((cenario, "professor"))
        if referencias is None:
            referencias = [m for (c, _), ms in sequenciais.items() if c == cenario for m in ms]
        # Se houver referências sequenciais distintas, não escolher arbitrariamente.
        if len(referencias) == 1:
            linha["ganho_vs_sequencial"] = referencias[0] / mediana
        mesmo_kernel = sequenciais.get((cenario, linha["kernel"]), [])
        if linha["implementacao"] != "sequencial" and len(mesmo_kernel) == 1:
            speedup = mesmo_kernel[0] / mediana
            linha["speedup_vs_sequencial"] = speedup
            linha["eficiencia_vs_sequencial"] = speedup / linha["workers"]
        if linha["implementacao"] != "sequencial" and chave[:-1] in bases:
            speedup = bases[chave[:-1]] / mediana
            linha["speedup_escalabilidade"] = speedup
            linha["eficiencia_escalabilidade"] = speedup / linha["workers"]
    return [linha for _, linha in linhas]


def analisar(caminho):
    """Lê raw.csv e grava summary.csv adjacente, preservando as entradas."""
    caminho = Path(caminho)
    raw = caminho / "raw.csv" if caminho.is_dir() else caminho
    if raw.name != "raw.csv":
        raise ValueError("Informe um diretório de experimento ou um arquivo raw.csv.")
    with raw.open(newline="", encoding="utf-8-sig") as arquivo:
        leitor = csv.DictReader(arquivo)
        ausentes = OBRIGATORIOS - set(leitor.fieldnames or [])
        if ausentes:
            raise ValueError("Colunas ausentes: " + ", ".join(sorted(ausentes)))
        linhas = resumir(leitor)
    summary = raw.with_name("summary.csv")
    with summary.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CAMPOS)
        escritor.writeheader()
        escritor.writerows(linhas)
    return summary, linhas


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experimento", type=Path)
    args = parser.parse_args(argv)
    try:
        summary, linhas = analisar(args.experimento)
    except (OSError, ValueError) as erro:
        parser.exit(1, f"Erro: {erro}\n")
    print(f"Resumo: {summary}")
    print(f"{len(linhas)} configurações; "
          f"{sum(l['repeticoes_validas'] for l in linhas)} medições válidas; "
          f"{sum(l['repeticoes_invalidas'] for l in linhas)} inválidas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
