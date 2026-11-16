# Contrato de interface e núcleo compartilhado

Este documento define como as três versões (sequencial, paralela e distribuída) se encaixam.
O código comum está em `src/common/core.py`; o código original do professor continua intacto em
`src/sequential/fake_news.py` e serve de gabarito nos testes.

## Estrutura

```
src/
  common/core.py                  # base comum: regras, grade, contagem, hash, simular sequencial
  sequential/fake_news.py         # ORIGINAL do professor (não alterar)
  sequential/run_sequential.py    # CLI da versão sequencial (usa common/core.py)
  parallel/                       # (Pedro)  expõe simular(config)
  distributed/                    # (Miguel) expõe simular(config)
tests/test_equivalence.py         # testes de equivalência
```

## Como rodar (na raiz do repositório)

```bash
python src/sequential/run_sequential.py                                  # padrão
python src/sequential/run_sequential.py -l 500 -c 500 -g 100 -p 0.02 -t 2
python src/sequential/run_sequential.py --silencioso --saida seq.json    # benchmark
python -m unittest discover -s tests -v                                  # testes
```

Só usa a biblioteca padrão (Python 3.8+).

## Como importar o núcleo nas outras versões

Os scripts são executados direto (`python src/parallel/x.py`), então o Python não enxerga `src/`
sozinho. Coloque no topo do arquivo, antes dos imports:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # adiciona src/ ao path

from common.core import Config, Resultado, calcular_faixa, dividir_linhas  # etc.
```

## Contrato (todas as versões)

Cada versão expõe uma função:

```python
def simular(config: Config) -> Resultado
```

Os testes procuram por padrão `src/parallel/parallel.py` e `src/distributed/distributed.py`
(nomes configuráveis em `MODULO_PARALELO` / `MODULO_DISTRIBUIDO`, no topo de
`tests/test_equivalence.py`). Se o módulo não existir, o teste dessa versão é pulado.

- `Config`: `linhas, colunas, geracoes, percentual_espalhadores, limiar_convencimento, semente, num_threads, num_processos`
- `Resultado`: `versao, config, historico, geracoes_executadas, tempo_s, grade_final, hash_grade`
- `historico`: lista de `{"geracao", "ignorantes", "espalhadores", "inativos"}`, uma por geração
  (use `registro_historico`).
- A grade inicial é sempre criada **inteira** com `criar_grade(...)` e depois distribuída.
- Parada: igual ao original (roda `geracoes` ou até `espalhadores == 0`).
- Resultado correto = mesmo `historico` e mesmo `hash_grade` de `simular` em `common/core.py`.
- `tempo_s` mede só o laço de gerações (sem criar a grade inicial e sem impressão). Nas versões
  paralela/distribuída inclui criação de threads e comunicação. O grupo precisa combinar se subir os
  workers entra na medição e manter a mesma regra em todos os experimentos.

## Blocos prontos (src/common/core.py)

| Função | Para quê |
|---|---|
| `dividir_linhas(total, partes)` | divide as linhas em faixas contíguas e balanceadas |
| `calcular_faixa(grade, ini, fim, limiar)` | calcula só as linhas `[ini, fim)`; **lê** a grade e devolve linhas novas |
| `contar_estados(grade)` / `somar_contagens([...])` | contagem parcial por thread/worker e soma |
| `registro_historico(geracao, contagem)` | formato padrão do histórico |
| `hash_grade(grade)` | prova de que duas versões chegaram ao mesmo estado |

### Threads

Cada thread chama `calcular_faixa(grade_atual, ini, fim, limiar)` e guarda o resultado numa posição
própria (`resultados[k]`). Como ninguém escreve em `grade_atual`, não há condição de corrida. Use
`join` ou `threading.Barrier` entre gerações e monte a nova grade só depois que todas terminarem.
Em CPython, threads puras não aceleram trabalho de CPU (GIL); o enunciado aceita `multiprocessing`
para paralelismo real, então vale medir e discutir isso.

### Sockets

Cada worker mantém suas linhas mais 1 linha de halo em cima e embaixo. A cada geração: troca as
bordas com os vizinhos, monta `fatia = [halo_cima] + minhas_linhas + [halo_baixo]` (sem halo nas
bordas globais) e chama `calcular_faixa(fatia, off, off + n, limiar)`, com `off = 1` se houver halo
em cima, senão `0`. Isso é validado por `test_fatia_com_halo_igual_geracao_completa`.

Atenção ao `protocol.py` atual: o limite de 1 MiB por mensagem JSON. Uma lista de inteiros em JSON
gasta cerca de 3 bytes por célula, então 1 MiB comporta algo perto de 350 mil células. O envio
inicial da fatia de cada worker passa disso em matrizes grandes (ex.: 1000x1000 com 2 workers). Vale
enviar as linhas como texto (um caractere por célula, ex. `"0120..."`) ou em lotes, ou aumentar o
limite.

## Parâmetros para os benchmarks

Os parâmetros do `main` original (5% de espalhadores, limiar 3) fazem a propagação **morrer em 2–3
gerações**, então qualquer medição sobre eles quase não exercita a simulação. Medido em 200x200 com
50 gerações pedidas:

| espalhadores | limiar | gerações executadas |
|---|---|---|
| 5% | 3 | 3 |
| 10% | 3 | 3 |
| 5% | 2 | 44 |
| 2% | 2 | 50 (ainda com espalhadores) |

Sugestão: usar limiar 2 (ou 1) nos experimentos e registrar quantas gerações realmente rodaram.

## Mudanças em relação ao original

- Regras e resultados **idênticos** (testado contra o próprio `fake_news.py` em 9 cenários).
- Sem `deepcopy`: cada linha nova é construída direto (ganho pequeno, ~10%).
- `criar_grade` usa `random.Random(semente)` local em vez de `random.seed` global: mesma sequência,
  sem efeito colateral entre módulos/threads.
- Tempo medido com `time.perf_counter()`.
- `Config`/`Resultado` padronizados, com saída JSON, e `hash_grade` para comparar versões.
