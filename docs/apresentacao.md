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

- Mesmos cenários nas três versões.
- Variáveis: tamanho, gerações, percentual inicial e workers.
- Aquecimento separado e cinco repetições; análise pela mediana.
- Speedup contra a sequencial com o mesmo kernel.
- Informar CPU, núcleos, RAM, SO, Python e ambiente a partir do `metadata.json`.

## Slide 10 — Tempo e speedup (2 min)

- Inserir `cenario_*_tempo.png` e `cenario_*_speedup.png` do experimento final.
- Explicar onde o custo de criar processos ou comunicar supera o ganho.
- Não confundir ganho do kernel com speedup paralelo.

## Slide 11 — Eficiência e escalabilidade (1 min)

- Inserir `cenario_*_eficiencia.png`.
- Eficiência = speedup / workers.
- Queda de eficiência indica overhead, barreira, GIL, comunicação ou limite de núcleos.

## Slide 12 — Comunicação e sincronização (1 min)

- `overhead_s = tempo das gerações − caminho crítico de cálculo`.
- Comunicação por geração cresce aproximadamente com workers × colunas, não com toda a matriz.
- Coordenador centralizado é um gargalo possível.

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
- Mostrar hashes iguais e uma extensão ativada.
- Conclusão: correção preservada; ganho depende do tamanho e do custo de coordenação.

## Comandos de demonstração

```powershell
python src/parallel/fake_news_paralelo.py --backend processos --workers 4 --linhas 100 --colunas 100 --geracoes 10
python src/distributed/server.py --automaticos --workers 2 --port 0 -l 100 -c 100 -g 10 -p 0.02 -t 2
python src/distributed/server.py --automaticos --workers 2 --port 0 -l 100 -c 100 -g 10 -p 0.02 -t 2 --bots 0.005 --influenciadores 0.02
```
