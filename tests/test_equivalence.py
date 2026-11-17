"""
Testes de equivalência da simulação de Fake News.

Objetivo: garantir que sequencial, paralela e distribuída produzem EXATAMENTE
os mesmos resultados (mesmo histórico por geração e mesma grade final).

O gabarito é o código ORIGINAL do professor, que fica intacto em
src/sequential/fake_news.py (não há cópia: se alguém alterar o original,
os testes passam a cobrar a mudança).

Como rodar (a partir da raiz do repositório):
    python -m unittest discover -s tests -v

Camadas de teste:
  1. src/common/core.py (refatorado)  == código original do professor
  2. Blocos de construção usados pelas versões paralelas (faixas e halo)
  3. Versões paralela e distribuída == sequencial
     (rodam automaticamente quando os módulos listados em MODULO_PARALELO e
      MODULO_DISTRIBUIDO existirem e expuserem `simular(config)`; senão são puladas)
"""

import importlib
import os
import sys
import unittest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(RAIZ, "src"))

from common import core as nucleo          # núcleo refatorado
from sequential import fake_news as ref    # original do professor (gabarito)

# Módulos que o Pedro e o Miguel devem criar, cada um expondo simular(config).
# Se escolherem outros nomes, é só ajustar aqui.
MODULO_PARALELO = "parallel.paralela"
MODULO_DISTRIBUIDO = "distributed.distribuida"


def simular_referencia(linhas, colunas, geracoes, percentual, limiar, semente=42):
    """
    Reproduz o laço de executar_simulacao() do original usando as funções do
    próprio original. Devolve (historico_de_tuplas, grade_final, geracoes_executadas).
    """
    grade = ref.criar_grade(linhas, colunas, percentual, semente)
    historico = []
    executadas = 0
    for geracao in range(geracoes):
        grade = ref.proxima_geracao(grade, limiar)
        c = ref.contar_estados(grade)
        historico.append((c[ref.IGNORANTE], c[ref.ESPALHADOR], c[ref.INATIVO]))
        executadas = geracao + 1
        if c[ref.ESPALHADOR] == 0:
            break
    return historico, grade, executadas


# (linhas, colunas, geracoes, percentual, limiar)
CENARIOS = [
    (10, 10, 10, 0.10, 2),
    (30, 40, 20, 0.05, 3),      # não quadrada
    (50, 50, 30, 0.02, 2),
    (100, 100, 50, 0.05, 3),    # cenário do main original
    (1, 25, 10, 0.20, 1),       # uma única linha
    (25, 1, 10, 0.20, 1),       # uma única coluna
    (20, 20, 15, 0.00, 2),      # sem espalhadores: para na 1ª geração
    (20, 20, 40, 0.50, 1),      # muito denso, limiar baixo
    (17, 23, 25, 0.08, 4),      # dimensões "estranhas" (primos)
]


def config_de(c, **extra):
    l, co, g, p, t = c
    return nucleo.Config(linhas=l, colunas=co, geracoes=g,
                         percentual_espalhadores=p, limiar_convencimento=t, **extra)


def historico_como_tuplas(historico):
    return [(h["ignorantes"], h["espalhadores"], h["inativos"]) for h in historico]


