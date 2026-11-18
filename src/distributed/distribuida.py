"""Interface do grupo: simular(config) usa processos locais conectados por TCP."""

from .server import Config, ResultadoDistribuido, executar_servidor


def simular(config: Config) -> ResultadoDistribuido:
    """Escolhe uma porta livre e inicia/encerra config.num_processos workers.

    Não exige terminais manuais e não usa memória compartilhada no cálculo.
    Para workers em outras máquinas, use a CLI de server.py e worker.py.
    """
    return executar_servidor(config, porta=0, automaticos=True)
