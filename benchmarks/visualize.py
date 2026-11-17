"""Anima a trajetória sequencial de referência, separada dos benchmarks.

Uso: py benchmarks/visualize.py --linhas 20 --colunas 20 --geracoes 15
Exporta GIF e PNGs por padrão; --mostrar também abre uma janela de animação.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Patch

_SEQUENCIAL = str(Path(__file__).resolve().parents[1] / "src" / "sequential")
if _SEQUENCIAL not in sys.path:
    sys.path.insert(0, _SEQUENCIAL)
from fake_news import criar_grade, proxima_geracao, contar_estados  # noqa: E402

CORES = ("#d9e2ec", "#e66101", "#5e3c99")
ESTADOS = ("Ignorante (0)", "Espalhador (1)", "Inativo (2)")


@dataclass
class Quadro:
    geracao: int
    grade: list[list[int]]
    contagem: dict[int, int]


def gerar_trajetoria(grade_inicial, geracoes, limiar):
    """Inclui geração zero e preserva a entrada; mesma parada do original.

    Mesmo uma grade inicialmente sem espalhadores executa uma geração se o
    limite permitir, pois o original verifica a parada após a atualização.
    Armazena todas as grades: use matrizes pequenas para demonstrações.
    """
    if geracoes < 0:
        raise ValueError("Gerações devem ser não negativas.")
    grade = [list(linha) for linha in grade_inicial]
    if not grade or not grade[0] or any(len(l) != len(grade[0]) for l in grade):
        raise ValueError("A matriz deve ser retangular e não vazia.")
    if any(c not in (0, 1, 2) for linha in grade for c in linha):
        raise ValueError("Estados devem ser 0, 1 ou 2.")
    quadros = [Quadro(0, grade, contar_estados(grade))]
    for geracao in range(1, geracoes + 1):
        grade = proxima_geracao(grade, limiar)
        contagem = contar_estados(grade)
        quadros.append(Quadro(geracao, grade, contagem))
        if contagem[1] == 0:
            break
    return quadros


def criar_animacao(quadros, *, fps=4, configuracao="", figura=None):
    """Retorna figura, animação e função de atualização para exportação/preview."""
    if not quadros or fps <= 0:
        raise ValueError("São necessários quadros e fps positivo.")
    if figura is None:
        figura = Figure(figsize=(7, 7), layout="constrained")
        FigureCanvasAgg(figura)
    eixo = figura.subplots()
    mapa = ListedColormap(CORES)
    imagem = eixo.imshow(quadros[0].grade, cmap=mapa,
                         norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3), interpolation="nearest")
    eixo.set_xlabel("Coluna")
    eixo.set_ylabel("Linha")
    figura.suptitle("Propagação de fake news — referência sequencial\n" + configuracao, fontsize=10)
    eixo.legend(handles=[Patch(facecolor=c, label=e) for c, e in zip(CORES, ESTADOS)],
                loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=9)

    def atualizar(indice):
        quadro = quadros[indice]
        imagem.set_data(quadro.grade)
        c = quadro.contagem
        eixo.set_title(f"Geração {quadro.geracao}\n"
                       f"Ignorantes: {c[0]} | Espalhadores: {c[1]} | Inativos: {c[2]}", fontsize=11)
        return (imagem,)

    atualizar(0)
    animacao = FuncAnimation(figura, atualizar, frames=range(len(quadros)),
                             interval=1000 / fps, blit=False, repeat=True)
    return figura, animacao, atualizar


def exportar(quadros, raiz, *, fps=4, configuracao="", parametros=None):
    """Cria diretório exclusivo, PNGs inicial/final, GIF e descrição da execução."""
    if not quadros or fps <= 0:
        raise ValueError("São necessários quadros e fps positivo.")
    nome = "visualizacao_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ_") + uuid4().hex[:8]
    pasta = Path(raiz) / nome
    pasta.mkdir(parents=True, exist_ok=False)
    figura, animacao, atualizar = criar_animacao(quadros, fps=fps, configuracao=configuracao)
    try:
        atualizar(0)
        figura.savefig(pasta / "inicial.png", dpi=120)
        atualizar(len(quadros) - 1)
        figura.savefig(pasta / "final.png", dpi=120)
        animacao.save(pasta / "propagacao.gif", writer=PillowWriter(fps=fps), dpi=100)
    finally:
        figura.clear()
    metadata = {
        "implementacao": "sequencial de referência",
        "uso": "Visualização independente; renderização e exportação não são benchmarks.",
        "parametros": parametros or {}, "fps": fps,
        "geracoes_executadas": quadros[-1].geracao,
        "quadros": [{"geracao": q.geracao, "contagem": q.contagem} for q in quadros],
    }
    (pasta / "visualization.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return pasta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--linhas", type=int, default=20)
    parser.add_argument("--colunas", type=int, default=20)
    parser.add_argument("--geracoes", type=int, default=15)
    parser.add_argument("--espalhadores", type=float, default=0.05, help="Fração inicial: 0.05 = 5%%.")
    parser.add_argument("--limiar", type=int, default=2)
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("--fps", type=int, default=4)
    parser.add_argument("--mostrar", action="store_true", help="Também abre animação interativa; requer backend gráfico.")
    parser.add_argument("--saida", type=Path, default=Path(__file__).resolve().parent / "results")
    args = parser.parse_args(argv)
    if args.linhas < 1 or args.colunas < 1 or args.geracoes < 0 or args.fps < 1:
        parser.error("Dimensões e fps devem ser positivos; gerações não negativas.")
    if not 0 <= args.espalhadores <= 1 or not 0 <= args.limiar <= 8:
        parser.error("Fração inicial deve estar entre 0 e 1; limiar entre 0 e 8.")
    grade = criar_grade(args.linhas, args.colunas, args.espalhadores, args.semente)
    quadros = gerar_trajetoria(grade, args.geracoes, args.limiar)
    descricao = (f"Matriz {args.linhas}×{args.colunas}; limite={args.geracoes}; "
                 f"fração inicial={args.espalhadores}; limiar={args.limiar}; semente={args.semente}")
    parametros = {k: v for k, v in vars(args).items() if k not in ("saida", "mostrar")}
    pasta = exportar(quadros, args.saida, fps=args.fps, configuracao=descricao, parametros=parametros)
    print(f"Referência sequencial: {quadros[-1].geracao} gerações executadas.")
    print(f"Arquivos: {pasta}")
    if args.mostrar:
        import matplotlib.pyplot as plt
        figura = plt.figure(figsize=(7, 7), layout="constrained")
        _, animacao, _ = criar_animacao(quadros, fps=args.fps, configuracao=descricao, figura=figura)
        plt.show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
