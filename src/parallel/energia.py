"""Evita que o Windows 11 rebaixe o processo para o modo de economia (EcoQoS).

Problema medido no notebook do Pedro (i5-13450HX: 6 núcleos P + 4 núcleos E):
um processo de console sem janela em primeiro plano é classificado como
"segundo plano" depois de cerca de 3 segundos e passa a rodar nos núcleos de
eficiência (E-cores). O mesmo código fica até 2x mais lento. Processos recém-
criados escapam nos primeiros segundos, então uma comparação entre o processo
principal (sequencial, threads) e processos filhos fica distorcida.

``desligar_economia_de_energia()`` pede ao Windows para não aplicar essa
economia ao processo atual (SetProcessInformation com ProcessPowerThrottling,
documentado pela Microsoft). Cada processo precisa chamar a função: o pedido
não passa para os filhos. Fora do Windows não faz nada.

Vale para qualquer benchmark do grupo (sequencial, paralelo e distribuído).
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

        # ControlMask diz que vamos controlar a velocidade de execução;
        # StateMask = 0 diz "sem economia" (QoS alto).
        estado = _Estado(_VERSAO, _EXECUTION_SPEED, 0)
        return bool(
            kernel32.SetProcessInformation(
                kernel32.GetCurrentProcess(),
                _PROCESS_POWER_THROTTLING,
                ctypes.byref(estado),
                ctypes.sizeof(estado),
            )
        )
    except (AttributeError, OSError):  # Windows antigo sem essa API
        return False
