"""``simular(config) -> Resultado`` da versão distribuída, com workers locais via TCP."""

from .server import Config, ResultadoDistribuido, executar_servidor


def simular(config: Config) -> ResultadoDistribuido:
    """Inicia ``config.num_processos`` workers numa porta livre; para várias máquinas, use as CLIs."""
    return executar_servidor(config, porta=0, automaticos=True)
