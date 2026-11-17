"""Trajetória de referência e exportação de demonstrações pequenas."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchmarks"))
import visualize


class TestVisualize(unittest.TestCase):
    def test_trajetoria_contagens_e_preservacao_da_entrada(self):
        grade = [[0, 1], [2, 0]]
        quadros = visualize.gerar_trajetoria(grade, 10, 1)
        self.assertEqual([q.geracao for q in quadros], [0, 1, 2])
        self.assertEqual([q.contagem for q in quadros],
                         [{0: 2, 1: 1, 2: 1}, {0: 0, 1: 2, 2: 2}, {0: 0, 1: 0, 2: 4}])
        self.assertEqual(quadros[1].grade, [[1, 2], [2, 1]])
        self.assertEqual(quadros[2].grade, [[2, 2], [2, 2]])
        quadros[0].grade[0][0] = 2
        self.assertEqual(grade, [[0, 1], [2, 0]])

    def test_limite_zero_e_parada_apos_primeira_geracao(self):
        self.assertEqual(len(visualize.gerar_trajetoria([[1]], 0, 2)), 1)
        self.assertEqual(len(visualize.gerar_trajetoria([[0]], 15, 2)), 2)
        # Limiar zero cria espalhadores, mesmo se não houver nenhum na entrada.
        self.assertEqual(visualize.gerar_trajetoria([[0]], 1, 0)[-1].contagem[1], 1)

    def test_reprodutibilidade(self):
        a = visualize.criar_grade(5, 5, 0.2, 7)
        b = visualize.criar_grade(5, 5, 0.2, 7)
        self.assertEqual(a, b)
        self.assertEqual(visualize.gerar_trajetoria(a, 4, 2), visualize.gerar_trajetoria(b, 4, 2))

    def test_exportacao_png_gif_e_diretorios_exclusivos(self):
        with tempfile.TemporaryDirectory() as temporario:
            quadros = visualize.gerar_trajetoria([[0, 1], [2, 0]], 3, 1)
            pasta = visualize.exportar(quadros, temporario)
            for nome in ("inicial.png", "final.png"):
                with Image.open(pasta / nome) as imagem:
                    self.assertEqual(imagem.format, "PNG")
                    imagem.verify()
            with Image.open(pasta / "propagacao.gif") as imagem:
                self.assertEqual(imagem.n_frames, len(quadros))
                self.assertEqual(imagem.info["loop"], 0)
                for i in range(imagem.n_frames):
                    imagem.seek(i)
                    imagem.load()
            metadata = json.loads((pasta / "visualization.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["geracoes_executadas"], 2)
            antes = (pasta / "propagacao.gif").read_bytes()
            outra = visualize.exportar(quadros[:1], temporario)
            self.assertNotEqual(pasta, outra)
            self.assertEqual((pasta / "propagacao.gif").read_bytes(), antes)
            with Image.open(outra / "propagacao.gif") as imagem:
                self.assertEqual(imagem.n_frames, 1)


if __name__ == "__main__":
    unittest.main()
