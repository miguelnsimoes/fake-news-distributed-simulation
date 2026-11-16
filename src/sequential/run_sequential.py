"""
Versão SEQUENCIAL da simulação de propagação de Fake News.

Uso (a partir da raiz do repositório):
    python src/sequential/run_sequential.py
    python src/sequential/run_sequential.py -l 500 -c 500 -g 100 -p 0.02 -t 2
    python src/sequential/run_sequential.py --silencioso --saida resultado_seq.json   # benchmarks
    python src/sequential/run_sequential.py --mostrar-grade -l 20 -c 20 -g 10         # demonstração

A saída em JSON (--saida) segue o formato padronizado de `Resultado`
(ver src/common/core.py) e é a mesma das versões paralela e distribuída.

Observação: o código original do professor continua intacto em fake_news.py;
este arquivo usa o núcleo refatorado de src/common/core.py.
"""

import argparse
import json
import sys
from pathlib import Path

# Permite `from common.core import ...` ao rodar o script direto (python src/sequential/...).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.core import (
    Config, Grade, IGNORANTE, ESPALHADOR, INATIVO,
    contar_estados, simular,
)

SIMBOLOS = {IGNORANTE: ".", ESPALHADOR: "E", INATIVO: "N"}


def imprimir_grade(grade: Grade, limite: int = 30) -> None:
    """Mostra o canto superior esquerdo da grade (no máx. limite x limite)."""
    for i in range(min(len(grade), limite)):
        print(" ".join(SIMBOLOS[x] for x in grade[i][:limite]))
    print()


def ler_argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Propagação de Fake News - versão sequencial")
    p.add_argument("-l", "--linhas", type=int, default=100)
    p.add_argument("-c", "--colunas", type=int, default=100)
    p.add_argument("-g", "--geracoes", type=int, default=50)
    p.add_argument("-p", "--percentual", type=float, default=0.05,
                   help="percentual inicial de espalhadores (0 a 1). Ex.: 0.05 = 5%%")
    p.add_argument("-t", "--limiar", type=int, default=3,
                   help="limiar de convencimento (nº de vizinhos espalhadores)")
    p.add_argument("-s", "--semente", type=int, default=42)
    p.add_argument("--mostrar-grade", action="store_true",
                   help="imprime a grade a cada geração (só p/ grades pequenas)")
    p.add_argument("--silencioso", action="store_true",
                   help="não imprime nada por geração (use nos benchmarks)")
    p.add_argument("--saida", type=str, default=None,
                   help="caminho de um arquivo JSON para salvar o resultado")
    p.add_argument("--incluir-grade", action="store_true",
                   help="inclui a grade final no JSON (arquivo grande!)")
    return p.parse_args()


def main() -> None:
    a = ler_argumentos()
    config = Config(
        linhas=a.linhas,
        colunas=a.colunas,
        geracoes=a.geracoes,
        percentual_espalhadores=a.percentual,
        limiar_convencimento=a.limiar,
        semente=a.semente,
    )

    total = config.linhas * config.colunas
    if not a.silencioso:
        print("=== SIMULAÇÃO SEQUENCIAL DE PROPAGAÇÃO DE FAKE NEWS ===")
        print(f"Tamanho da grade: {config.linhas} x {config.colunas} ({total:,} pessoas)")
        print(f"Gerações: {config.geracoes}")
        print(f"Percentual inicial de espalhadores: {config.percentual_espalhadores * 100:.2f}%")
        print(f"Limiar de convencimento: {config.limiar_convencimento} vizinhos")
        print()

    def gancho(geracao, grade, contagem):
        if a.silencioso:
            return
        print(f"Geração {geracao:03d} | "
              f"Ignorantes: {contagem[IGNORANTE]:>10,} | "
              f"Espalhadores: {contagem[ESPALHADOR]:>10,} | "
              f"Inativos: {contagem[INATIVO]:>10,}")
        if a.mostrar_grade:
            imprimir_grade(grade)

    resultado = simular(config, ao_final_de_geracao=None if a.silencioso and not a.mostrar_grade else gancho)

    if not a.silencioso:
        if resultado.geracoes_executadas < config.geracoes:
            print("\nA propagação terminou: não há mais espalhadores.")
        final = contar_estados(resultado.grade_final)
        print("\n=== RESULTADO FINAL ===")
        print(f"Gerações executadas: {resultado.geracoes_executadas}")
        print(f"Tempo total de execução: {resultado.tempo_s:.4f} segundos")
        for nome, estado in (("Ignorantes", IGNORANTE), ("Espalhadores", ESPALHADOR), ("Inativos", INATIVO)):
            print(f"{nome} finais: {final[estado]:,} ({final[estado] / total * 100:,.2f}%)")
        print(f"Hash da grade final: {resultado.hash_grade[:16]}...")
    else:
        # modo silencioso: uma única linha, fácil de ler em scripts de benchmark
        print(f"sequencial tempo_s={resultado.tempo_s:.6f} hash={resultado.hash_grade}")

    if a.saida:
        with open(a.saida, "w", encoding="utf-8") as f:
            json.dump(resultado.para_dict(incluir_grade=a.incluir_grade), f, ensure_ascii=False)
        if not a.silencioso:
            print(f"Resultado salvo em {a.saida}")


if __name__ == "__main__":
    main()