class TestNucleoContraOriginal(unittest.TestCase):
    """O nucleo.py refatorado deve se comportar igual ao código do professor."""

    def test_grade_inicial_identica(self):
        for c in CENARIOS:
            l, co, _, p, _ = c
            with self.subTest(cenario=c):
                self.assertEqual(nucleo.criar_grade(l, co, p, 42),
                                 ref.criar_grade(l, co, p, 42))

    def test_grade_inicial_com_outras_sementes(self):
        for semente in (0, 1, 7, 123, 2026):
            with self.subTest(semente=semente):
                self.assertEqual(nucleo.criar_grade(40, 40, 0.07, semente),
                                 ref.criar_grade(40, 40, 0.07, semente))

    def test_uma_geracao_identica(self):
        for c in CENARIOS:
            l, co, _, p, t = c
            with self.subTest(cenario=c):
                g0 = ref.criar_grade(l, co, p, 42)
                self.assertEqual(nucleo.proxima_geracao(g0, t),
                                 ref.proxima_geracao(g0, t))

    def test_simulacao_completa_identica(self):
        for c in CENARIOS:
            with self.subTest(cenario=c):
                l, co, g, p, t = c
                hist_ref, grade_ref, exec_ref = simular_referencia(l, co, g, p, t)
                r = nucleo.simular(config_de(c))
                self.assertEqual(historico_como_tuplas(r.historico), hist_ref)
                self.assertEqual(r.grade_final, grade_ref)
                self.assertEqual(r.geracoes_executadas, exec_ref)

    def test_parada_antecipada_sem_espalhadores(self):
        r = nucleo.simular(nucleo.Config(linhas=20, colunas=20, geracoes=100,
                                         percentual_espalhadores=0.0))
        self.assertEqual(r.geracoes_executadas, 1)
        self.assertEqual(r.historico[-1]["espalhadores"], 0)

    def test_nao_altera_grade_de_entrada(self):
        g0 = nucleo.criar_grade(30, 30, 0.1, 42)
        copia = [linha[:] for linha in g0]
        nucleo.proxima_geracao(g0, 2)
        self.assertEqual(g0, copia)

    def test_conservacao_total_de_celulas(self):
        r = nucleo.simular(config_de((40, 30, 20, 0.05, 2)))
        for h in r.historico:
            self.assertEqual(h["ignorantes"] + h["espalhadores"] + h["inativos"], 40 * 30)

    def test_ignorantes_nunca_aumentam(self):
        r = nucleo.simular(config_de((40, 40, 30, 0.05, 2)))
        ign = [h["ignorantes"] for h in r.historico]
        self.assertEqual(ign, sorted(ign, reverse=True))


class TestBlocosParaParalelismo(unittest.TestCase):
    """Peças que o Pedro (threads) e o Miguel (sockets) vão reutilizar."""

    def test_dividir_linhas_cobre_tudo_sem_sobreposicao(self):
        for total in (1, 2, 7, 10, 100, 101):
            for partes in (1, 2, 3, 4, 7, 8, 16):
                with self.subTest(total=total, partes=partes):
                    faixas = nucleo.dividir_linhas(total, partes)
                    self.assertEqual(len(faixas), partes)
                    todas = [i for f in faixas for i in f]
                    self.assertEqual(todas, list(range(total)))
                    tamanhos = [len(f) for f in faixas]
                    self.assertLessEqual(max(tamanhos) - min(tamanhos), 1)

    def test_faixas_concatenadas_igual_geracao_completa(self):
        g0 = nucleo.criar_grade(37, 29, 0.08, 42)
        esperado = nucleo.proxima_geracao(g0, 2)
        for partes in (1, 2, 3, 4, 5, 8, 37, 50):
            with self.subTest(partes=partes):
                nova = []
                for faixa in nucleo.dividir_linhas(len(g0), partes):
                    if len(faixa) == 0:
                        continue
                    nova.extend(nucleo.calcular_faixa(g0, faixa.start, faixa.stop, 2))
                self.assertEqual(nova, esperado)

    def test_fatia_com_halo_igual_geracao_completa(self):
        """
        Simula o que um worker distribuído faz: recebe suas linhas + 1 linha
        de halo em cada lado (quando existir), calcula só as linhas internas.
        """
        g0 = nucleo.criar_grade(41, 33, 0.10, 42)
        esperado = nucleo.proxima_geracao(g0, 3)
        for workers in (1, 2, 3, 4, 6, 10):
            with self.subTest(workers=workers):
                nova = []
                for faixa in nucleo.dividir_linhas(len(g0), workers):
                    if len(faixa) == 0:
                        continue
                    ini = max(faixa.start - 1, 0)
                    fim = min(faixa.stop + 1, len(g0))
                    fatia = g0[ini:fim]  # linhas próprias + halo
                    off = faixa.start - ini  # 0 na borda superior, 1 nas demais
                    nova.extend(nucleo.calcular_faixa(fatia, off, off + len(faixa), 3))
                self.assertEqual(nova, esperado)

    def test_somar_contagens(self):
        g0 = nucleo.criar_grade(30, 30, 0.1, 42)
        total = nucleo.contar_estados(g0)
        partes = [nucleo.contar_estados(g0[f.start:f.stop])
                  for f in nucleo.dividir_linhas(30, 4)]
        self.assertEqual(nucleo.somar_contagens(partes), total)

    def test_hash_grade(self):
        a = nucleo.criar_grade(20, 20, 0.1, 42)
        b = nucleo.criar_grade(20, 20, 0.1, 42)
        c = nucleo.criar_grade(20, 20, 0.1, 43)
        self.assertEqual(nucleo.hash_grade(a), nucleo.hash_grade(b))
        self.assertNotEqual(nucleo.hash_grade(a), nucleo.hash_grade(c))
        # mudar uma única célula deve mudar o hash
        b[5][5] = (b[5][5] + 1) % 3
        self.assertNotEqual(nucleo.hash_grade(a), nucleo.hash_grade(b))


