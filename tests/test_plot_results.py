"""Geração real de PNGs e isolamento de configurações, sem benchmarks."""

import csv
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
import plot_results as plots


def registro(**opcoes):
    linha = dict.fromkeys(plots.OBRIGATORIOS, "")
    linha.update(experimento="piloto", cenario="1", linhas="12", colunas="12",
                 geracoes_pedidas="4", espalhadores="0.1", limiar="1", semente="42",
                 implementacao="paralela", backend="threads", kernel="otimizado",
                 divisao="estatica", workers="1", repeticoes_validas="2",
                 mediana_tempo_externo_s="0.001", speedup_vs_sequencial="1",
                 speedup_escalabilidade="1",
                 eficiencia_escalabilidade="1")
    linha.update(opcoes)
    return linha


def gravar(pasta, registros):
    with (pasta / "summary.csv").open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=sorted(plots.OBRIGATORIOS))
        escritor.writeheader()
        escritor.writerows(registros)


class TestPlotResults(unittest.TestCase):
    def test_pngs_por_cenario_e_preservacao_dos_csvs(self):
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            gravar(pasta, [registro(), registro(workers="2", speedup_escalabilidade="1.5"),
                          registro(cenario="2", linhas="24")])
            for nome in ("raw.csv", "warmup.csv", "metadata.json"):
                (pasta / nome).write_text("preservar", encoding="utf-8")
            antes = {p.name: p.read_bytes() for p in pasta.iterdir()}
            arquivos = plots.gerar_graficos(pasta)
            self.assertEqual(len(arquivos), 8)
            for arquivo in arquivos:
                self.assertEqual(arquivo.parent, pasta / "figures")
                self.assertTrue(arquivo.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertGreater(arquivo.stat().st_size, 1000)
            for nome, dados in antes.items():
                self.assertEqual((pasta / nome).read_bytes(), dados)

    def test_titulo_descreve_extensoes(self):
        self.assertEqual(plots._descrever_extensoes({}), "")
        self.assertEqual(plots._descrever_extensoes(
            dict(probabilidade="1.0", influenciadores="0.0", bots="0.0")), "")
        texto = plots._descrever_extensoes(
            dict(probabilidade="0.5", influenciadores="0.02", peso_influenciador="3", bots="0.0"))
        self.assertIn("probabilidade=0.5", texto)
        self.assertIn("peso 3", texto)

    def test_referencias_ausentes_e_tempos_invalidos(self):
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            gravar(pasta, [registro(workers="2", mediana_tempo_externo_s="nan",
                                   speedup_vs_sequencial="",
                                   speedup_escalabilidade="", eficiencia_escalabilidade="")])
            cenario, = plots.ler_cenarios(pasta / "summary.csv").values()
            for metrica in plots.METRICAS:
                self.assertTrue(math.isnan(cenario[0][metrica]))
            self.assertEqual(len(plots.gerar_graficos(pasta)), 4)
        for valor in ("", "abc", "inf", "nan", "0", "-1"):
            self.assertTrue(math.isnan(plots.numero(valor)))

    def test_series_distintas_e_dados_sem_repeticoes_validas(self):
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            gravar(pasta, [registro(), registro(backend="processos"),
                          registro(kernel="referencia"), registro(divisao="dinamica"),
                          registro(workers="2", repeticoes_validas="0")])
            registros, = plots.ler_cenarios(pasta / "summary.csv").values()
            self.assertEqual(len({tuple(r[c] for c in plots.SERIE) for r in registros}), 4)
            self.assertTrue(math.isnan(registros[-1]["mediana_tempo_externo_s"]))
            gravar(pasta, [registro(), registro()])
            with self.assertRaisesRegex(ValueError, "duplicada"):
                plots.gerar_graficos(pasta)

    def test_csv_vazio_e_cabecalho_invalido(self):
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            gravar(pasta, [])
            self.assertEqual(plots.gerar_graficos(pasta), [])
            (pasta / "summary.csv").write_text("errado\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Colunas ausentes"):
                plots.gerar_graficos(pasta)


if __name__ == "__main__":
    unittest.main()
