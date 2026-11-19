"""Impede que o Windows 11 rebaixe o processo para os núcleos de economia (EcoQoS).

O rebaixamento distorce os benchmarks (ver "Achado 2" em docs/versao-paralela.md).
O pedido não é herdado: cada processo precisa chamar a função.
"""

from __future__ import annotations

import sys

_PROCESS_POWER_THROTTLING = 4  # valor de PROCESS_INFORMATION_CLASS
_VERSAO = 1  # PROCESS_POWER_THROTTLING_CURRENT_VERSION
_EXECUTION_SPEED = 0x1  # PROCESS_POWER_THROTTLING_EXECUTION_SPEED


def desligar_economia_de_energia() -> bool:
    """Devolve True se o Windows aceitou o pedido; False fora do Windows ou se falhar."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class _Estado(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.ULONG),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetProcessInformation.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        kernel32.SetProcessInformation.restype = wintypes.BOOL

        # StateMask = 0: sem economia de energia.
        estado = _Estado(_VERSAO, _EXECUTION_SPEED, 0)
        return bool(
            kernel32.SetProcessInformation(
                kernel32.GetCurrentProcess(),
                _PROCESS_POWER_THROTTLING,
                ctypes.byref(estado),
                ctypes.sizeof(estado),
            )
        )
    except (AttributeError, OSError):  # Windows sem essa API
        return False
