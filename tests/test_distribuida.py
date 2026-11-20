"""Testes de TCP, halos e execução distribuída, sem modificar as outras versões."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from common.core import Config, simular as sequencial
from distributed.distribuida import simular
from distributed import protocol
from distributed.server import executar_servidor
from distributed.worker import processar_tarefas
from common.core import proxima_geracao


def nucleo_proxima(grade, geracoes, limiar):
    """Laço sequencial do núcleo com a mesma parada do original."""
    for _ in range(geracoes):
        grade = proxima_geracao(grade, limiar)
        if not any(1 in linha for linha in grade):
            break
    return grade


@contextmanager
def par_de_sockets():
    origem, destino = socket.socketpair()
    with origem, destino:
        origem.settimeout(5)
        destino.settimeout(5)
        yield origem, destino


class TestProtocoloDistribuido(unittest.TestCase):
    def test_fragmentacao_e_mensagens_consecutivas_com_utf8(self):
        class Fragmentado:
            def __init__(self, conexao):
                self.conexao = conexao

            def recv(self, quantidade):
                return self.conexao.recv(min(quantidade, 2))

        with par_de_sockets() as (origem, destino):
            protocol.enviar_mensagem(origem, {"mensagem": "ação"})
            protocol.enviar_mensagem(origem, {"segunda": True})
            self.assertEqual(protocol.receber_mensagem(Fragmentado(destino)), {"mensagem": "ação"})
            self.assertEqual(protocol.receber_mensagem(destino), {"segunda": True})

    def test_grade_maior_que_limite_em_lotes(self):
        # Mais de um MiB até na representação compacta: exige múltiplos quadros.
        grade = [[i % 3] * 1200 for i in range(1000)]
        self.assertGreater(len(grade) * len(grade[0]), protocol.LIMITE_MENSAGEM)
        with par_de_sockets() as (origem, destino):
            erros = []

            def enviar():
                try:
                    protocol.enviar_grade(origem, grade, 1200)
                except Exception as erro:
                    erros.append(erro)

            thread = threading.Thread(target=enviar, daemon=True)
            thread.start()
            recebida = protocol.receber_grade(destino, 1000, 1200)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(erros, [])
            self.assertEqual(recebida, grade)

    def test_rejeita_quadros_invalidos_e_desconexao_parcial(self):
        casos = [
            (struct.pack("!I", 0), ValueError),
            (struct.pack("!I", protocol.LIMITE_MENSAGEM + 1), ValueError),
            (struct.pack("!I", 1) + b"{", ValueError),
            (struct.pack("!I", 1) + bytes([255]), ValueError),
            (struct.pack("!I", 2) + b"[]", ValueError),
            (bytes([0, 0]), ConnectionError),
            (struct.pack("!I", 10) + b"{}", ConnectionError),
        ]
        for dados, erro in casos:
            with self.subTest(dados=dados), par_de_sockets() as (origem, destino):
                origem.sendall(dados)
                origem.shutdown(socket.SHUT_WR)
                with self.assertRaises(erro):
                    protocol.receber_mensagem(destino)

    def test_rejeita_estados_invalidos_no_lote(self):
        with par_de_sockets() as (origem, destino):
            protocol.enviar_mensagem(origem, {"tipo": "grade", "linhas": 1, "colunas": 3})
            protocol.enviar_mensagem(origem, {"tipo": "dados_grade", "dados": "019"})
            with self.assertRaises(ValueError):
                protocol.receber_grade(destino, 1, 3)

    def test_worker_rejeita_geracao_fora_de_ordem(self):
        with par_de_sockets() as (servidor, worker):
            erros = []

            def executar():
                try:
                    processar_tarefas(worker)
                except Exception as erro:
                    erros.append(erro)

            thread = threading.Thread(target=executar, daemon=True)
            thread.start()
            protocol.receber_tipo(servidor, "pronto")
            protocol.enviar_mensagem(servidor, {
                "tipo": "iniciar", "linhas": 1, "colunas": 3, "limiar": 1,
                "tem_acima": False, "tem_abaixo": False,
            })
            protocol.enviar_grade(servidor, [[0, 1, 0]], 3)
            protocol.receber_tipo(servidor, "estado")
            protocol.enviar_mensagem(servidor, {
                "tipo": "calcular", "geracao": 2, "acima": None, "abaixo": None,
            })
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(erros), 1)
            self.assertIsInstance(erros[0], ValueError)


class TestSimulacaoDistribuida(unittest.TestCase):
    def test_zero_geracoes_nao_inicia_workers_e_preserva_grade(self):
        config = Config(linhas=5, colunas=7, geracoes=0, num_processos=3)
        obtido, esperado = simular(config), sequencial(config)
        self.assertEqual(obtido.grade_final, esperado.grade_final)
        self.assertEqual(obtido.historico, [])
        self.assertEqual(obtido.metricas["workers"], [])

    def test_apenas_halos_durante_geracoes_e_metricas_serializaveis(self):
        config = Config(linhas=17, colunas=23, geracoes=6, percentual_espalhadores=0.2,
                        limiar_convencimento=1, num_processos=3)
        resultado = simular(config)
        esperado = sequencial(config)
        self.assertEqual(resultado.grade_final, esperado.grade_final)
        self.assertEqual(resultado.historico, esperado.historico)
        self.assertEqual(resultado.metricas["celulas_halo_enviadas"],
                         2 * (config.num_processos - 1) * config.colunas * resultado.geracoes_executadas)
        self.assertEqual(len(resultado.metricas["workers"]), 3)
        self.assertGreaterEqual(resultado.metricas["total_s"], resultado.tempo_s)
        self.assertEqual(json.loads(json.dumps(resultado.para_dict()))["hash_grade"], esperado.hash_grade)
        self.assertNotIn("grade_final", resultado.para_dict())

    def test_configuracoes_invalidas(self):
        for campo, valor in (("num_processos", 0), ("linhas", 0), ("colunas", -1),
                             ("geracoes", -1), ("percentual_espalhadores", 1.1)):
            with self.subTest(campo=campo):
                config = Config()
                setattr(config, campo, valor)
                with self.assertRaises(ValueError):
                    simular(config)

    def test_kernel_e_grade_inicial_externa(self):
        grade = [[0, 1, 0, 0], [1, 0, 2, 0], [0, 0, 0, 1], [0, 1, 0, 0], [0, 0, 0, 0]]
        for kernel in ("referencia", "otimizado"):
            with self.subTest(kernel=kernel):
                config = Config(linhas=5, colunas=4, geracoes=6, limiar_convencimento=1,
                                num_processos=2, kernel=kernel)
                resultado = executar_servidor(config, porta=0, automaticos=True,
                                              grade_inicial=grade)
                esperado = nucleo_proxima(grade, 6, 1)
                self.assertEqual(resultado.grade_final, esperado)
                self.assertEqual(resultado.config.kernel, kernel)
        with self.assertRaises(ValueError):  # dimensões diferentes de config
            executar_servidor(Config(linhas=4, colunas=4, num_processos=1), porta=0,
                              automaticos=True, grade_inicial=grade)
        with self.assertRaises(ValueError):
            simular(Config(kernel="gpu"))

    def test_worker_rejeita_kernel_desconhecido(self):
        with par_de_sockets() as (servidor, worker):
            erros = []

            def executar():
                try:
                    processar_tarefas(worker)
                except Exception as erro:
                    erros.append(erro)

            thread = threading.Thread(target=executar, daemon=True)
            thread.start()
            self.assertEqual(protocol.receber_tipo(servidor, "pronto")["protocolo"], 2)
            protocol.enviar_mensagem(servidor, {
                "tipo": "iniciar", "linhas": 1, "colunas": 3, "limiar": 1, "kernel": "gpu",
                "tem_acima": False, "tem_abaixo": False,
            })
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(erros), 1)
            self.assertIsInstance(erros[0], ValueError)

    def test_timeout_sem_workers_fecha_porta(self):
        with socket.socket() as reserva:
            reserva.bind(("127.0.0.1", 0))
            porta = reserva.getsockname()[1]
        with self.assertRaises(socket.timeout):
            executar_servidor(Config(num_processos=1), porta=porta, tempo_limite=0.1)
        with socket.socket() as livre:
            livre.bind(("127.0.0.1", porta))

    def test_cli_manual_com_dois_processos_workers(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        with tempfile.TemporaryDirectory() as temporario:
            saida = Path(temporario) / "resultado.json"
            servidor = subprocess.Popen(
                [sys.executable, "-B", str(SRC / "distributed/server.py"),
                 "--port", "0", "--workers", "2", "-l", "11", "-c", "13",
                 "-g", "4", "-p", "0.2", "-t", "1", "--saida", str(saida), "--incluir-grade"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", env=env,
            )
            linhas = queue.Queue()
            log = []
            workers = []

            def coletar():
                for linha in servidor.stdout:
                    log.append(linha)
                    linhas.put(linha)

            leitor = threading.Thread(target=coletar, daemon=True)
            leitor.start()
            try:
                primeira = linhas.get(timeout=10)
                porta = re.search(r"127[.]0[.]0[.]1:(\d+)", primeira).group(1)
                for _ in range(2):
                    workers.append(subprocess.Popen(
                        [sys.executable, "-B", str(SRC / "distributed/worker.py"), "--port", porta,
                         "--silencioso"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env,
                    ))
                self.assertEqual(servidor.wait(timeout=15), 0, "".join(log))
                for worker in workers:
                    _, erros = worker.communicate(timeout=5)
                    self.assertEqual(worker.returncode, 0, erros)
                dados = json.loads(saida.read_text(encoding="utf-8"))
                esperado = sequencial(Config(linhas=11, colunas=13, geracoes=4,
                                            percentual_espalhadores=0.2, limiar_convencimento=1))
                self.assertEqual(dados["grade_final"], esperado.grade_final)
                self.assertEqual(dados["historico"], esperado.historico)
            finally:
                for processo in [servidor] + workers:
                    if processo.poll() is None:
                        processo.terminate()
                        processo.wait(timeout=5)
                leitor.join(timeout=2)
                servidor.stdout.close()
                for worker in workers:
                    if worker.stderr:
                        worker.stderr.close()


if __name__ == "__main__":
    unittest.main()
