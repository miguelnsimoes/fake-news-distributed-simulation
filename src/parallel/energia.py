"""Compatibilidade: o módulo fica em ``src/common/energia.py``."""

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1])
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from common.energia import desligar_economia_de_energia  # noqa: E402,F401
