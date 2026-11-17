"""Contratos do executor; arquivos restritos a diretórios temporários."""

import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
import run_experiments as runner


class TestRunExperiments(unittest.TestCase):
    def test_padrao_e_piloto(self):
        self.assertEqual(runner.argumentos([]).repeticoes, 5)
        piloto = runner.argumentos(["--piloto"])
        self.assertEqual((piloto.linhas, piloto.colunas, piloto.geracoes), ([12], [12], [4]))
        self.assertEqual(runner.argumentos(["--piloto", "--repeticoes", "5"]).repeticoes, 5)

    def test_aquecimento_csv_equivalencia_e_diretorio_exclusivo(self):
        with tempfile.TemporaryDirectory() as temporario:
            args = runner.argumentos(["--piloto", "--workers", "1", "--saida", temporario])
            original = runner._executar
            entradas = []

            def executar(grade, *parametros):
                entradas.append(grade)
                return original(grade, *parametros)

            with patch.object(runner, "_executar", side_effect=executar), redirect_stdout(io.StringIO()):
                pasta, sucesso = runner.executar_experimento(args)
            self.assertTrue(sucesso)
            self.assertTrue(all(grade is entradas[0] for grade in entradas))
            for nome, quantidade, fase in (("raw.csv", 6, "medicao"), ("warmup.csv", 3, "aquecimento")):
                with (pasta / nome).open(encoding="utf-8", newline="") as arquivo:
                    registros = list(csv.DictReader(arquivo))
                self.assertEqual(len(registros), quantidade)
                self.assertEqual({r["backend"] for r in registros}, {"sequencial", "threads", "processos"})
                self.assertTrue(all(r["status"] == "ok" and r["fase"] == fase for r in registros))
                self.assertTrue(all(float(r["tempo_externo_s"]) >= 0 for r in registros))
            with patch.object(runner, "_executar", return_value=runner.adapters.executar_sequencial([[0]], 0)), redirect_stdout(io.StringIO()):
                outra, _ = runner.executar_experimento(args)
            self.assertNotEqual(pasta, outra)
            self.assertTrue((pasta / "metadata.json").exists())

    def test_registra_divergencia_e_erro(self):
        referencia = runner.adapters.executar_sequencial([[0]], 0)
        divergente = runner.adapters.executar_sequencial([[1]], 0)
        with tempfile.TemporaryDirectory() as temporario:
            args = runner.argumentos(["--piloto", "--workers", "1", "--repeticoes", "1", "--saida", temporario])
            def executar(grade, geracoes, limiar, backend, workers):
                if backend == "threads":
                    return divergente
                if backend == "processos":
                    raise RuntimeError("falha de teste")
                return referencia
            with patch.object(runner, "_executar", side_effect=executar), redirect_stdout(io.StringIO()):
                pasta, sucesso = runner.executar_experimento(args)
            self.assertFalse(sucesso)
            with (pasta / "raw.csv").open(encoding="utf-8", newline="") as arquivo:
                registros = list(csv.DictReader(arquivo))
            self.assertEqual({r["status"] for r in registros}, {"ok", "divergente", "erro"})
            erro = next(r for r in registros if r["status"] == "erro")
            self.assertEqual(erro["tempo_externo_s"], "")
            self.assertIn("falha de teste", erro["erro"])

    def test_falha_da_referencia_aborta_cenario(self):
        with tempfile.TemporaryDirectory() as temporario:
            args = runner.argumentos(["--piloto", "--saida", temporario])
            with patch.object(runner, "_executar", side_effect=RuntimeError("sem referência")) as executar, redirect_stdout(io.StringIO()):
                _, sucesso = runner.executar_experimento(args)
            self.assertFalse(sucesso)
            self.assertEqual(executar.call_count, 1)


if __name__ == "__main__":
    unittest.main()
