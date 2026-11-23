"""Opções de linha de comando das extensões do modelo, iguais nas três versões."""

import argparse

from .modelo import PESO_INFLUENCIADOR_PADRAO


def adicionar_extensoes(parser: argparse.ArgumentParser) -> None:
    grupo = parser.add_argument_group("extensões do modelo (docs/extensoes-modelo.md)")
    grupo.add_argument("--probabilidade", type=float, default=1.0,
                       help="Chance de cada exposição convencer (1 = modelo original).")
    grupo.add_argument("--influenciadores", type=float, default=0.0,
                       help="Fração da população que é influenciadora (0.01 = 1%%).")
    grupo.add_argument("--peso-influenciador", type=int, default=PESO_INFLUENCIADOR_PADRAO,
                       help="Quantas exposições vale um influenciador espalhando.")
    grupo.add_argument("--bots", type=float, default=0.0,
                       help="Fração da população que é bot (espalha sempre).")


def extensoes_de(args: argparse.Namespace) -> dict:
    """Campos de ``Config`` correspondentes às opções de ``adicionar_extensoes``."""
    return {
        "probabilidade_convencimento": args.probabilidade,
        "percentual_influenciadores": args.influenciadores,
        "peso_influenciador": args.peso_influenciador,
        "percentual_bots": args.bots,
    }
