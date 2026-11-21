"""Extensões do modelo: semântica de cada regra e equivalência entre as versões."""

import random
import statistics
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from common import core  # noqa: E402
from common.core import ESPALHADOR, IGNORANTE, INATIVO, Config  # noqa: E402
from common.modelo import (  # noqa: E402
    BOT, COMUM, INFLUENCIADOR, Modelo, criar_modelo, criar_tipos, linha_estendida_otimizada,
    linha_estendida_referencia, obter_kernel_estendido, sorteio,
)
from distributed.distribuida import simular as simular_distribuida  # noqa: E402
from parallel.paralela import simular as simular_paralela  # noqa: E402

EXTENSOES = {
    "probabilidade": dict(probabilidade_convencimento=0.35),
    "influenciadores": dict(percentual_influenciadores=0.06, peso_influenciador=4),
    "bots": dict(percentual_bots=0.02),
    "todas": dict(probabilidade_convencimento=0.5, percentual_influenciadores=0.04,
                  peso_influenciador=3, percentual_bots=0.01),
}


def config_com(extensoes, **campos):
    base = dict(linhas=24, colunas=21, geracoes=25, percentual_espalhadores=0.04,
                limiar_convencimento=1)
    base.update(campos)
    return Config(**base, **extensoes)


def uma_geracao(grade, limiar, modelo, tipos=None, geracao=1, kernel="referencia"):
    linhas = [bytes(linha) for linha in grade]
    linhas_tipos = None if tipos is None else [bytes(linha) for linha in tipos]
    novas = core.calcular_linhas(linhas, 0, len(linhas), limiar, kernel, modelo=modelo,
                                 tipos=linhas_tipos, geracao=geracao)
    return [list(linha) for linha in novas]


class TestSorteio(unittest.TestCase):
    def test_deterministico_e_no_intervalo(self):
        valores = [sorteio(7, g, i, j) for g in range(3) for i in range(40) for j in range(40)]
        self.assertEqual(valores, [sorteio(7, g, i, j)
                                   for g in range(3) for i in range(40) for j in range(40)])
        self.assertTrue(all(0 <= v < 1 for v in valores))
        self.assertAlmostEqual(statistics.mean(valores), 0.5, delta=0.02)

    def test_muda_com_cada_coordenada(self):
        base = sorteio(1, 2, 3, 4)
        for outro in (sorteio(9, 2, 3, 4), sorteio(1, 9, 3, 4),
                      sorteio(1, 2, 9, 4), sorteio(1, 2, 3, 9)):
            self.assertNotEqual(base, outro)


class TestParametros(unittest.TestCase):
    def test_padroes_desligam_as_extensoes(self):
        self.assertIsNone(criar_modelo(1.0, 0.0, 3, 0.0, 42))
        self.assertIsNone(criar_tipos(10, 10, 0.0, 0.0, 42))

    def test_valores_invalidos(self):
        for campos in (dict(probabilidade_convencimento=0), dict(probabilidade_convencimento=1.5),
                       dict(percentual_influenciadores=-0.1), dict(percentual_bots=2),
                       dict(peso_influenciador=0)):
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                core.simular(config_com(campos))

    def test_tipos_reprodutiveis_e_sem_alterar_a_grade_inicial(self):
        tipos = criar_tipos(30, 30, 0.1, 0.05, semente=3)
        self.assertEqual(tipos, criar_tipos(30, 30, 0.1, 0.05, semente=3))
        self.assertNotEqual(tipos, criar_tipos(30, 30, 0.1, 0.05, semente=4))
        contagem = sum(linha.count(INFLUENCIADOR) + linha.count(BOT) for linha in tipos)
        self.assertTrue(0 < contagem <= int(900 * 0.1) + int(900 * 0.05))
        sem = core.preparar_inicio(Config(linhas=30, colunas=30, semente=3))[0]
        com = core.preparar_inicio(Config(linhas=30, colunas=30, semente=3,
                                          percentual_influenciadores=0.1))[0]
        self.assertEqual(sem, com)  # influenciadores usam outro gerador


