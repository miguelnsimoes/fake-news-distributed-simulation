"""Cálculos estatísticos e seleção de referências do analisador."""

import csv
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
import analyze


def registro(tempo, **opcoes):
    linha = dict(
        experimento="teste", cenario="1", linhas="12", colunas="12",
        geracoes_pedidas="4", espalhadores="0.1", limiar="1", semente="42",
        backend="threads", kernel="otimizado", divisao="estatica", workers="1",
        fase="medicao", tempo_externo_s=str(tempo), matriz_identica="True",
        historico_identico="True", status="ok",
    )
    linha.update(opcoes)
    return linha


class TestAnalyze(unittest.TestCase):
    def test_estatisticas_e_referencias_separadas(self):
        registros = [registro(t, backend="sequencial", kernel="professor", divisao="") for t in (8, 12)]
        registros += [registro(t) for t in (4, 6)]
        registros += [registro(t, workers="2") for t in (2, 3)]
        seq, um, dois = analyze.resumir(registros)
        self.assertEqual(seq["ganho_vs_sequencial"], 1)
        self.assertEqual(seq["speedup_escalabilidade"], "")
        self.assertEqual(um["speedup_escalabilidade"], 1)
        self.assertEqual(dois["mediana_tempo_externo_s"], 2.5)
        self.assertEqual(dois["media_tempo_externo_s"], 2.5)
        self.assertAlmostEqual(dois["desvio_padrao_tempo_externo_s"], math.sqrt(0.5))
        self.assertEqual((dois["minimo_tempo_externo_s"], dois["maximo_tempo_externo_s"]), (2, 3))
        self.assertEqual(dois["ganho_vs_sequencial"], 4)
        self.assertEqual(dois["speedup_escalabilidade"], 2)
        self.assertEqual(dois["eficiencia_escalabilidade"], 1)

    def test_tempos_e_validacoes_invalidas(self):
        registros = [registro(t) for t in ("", "abc", "nan", "inf", "-inf", -1, 0)]
        registros += [registro(1, status="erro"), registro(1, matriz_identica="False"),
                      registro(1, historico_identico="False"), registro(2)]
        registros.append(registro(100, fase="aquecimento"))
        linha, = analyze.resumir(registros)
        self.assertEqual(linha["repeticoes_validas"], 1)
        self.assertEqual(linha["repeticoes_invalidas"], 10)
        self.assertEqual(linha["mediana_tempo_externo_s"], 2)
        self.assertEqual(linha["desvio_padrao_tempo_externo_s"], "")

    def test_referencias_ausentes_e_grupo_sem_validas(self):
        dois, invalido = analyze.resumir([registro(2, workers="2"), registro("nan")])
        for linha in (dois, invalido):
            self.assertEqual(linha["ganho_vs_sequencial"], "")
            self.assertEqual(linha["speedup_escalabilidade"], "")
            self.assertEqual(linha["eficiencia_escalabilidade"], "")
        self.assertEqual(invalido["repeticoes_invalidas"], 1)
        self.assertEqual(invalido["mediana_tempo_externo_s"], "")

    def test_nao_mistura_cenarios_backends_kernels_ou_divisoes(self):
        base = registro(10)
        variacoes = [dict(cenario="2"), dict(experimento="outro"), dict(linhas="24"),
                     dict(backend="processos"), dict(kernel="referencia"), dict(divisao="dinamica")]
        linhas = analyze.resumir([base] + [registro(2, workers="2", **v) for v in variacoes])
        for linha in linhas[1:]:
            self.assertEqual(linha["speedup_escalabilidade"], "")
        linhas = analyze.resumir([
            registro(10, backend="sequencial"), registro(2, cenario="2", workers="2"),
        ])
        self.assertEqual(linhas[1]["ganho_vs_sequencial"], "")

    def test_arquivos_de_entrada_preservados(self):
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario)
            with (pasta / "raw.csv").open("w", newline="", encoding="utf-8") as arquivo:
                linha = registro(2)
                escritor = csv.DictWriter(arquivo, fieldnames=list(linha))
                escritor.writeheader()
                escritor.writerow(linha)
            for nome in ("warmup.csv", "metadata.json"):
                (pasta / nome).write_text("preservar", encoding="utf-8")
            antes = {p.name: p.read_bytes() for p in pasta.iterdir()}
            summary, linhas = analyze.analisar(pasta)
            self.assertEqual(summary, pasta / "summary.csv")
            for nome, conteudo in antes.items():
                self.assertEqual((pasta / nome).read_bytes(), conteudo)
            with summary.open(newline="", encoding="utf-8") as arquivo:
                self.assertEqual(len(list(csv.DictReader(arquivo))), len(linhas))
            (pasta / "raw.csv").write_text("coluna_errada\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Colunas ausentes"):
                analyze.analisar(pasta)


if __name__ == "__main__":
    unittest.main()
