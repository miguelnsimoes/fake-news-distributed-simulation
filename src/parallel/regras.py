"""Compatibilidade: os kernels ficam em ``src/common/kernels.py``."""

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1])
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from common.estados import ESPALHADOR, IGNORANTE, INATIVO  # noqa: E402,F401
from common.kernels import (  # noqa: E402,F401
    KERNELS,
    Kernel,
    linha_otimizada,
    linha_referencia,
    obter_kernel,
)
