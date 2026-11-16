"""Regra de transição da simulação, aplicada uma linha por vez.

Por causa da vizinhança de Moore, a linha ``i`` da próxima geração depende
só das linhas ``i - 1``, ``i`` e ``i + 1`` da geração atual. As funções
daqui recebem exatamente essas três linhas e devolvem a nova linha ``i``.
Quem decide quais linhas cada thread/processo calcula é o código que divide
o trabalho (``fake_news_paralelo.py``); a regra não sabe nada disso.

Formato: cada linha é um ``bytes`` com um byte por pessoa (0, 1 ou 2).
``None`` em ``acima``/``abaixo`` significa "fora da matriz" (bordas superior
e inferior), o mesmo que o teste de limites do código sequencial.

Os dois kernels dão exatamente o mesmo resultado que ``proxima_geracao`` de
``src/sequential/fake_news.py`` (verificado em ``tests/test_paralelo.py``):

* ``linha_referencia``: mesma estratégia do professor, célula a célula,
  olhando os 8 vizinhos com teste de limites. É a base justa para medir o
  ganho que vem só do paralelismo.
* ``linha_otimizada``: mesma regra, mas soma os espalhadores por coluna e
  usa uma janela de 3 colunas, sem teste de limites por vizinho. É uma
  otimização de algoritmo, independente do paralelismo, e o ganho dela deve
  ser apresentado separado do speedup.
"""

from __future__ import annotations

from typing import Callable, Optional

# Mesmos códigos de src/sequential/fake_news.py (o teste confere).
IGNORANTE = 0
ESPALHADOR = 1
INATIVO = 2

Kernel = Callable[[Optional[bytes], bytes, Optional[bytes], int], bytes]

# Tabela para bytes.translate: espalhador -> 1, qualquer outro estado -> 0.
_SO_ESPALHADORES = bytes.maketrans(
    bytes((IGNORANTE, ESPALHADOR, INATIVO)),
    bytes((0, 1, 0)),
)


def linha_referencia(
    acima: Optional[bytes], linha: bytes, abaixo: Optional[bytes], limiar: int
) -> bytes:
    """Calcula a nova linha célula a célula, como o código sequencial."""
    colunas = len(linha)
    trio = (acima, linha, abaixo)
    nova = bytearray(colunas)

    for j in range(colunas):
        if linha[j] == IGNORANTE:
            vizinhos = 0
            for di in range(3):
                vizinha = trio[di]
                if vizinha is None:  # linha fora da matriz
                    continue
                for dj in (-1, 0, 1):
                    if di == 1 and dj == 0:  # a própria célula
                        continue
                    nj = j + dj
                    if 0 <= nj < colunas and vizinha[nj] == ESPALHADOR:
                        vizinhos += 1
            nova[j] = ESPALHADOR if vizinhos >= limiar else IGNORANTE
        else:
            # Espalhador vira inativo; inativo continua inativo.
            nova[j] = INATIVO

    return bytes(nova)


def linha_otimizada(
    acima: Optional[bytes], linha: bytes, abaixo: Optional[bytes], limiar: int
) -> bytes:
    """Calcula a nova linha somando espalhadores por coluna.

    ``colunas_somadas[k]`` guarda quantos espalhadores existem na coluna
    ``k - 1`` das três linhas, com um zero extra em cada ponta. A janela 3x3
    da célula ``j`` é então ``colunas_somadas[j] + [j + 1] + [j + 2]``. Para
    uma célula ignorante a própria célula vale 0 na soma, então a janela é
    exatamente o número de vizinhos espalhadores. Os zeros das pontas fazem
    o papel do teste de limites das bordas esquerda e direita.
    """
    vazia = bytes(len(linha))
    e_acima = vazia if acima is None else acima.translate(_SO_ESPALHADORES)
    e_meio = linha.translate(_SO_ESPALHADORES)
    e_abaixo = vazia if abaixo is None else abaixo.translate(_SO_ESPALHADORES)

    colunas_somadas = [0]
    colunas_somadas += [a + b + c for a, b, c in zip(e_acima, e_meio, e_abaixo)]
    colunas_somadas.append(0)

    return bytes(
        [
            INATIVO
            if estado != IGNORANTE
            else (ESPALHADOR if esquerda + centro + direita >= limiar else IGNORANTE)
            for estado, esquerda, centro, direita in zip(
                linha, colunas_somadas, colunas_somadas[1:], colunas_somadas[2:]
            )
        ]
    )


KERNELS: dict[str, Kernel] = {
    "referencia": linha_referencia,
    "otimizado": linha_otimizada,
}
