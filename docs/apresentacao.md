# Roteiro da apresentação — 15 a 20 minutos

Este arquivo é o conteúdo-base dos slides. Substitua os campos entre colchetes e use os gráficos do experimento final em `benchmarks/results/`.

## Slide 1 — Capa (30 s)

- Fake News Distributed Simulation
- Sistemas Paralelos e Distribuídos
- Integrantes: Miguel, [nome], [nome], [nome]

## Slide 2 — Problema e objetivo (1 min)

- População representada por uma matriz bidimensional.
- Cada posição é um indivíduo.
- Objetivo: preservar o modelo e comparar execução sequencial, paralela e distribuída.

## Slide 3 — Modelo computacional (1 min)

- Estados: ignorante, espalhador e inativo.
- Vizinhança de Moore: até oito vizinhos.
- Gerações síncronas: a geração nova lê somente a anterior.
- Critério de parada: ausência de espalhadores ou limite de gerações.

## Slide 4 — Versão sequencial (1 min)

- Código do professor preservado como referência.
- Percorre toda a grade e produz uma nova grade.
- Mesmo estado inicial e mesma semente nas comparações.

## Slide 5 — Versão paralela (2 min)

- Matriz dividida em faixas de linhas.
- Uma thread ou processo é dono de cada faixa.
- Buffer duplo evita leitura de valores da geração nova.
- Barreira garante gerações consistentes.
- Threads são corretas, mas o GIL limita desempenho no CPython tradicional; processos permitem paralelismo real.

## Slide 6 — Versão distribuída (2 min)

- Coordenador TCP cria e divide a grade.
- Cada worker mantém seu bloco localmente.
- Apenas primeira e última linha são trocadas a cada geração.
- Coordenador encaminha halos e espera todos: barreira distribuída.
- Ao final, contagens são somadas e os blocos reunidos.

```text
Worker 0 [linhas 0..n] <-- halos --> Coordenador <-- halos --> Worker 1 [linhas n+1..m]
                              barreira por geração
```

## Slide 7 — Protocolo TCP (1 min)

- TCP entrega um fluxo de bytes, não mensagens.
- Cada JSON recebe prefixo binário de 4 bytes com o tamanho.
- `receber_bytes` trata leituras parciais.
- Grades grandes usam lotes; durante as gerações viajam somente halos e contagens.

## Slide 8 — Melhorias (2 min)

- Probabilidade de convencimento.
- Influenciadores com peso.
- Bots permanentes.
- Sorteio determinístico por semente, geração, linha e coluna mantém equivalência.
- Kernel otimizado, divisão dinâmica, visualização e redução de comunicação.

## Slide 9 — Metodologia experimental (1 min)

- Mesmos cenários para sequencial, paralela (threads e processos) e distribuída.
- Tamanhos de 200×200, 350×350 e 500×500 na rodada de tamanho. As rodadas de gerações e espalhadores usam 400×400.
- Limites de 10, 30 e 60 gerações, frações iniciais de 1%, 2% e 5% e configurações com 1, 2, 4 e 8 threads ou processos. A rodada de escalabilidade em 500×500 inclui as quatro quantidades de workers.
- Aquecimento separado e cinco repetições; análise pela mediana.
- Speedup contra a sequencial com o mesmo kernel, usando a mediana do tempo externo. Eficiência contra essa referência = speedup ÷ workers.
- Ambiente das rodadas comparativas: Intel Core 5 210H, 8 núcleos físicos e 12 CPUs lógicas, 15,63 GiB de RAM detectada, Windows 11 e CPython 3.12.1 com GIL. A distribuída usa processos TCP locais em um único computador.
- As sete pastas de experimento em [resultados finais](../benchmarks/results/final/) reúnem 18 cenários em cinco séries, incluindo oito cenários de extensões. As 715 medições passaram na comparação da matriz final e do histórico de gerações.

## Slide 10 — Tempo e speedup (2 min)

Rodada de [escalabilidade em 500×500](../benchmarks/results/final/escalabilidade/20261121T220221161094Z_06ef00fb/summary.csv), com até 30 gerações e 2% de espalhadores iniciais.