class TestSemantica(unittest.TestCase):
    def test_probabilidade_um_reproduz_o_modelo_original(self):
        sorteador = random.Random(5)
        grade = [[sorteador.choice((0, 0, 1, 2)) for _ in range(13)] for _ in range(11)]
        for limiar in range(5):
            with self.subTest(limiar=limiar):
                self.assertEqual(uma_geracao(grade, limiar, Modelo()),
                                 core.proxima_geracao(grade, limiar))

    def test_taxa_de_convencimento_segue_a_probabilidade(self):
        # Cada ignorante tem exatamente um vizinho espalhador.
        grade = [[ESPALHADOR if j % 3 == 0 else IGNORANTE for j in range(300)] for _ in range(1)]
        for p in (0.2, 0.7):
            nova = uma_geracao(grade, 1, Modelo(probabilidade=p))
            ignorantes = [j for j in range(300) if j % 3 != 0]
            taxa = sum(nova[0][j] == ESPALHADOR for j in ignorantes) / len(ignorantes)
            self.assertAlmostEqual(taxa, p, delta=0.08)

    def test_mais_exposicoes_aumentam_a_chance(self):
        # 1 - (1 - p)^k com p = 0,3: dois vizinhos dão 51%, três dão 65,7%.
        duas = [[ESPALHADOR, IGNORANTE] * 200]
        tres = [[ESPALHADOR] * 400, [IGNORANTE] * 400]
        modelo = Modelo(probabilidade=0.3)
        taxa_duas = statistics.mean(
            c == ESPALHADOR for c in uma_geracao(duas, 1, modelo)[0][1:-1:2])
        taxa_tres = statistics.mean(
            c == ESPALHADOR for c in uma_geracao(tres, 1, modelo)[1][1:-1])
        self.assertAlmostEqual(taxa_duas, 1 - 0.7 ** 2, delta=0.07)
        self.assertAlmostEqual(taxa_tres, 1 - 0.7 ** 3, delta=0.07)

    def test_influenciador_vale_peso_exposicoes(self):
        grade = [[ESPALHADOR, IGNORANTE, IGNORANTE]]
        tipos = [[INFLUENCIADOR, COMUM, COMUM]]
        self.assertEqual(uma_geracao(grade, 3, Modelo(peso_influenciador=3), tipos)[0][1],
                         ESPALHADOR)
        self.assertEqual(uma_geracao(grade, 3, Modelo(peso_influenciador=2), tipos)[0][1],
                         IGNORANTE)
        # Influenciador que não está espalhando não pesa nada.
        self.assertEqual(uma_geracao([[INATIVO, IGNORANTE, IGNORANTE]], 1,
                                     Modelo(peso_influenciador=5), tipos)[0][1], IGNORANTE)

    def test_bots_nunca_ficam_inativos(self):
        config = config_com(dict(percentual_bots=0.03), geracoes=15, limiar_convencimento=2)
        grade, tipos, modelo = core.preparar_inicio(config)
        bots = [(i, j) for i, linha in enumerate(tipos) for j, t in enumerate(linha) if t == BOT]
        self.assertTrue(bots)
        self.assertTrue(all(grade[i][j] == ESPALHADOR for i, j in bots))
        geracoes = []
        core.evoluir(grade, 15, 2, ao_final_de_geracao=lambda g, atual, _: geracoes.append(atual),
                     modelo=modelo, tipos=tipos)
        self.assertEqual(len(geracoes), 15)  # com bots sempre há espalhadores
        for atual in geracoes:
            self.assertTrue(all(atual[i][j] == ESPALHADOR for i, j in bots))

    def test_kernels_estendidos_concordam(self):
        sorteador = random.Random(11)
        for _ in range(30):
            linhas, colunas = sorteador.randint(1, 9), sorteador.randint(1, 12)
            grade = [[sorteador.choice((0, 0, 0, 1, 2)) for _ in range(colunas)]
                     for _ in range(linhas)]
            tipos = [[sorteador.choice((0, 0, 0, 1, 2)) for _ in range(colunas)]
                     for _ in range(linhas)]
            modelo = Modelo(sorteador.choice((0.25, 0.6, 1.0)), sorteador.randint(1, 4),
                            sorteador.randint(0, 99))
            limiar = sorteador.randint(0, 5)
            with self.subTest(grade=grade, tipos=tipos, modelo=modelo, limiar=limiar):
                self.assertEqual(
                    uma_geracao(grade, limiar, modelo, tipos, 3, "referencia"),
                    uma_geracao(grade, limiar, modelo, tipos, 3, "otimizado"))

    def test_kernel_personalizado_nao_suporta_extensoes(self):
        self.assertIs(obter_kernel_estendido("otimizado"), linha_estendida_otimizada)
        self.assertIs(obter_kernel_estendido(linha_estendida_referencia), linha_estendida_referencia)
        with self.assertRaises(ValueError):
            obter_kernel_estendido(lambda acima, linha, abaixo, limiar: linha)


class TestEquivalenciaDasVersoes(unittest.TestCase):
    """O resultado não pode depender de como a matriz é dividida."""

    def conferir(self, simular, config, **opcoes):
        esperado = core.simular(config)
        obtido = simular(config, **opcoes)
        self.assertEqual(obtido.historico, esperado.historico)
        self.assertEqual(obtido.hash_grade, esperado.hash_grade)

    def test_paralela_threads(self):
        for nome, extensoes in EXTENSOES.items():
            for kernel in ("referencia", "otimizado"):
                for workers in (1, 2, 5):
                    with self.subTest(extensao=nome, kernel=kernel, workers=workers):
                        config = config_com(extensoes, kernel=kernel, num_threads=workers)
                        for divisao in ("estatica", "dinamica"):
                            self.conferir(simular_paralela, config, divisao=divisao)

    def test_paralela_processos(self):
        for nome, extensoes in EXTENSOES.items():
            with self.subTest(extensao=nome):
                self.conferir(simular_paralela, config_com(extensoes, num_processos=3,
                                                           kernel="otimizado"),
                              backend="processos")

    def test_distribuida(self):
        for nome, extensoes in EXTENSOES.items():
            for workers in (1, 3, 30):  # 30 > número de linhas
                with self.subTest(extensao=nome, workers=workers):
                    self.conferir(simular_distribuida,
                                  config_com(extensoes, num_processos=workers, kernel="otimizado"))


if __name__ == "__main__":
    unittest.main()
