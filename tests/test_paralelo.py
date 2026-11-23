"""A versão paralela deve dar exatamente o resultado do código original."""

import random
import sys
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
for pasta in ("sequential", "parallel"):
    caminho = str(RAIZ / "src" / pasta)
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

import fake_news as professor  # noqa: E402
import regras  # noqa: E402
from fake_news_paralelo import (  # noqa: E402
    dividir_linhas,
    simular_paralelo,
    tamanho_pedaco_automatico,
)

TAMANHOS = [(1, 1), (1, 7), (7, 1), (2, 2), (3, 5), (16, 16), (23, 17)]


def grade_aleatoria(linhas, colunas, semente):
    """Grade com os três estados misturados (testa também espalhador -> inativo)."""
    sorteio = random.Random(semente)
    return [
        [sorteio.choice((0, 0, 0, 1, 1, 2)) for _ in range(colunas)]
        for _ in range(linhas)
    ]


def trajetoria_do_professor(grade, geracoes, limiar):
    """O laço de executar_simulacao do professor, sem os prints."""
    historico = []
    for _ in range(geracoes):
        grade = professor.proxima_geracao(grade, limiar)
        contagem = professor.contar_estados(grade)
        historico.append(
            (
                contagem[professor.IGNORANTE],
                contagem[professor.ESPALHADOR],
                contagem[professor.INATIVO],
            )
        )
        if contagem[professor.ESPALHADOR] == 0:
            break
    return grade, historico


def aplicar_kernel(kernel, grade, limiar):
    linhas = [bytes(linha) for linha in grade]
    total = len(linhas)
    return [
        list(
            kernel(
                linhas[i - 1] if i > 0 else None,
                linhas[i],
                linhas[i + 1] if i + 1 < total else None,
                limiar,
            )
        )
        for i in range(total)
    ]


def kernel_que_falha(acima, linha, abaixo, limiar):
    """Falha só na linha marcada com INATIVO na coluna 0 (um único worker)."""
    if linha[0] == regras.INATIVO:
        raise ValueError("falha proposital")
    return regras.linha_otimizada(acima, linha, abaixo, limiar)


class TestRegras(unittest.TestCase):
    def test_codigos_de_estado_iguais_aos_do_professor(self):
        self.assertEqual(
            (regras.IGNORANTE, regras.ESPALHADOR, regras.INATIVO),
            (professor.IGNORANTE, professor.ESPALHADOR, professor.INATIVO),
        )

    def test_kernels_iguais_a_proxima_geracao_do_professor(self):
        for nome, kernel in regras.KERNELS.items():
            for linhas, colunas in TAMANHOS:
                grade = grade_aleatoria(linhas, colunas, semente=linhas * 100 + colunas)
                for limiar in range(10):  # 0 a 9 cobre "sempre" e "nunca" convence
                    with self.subTest(kernel=nome, tamanho=(linhas, colunas), limiar=limiar):
                        self.assertEqual(
                            aplicar_kernel(kernel, grade, limiar),
                            professor.proxima_geracao(grade, limiar),
                        )


class TestDivisao(unittest.TestCase):
    def test_blocos_cobrem_cada_linha_uma_vez_e_sao_equilibrados(self):
        for total in (0, 1, 5, 16, 101):
            for partes in (1, 2, 3, 7, 16, 200):
                blocos = dividir_linhas(total, partes)
                with self.subTest(total=total, partes=partes):
                    self.assertEqual(len(blocos), partes)
                    self.assertEqual(blocos[0][0], 0)
                    self.assertEqual(blocos[-1][1], total)
                    for (_, fim), (inicio, _) in zip(blocos, blocos[1:]):
                        self.assertEqual(fim, inicio)
                    tamanhos = [fim - inicio for inicio, fim in blocos]
                    self.assertLessEqual(max(tamanhos) - min(tamanhos), 1)

    def test_zero_workers_e_invalido(self):
        with self.assertRaises(ValueError):
            dividir_linhas(10, 0)

    def test_pedaco_automatico_da_varios_pedacos_por_worker(self):
        self.assertEqual(tamanho_pedaco_automatico(1000, 8), 15)
        self.assertEqual(tamanho_pedaco_automatico(5, 16), 1)