| Versão | Tempo externo mediano | Speedup contra a sequencial | Eficiência |
| --- | ---: | ---: | ---: |
| Sequencial otimizada | 0,993 s | 1,00× | — |
| Paralela com 4 threads | 1,263 s | 0,79× | 20% |
| Paralela com 4 processos | 0,447 s | 2,22× | 56% |
| Distribuída com 4 workers locais | 0,543 s | 1,83× | 46% |

## Slide 11 — Eficiência e escalabilidade (1 min)

- Usar o [gráfico de speedup contra a sequencial](../benchmarks/results/final/escalabilidade/20261121T220221161094Z_06ef00fb/figures/cenario_001_speedup_sequencial.png). Entre as quantidades testadas, a paralela com processos teve o menor tempo com 4 workers. A distribuída passou de 1,83× com 4 para 1,91× com 8.
- Usar o [gráfico das três variações de cenário](../benchmarks/results/final/comparacao_cenarios.png) para comparar os backends com 4 workers. A distribuída atingiu 0,86× em 200×200 e 1,66× em 350×350. Com a matriz 400×400, passou de 0,61× com limite de 10 gerações para 2,13× com limite de 60. Na rodada de espalhadores, foi de 1,23× com 1% inicial para 1,69× com 5%.
- Cada painel usa sua própria rodada pareada com a sequencial. Em 500×500, o speedup de 1,43× na série de tamanhos e o de 1,83× na série de escalabilidade vieram de medições separadas.
- A [rodada dedicada da distribuída em 1000×1000](../benchmarks/results/distribuida/20261122T182823334195Z_08c558aa/summary.csv) complementa a comparação. Com 8 workers locais, o tempo externo mediano foi de 1,186 s, frente a 4,015 s da sequencial otimizada, para um speedup de 3,39×. Essa série inclui sequencial e distribuída.

## Slide 12 — Comunicação e sincronização (1 min)

- Na rodada dedicada de 1000×1000, o servidor encaminhou 180.000 células de borda com 4 workers e 420.000 com 8, ao longo de 30 gerações. Cada fronteira interna exige o envio de uma linha em cada sentido.
- O overhead mediano durante as gerações foi de 59 ms com 4 workers e 69 ms com 8. É a diferença entre o tempo das gerações e o caminho crítico de cálculo. Inclui coordenação, comunicação e espera na barreira.
- O coordenador centraliza a troca de halos e só avança quando todos respondem. Medições em loopback descrevem o ambiente local e a parcela de latência de uma rede física permanece sem medição.

## Slide 13 — Correção e testes (1 min)

- Comparação de histórico, matriz e hash final.
- Testes de fragmentação TCP, lotes grandes e geração fora de ordem.
- Testes com mais workers que linhas, falha injetada e extensões combinadas.
- Informar o total final de testes da última execução.

## Slide 14 — Limitações e dificuldades (1 min)

- GIL em threads no CPython tradicional.
- Custo de `spawn` no Windows.
- Comunicação local não representa toda a latência de uma rede física.
- Sem tolerância a falhas ou autenticação.
- Modelo em grade é uma aproximação de redes sociais reais.

## Slide 15 — Contribuições, referências e IA (1 min)

- Miguel: versão distribuída.
- [nome]: sequencial/núcleo comum.
- [nome]: versão paralela.
- [nome]: benchmarks/visualização.
- Citar as principais referências de `docs/referencias.md`.
- Declarar IA como apoio, com revisão e validação do grupo.

## Slide 16 — Demonstração e conclusão (1 a 2 min)

- Executar paralela com threads ou processos.
- Executar servidor distribuído com dois workers.
- Mostrar que as contagens finais coincidem. O benchmark verifica também a igualdade da matriz e do histórico completo. O CLI da paralela imprime as contagens.
- Conclusão: correção preservada; ganho depende do tamanho e do custo de coordenação.

## Comandos de demonstração

```powershell
python src/parallel/fake_news_paralelo.py --backend threads --workers 2 --linhas 100 --colunas 100 --geracoes 10 --espalhadores 0.02 --limiar 2 --semente 42 --kernel otimizado
python src/distributed/server.py --automaticos --workers 2 --port 0 -l 100 -c 100 -g 10 -p 0.02 -t 2 -s 42 --kernel otimizado --saida demo-distribuida.json
python src/distributed/server.py --automaticos --workers 2 --port 0 -l 100 -c 100 -g 10 -p 0.02 -t 2 --bots 0.005 --influenciadores 0.02
```
