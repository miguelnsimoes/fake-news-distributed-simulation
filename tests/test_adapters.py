"""Contratos dos adaptadores de benchmark, sem gravação de resultados."""

import io
import sys
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
import adapters


class TestAdapters(unittest.TestCase):
    def test_equivalencia_e_preservacao_da_entrada(self):
        grade = [[0, 1, 0, 0], [1, 0, 0, 2], [0, 0, 1, 0]]
        original = deepcopy(grade)
        esperado = adapters.executar_sequencial(grade, 8, 2)
        for backend in ("threads", "processos"):
            for divisao in ("estatica", "dinamica"):
                with self.subTest(backend=backend, divisao=divisao):
                    resultado = adapters.executar_paralelo(
                        grade, 8, 2, workers=2, backend=backend, divisao=divisao,
                    )
                    self.assertEqual(resultado.grade_final, esperado.grade_final)
                    self.assertEqual(resultado.historico, esperado.historico)
                    self.assertEqual(resultado.geracoes_executadas, esperado.geracoes_executadas)
                    self.assertEqual(grade, original)
                    self.assertGreaterEqual(resultado.tempo_externo_s, resultado.tempo_total_s)
                    self.assertGreaterEqual(resultado.tempo_geracoes_s, 0)
        self.assertEqual(grade, original)

    def test_parada_e_zero_geracoes_sem_alias_da_entrada(self):
        for executar in (adapters.executar_sequencial, adapters.executar_paralelo):
            with self.subTest(executar=executar.__name__):
                grade = [[0, 0], [0, 0]]
                resultado = executar(grade, 20, 2)
                self.assertEqual(resultado.historico, [(4, 0, 0)])
                resultado = executar(grade, 0, 2)
                self.assertEqual(resultado.historico, [])
                self.assertEqual(resultado.geracoes_executadas, 0)
                self.assertEqual(resultado.grade_final, grade)
                resultado.grade_final[0][0] = 2
                self.assertEqual(grade[0][0], 0)

    def test_limite_de_geracoes_e_ordem_das_contagens(self):
        grade = [[0, 1], [2, 0]]
        for executar in (adapters.executar_sequencial, adapters.executar_paralelo):
            with self.subTest(executar=executar.__name__):
                resultado = executar(grade, 1, 1)
                self.assertEqual(resultado.grade_final, [[1, 2], [2, 1]])
                self.assertEqual(resultado.historico, [(0, 2, 2)])
                self.assertEqual(resultado.geracoes_executadas, 1)

    def test_sem_impressao(self):
        saida = io.StringIO()
        with redirect_stdout(saida):
            adapters.executar_sequencial([[0, 1]], 2, 1)
            adapters.executar_paralelo([[0, 1]], 2, 1)
        self.assertEqual(saida.getvalue(), "")

    def test_entradas_invalidas(self):
        for executar in (adapters.executar_sequencial, adapters.executar_paralelo):
            for grade, geracoes in (([], 1), ([[]], 1), ([[0], [0, 1]], 1),
                                    ([[3]], 1), ([[0]], -1)):
                with self.subTest(executar=executar.__name__, grade=grade, geracoes=geracoes):
                    with self.assertRaises(ValueError):
                        executar(grade, geracoes)

    def test_encaminha_opcoes_e_mede_chamada_externa(self):
        # Relógio controlado prova o escopo externo sem depender da máquina.
        with patch.object(adapters.paralelo, "simular_paralelo") as simular:
            simular.return_value = adapters.paralelo.ResultadoSimulacao(
                [[2]], [(0, 0, 1)], 0.5, 0.8, [0.4], 0.4,
                "processos", 1, "referencia", "dinamica", 3,
            )
            with patch.object(adapters.time, "perf_counter", side_effect=[10.0, 12.0]):
                grade = [[1]]
                resultado = adapters.executar_paralelo(
                    grade, 4, 3, workers=1, backend="processos",
                    kernel="referencia", divisao="dinamica", pedaco=3,
                )
            simular.assert_called_once_with(
                grade, 4, limiar_convencimento=3, workers=1, backend="processos",
                kernel="referencia", divisao="dinamica", pedaco=3,
            )
            self.assertIsNot(simular.call_args.args[0][0], grade[0])
            self.assertEqual(resultado.tempo_externo_s, 2.0)
            self.assertEqual(resultado.tempo_total_s, 0.8)
            self.assertEqual(resultado.tempo_geracoes_s, 0.5)


if __name__ == "__main__":
    unittest.main()