class TestEquivalenciaThreads(unittest.TestCase):
    backend = "threads"
    workers_testados = (1, 2, 3, 4, 7, 16)
    kernels_testados = ("otimizado", "referencia")
    limiares = (0, 1, 2, 3, 4)

    def conferir(self, grade, geracoes, limiar, workers, kernel,
                 divisao="estatica", pedaco=None):
        grade_esperada, historico_esperado = trajetoria_do_professor(grade, geracoes, limiar)
        resultado = simular_paralelo(grade, geracoes, limiar, workers, self.backend,
                                     kernel, divisao, pedaco)
        self.assertEqual(resultado.historico, historico_esperado)
        self.assertEqual(resultado.grade_final, grade_esperada)
        self.assertEqual(len(resultado.tempo_calculo_s), workers)
        self.assertGreaterEqual(resultado.desbalanceamento, 0.999)
        self.assertGreaterEqual(resultado.tempo_sincronizacao_s, 0.0)

    def test_mesma_trajetoria_que_o_professor(self):
        grades = {
            "criar_grade 40x30": professor.criar_grade(40, 30, 0.05, semente=7),
            "aleatória 19x23": grade_aleatoria(19, 23, semente=3),
        }
        for nome_grade, grade in grades.items():
            for kernel in self.kernels_testados:
                for divisao in ("estatica", "dinamica"):
                    for workers in self.workers_testados:
                        for limiar in self.limiares:
                            with self.subTest(grade=nome_grade, kernel=kernel,
                                              divisao=divisao, workers=workers,
                                              limiar=limiar):
                                self.conferir(grade, 30, limiar, workers, kernel, divisao)

    def test_divisao_dinamica_com_varios_tamanhos_de_pedaco(self):
        grade = grade_aleatoria(29, 11, semente=5)
        for pedaco in (1, 2, 7, 29, 1000):
            for workers in (1, 3, 8):
                with self.subTest(pedaco=pedaco, workers=workers):
                    self.conferir(grade, 20, 2, workers, "otimizado", "dinamica", pedaco)

    def test_mais_workers_que_linhas(self):
        for divisao in ("estatica", "dinamica"):
            with self.subTest(divisao=divisao):
                self.conferir(grade_aleatoria(3, 10, semente=1), 10, 2, 8,
                              "otimizado", divisao)

    def test_zero_geracoes_devolve_a_grade_inicial(self):
        grade = grade_aleatoria(5, 5, semente=2)
        resultado = simular_paralelo(grade, 0, 2, 2, self.backend)
        self.assertEqual(resultado.historico, [])
        self.assertEqual(resultado.grade_final, grade)

    def test_para_na_primeira_geracao_sem_espalhadores(self):
        grade = [[professor.IGNORANTE] * 6 for _ in range(6)]
        resultado = simular_paralelo(grade, 50, 1, 3, self.backend)
        self.assertEqual(resultado.historico, [(36, 0, 0)])

    def test_falha_num_worker_vira_erro_e_nao_trava(self):
        grade = [[professor.IGNORANTE] * 8 for _ in range(16)]
        grade[7][0] = regras.INATIVO  # só a linha 7 faz o kernel falhar
        def rodar(divisao, erros):
            try:
                simular_paralelo(grade, 5, 2, 4, self.backend, kernel_que_falha, divisao)
            except RuntimeError as erro:
                erros.append(erro)

        for divisao in ("estatica", "dinamica"):
            erros = []
            execucao = threading.Thread(target=rodar, args=(divisao, erros), daemon=True)
            execucao.start()
            execucao.join(timeout=60)
            with self.subTest(divisao=divisao):
                self.assertFalse(execucao.is_alive(), "a simulação travou depois da falha")
                self.assertEqual(len(erros), 1)

    def test_parametros_invalidos(self):
        with self.assertRaises(ValueError):
            simular_paralelo([[0, 1], [0]], 1, 2, 2, self.backend)
        with self.assertRaises(ValueError):
            simular_paralelo([[0]], 1, 2, 2, "gpu")
        with self.assertRaises(ValueError):
            simular_paralelo([[0]], 1, 2, 0, self.backend)
        with self.assertRaises(ValueError):
            simular_paralelo([[0]], 1, 2, 1, self.backend, divisao="aleatoria")
        with self.assertRaises(ValueError):
            simular_paralelo([[0]], 1, 2, 1, self.backend, divisao="dinamica", pedaco=0)


class TestEquivalenciaProcessos(TestEquivalenciaThreads):
    """Mesmos testes com processos (menos casos: criar processo é caro)."""

    backend = "processos"
    workers_testados = (1, 3, 4)
    kernels_testados = ("otimizado",)
    limiares = (2, 3)

    def test_divisao_dinamica_com_varios_tamanhos_de_pedaco(self):
        grade = grade_aleatoria(29, 11, semente=5)
        for pedaco in (1, 7):
            with self.subTest(pedaco=pedaco):
                self.conferir(grade, 20, 2, 3, "otimizado", "dinamica", pedaco)


if __name__ == "__main__":
    unittest.main()