class _EquivalenciaVersao:
    """Base: compara uma versão (módulo com simular(config)) com a sequencial."""
    modulo = None
    campo_paralelismo = None  # "num_threads" ou "num_processos"
    niveis = (1, 2, 3, 4)

    @classmethod
    def setUpClass(cls):
        try:
            cls.mod = importlib.import_module(cls.modulo)
        except ImportError as erro:
            # Mostra o motivo: um nome que colide com a pasta também cai aqui.
            raise unittest.SkipTest(f"módulo '{cls.modulo}' não importou: {erro}")
        if not hasattr(cls.mod, "simular"):
            raise unittest.SkipTest(f"'{cls.modulo}' não expõe simular(config)")

    def test_equivale_a_sequencial(self):
        for c in CENARIOS:
            for n in self.niveis:
                with self.subTest(cenario=c, paralelismo=n):
                    cfg = config_de(c, **{self.campo_paralelismo: n})
                    esperado = nucleo.simular(cfg)
                    obtido = self.mod.simular(cfg)
                    self.assertEqual(obtido.historico, esperado.historico)
                    self.assertEqual(obtido.geracoes_executadas, esperado.geracoes_executadas)
                    self.assertEqual(obtido.hash_grade, esperado.hash_grade)
                    self.assertEqual(obtido.grade_final, esperado.grade_final)

    def test_mais_workers_que_linhas(self):
        cfg = config_de((3, 20, 10, 0.2, 2), **{self.campo_paralelismo: 8})
        esperado = nucleo.simular(cfg)
        obtido = self.mod.simular(cfg)
        self.assertEqual(obtido.hash_grade, esperado.hash_grade)

    def test_resultado_estavel_entre_execucoes(self):
        """Roda várias vezes: se houver condição de corrida, o hash varia."""
        cfg = config_de((60, 60, 30, 0.05, 2), **{self.campo_paralelismo: 4})
        hashes = {self.mod.simular(cfg).hash_grade for _ in range(5)}
        self.assertEqual(len(hashes), 1)


class TestParalelaEquivaleSequencial(_EquivalenciaVersao, unittest.TestCase):
    modulo = MODULO_PARALELO
    campo_paralelismo = "num_threads"


class TestDistribuidaEquivaleSequencial(_EquivalenciaVersao, unittest.TestCase):
    modulo = MODULO_DISTRIBUIDO
    campo_paralelismo = "num_processos"


if __name__ == "__main__":
    unittest.main(verbosity=2)
