# Fake News Distributed Simulation

Trabalho acadêmico de Sistemas Paralelos e Distribuídos que simula a propagação de fake news em uma população representada por uma matriz bidimensional. O projeto compara implementações sequencial, paralela e distribuída, preservando o mesmo comportamento lógico entre todas elas.

**Status:** implementação concluída e validada por testes automatizados. Os resultados versionados identificam o ambiente em que foram medidos; novos resultados devem ser obtidos novamente quando o hardware ou o interpretador mudar.

## Modelo computacional

Cada célula representa uma pessoa e assume um dos estados abaixo:

| Código | Estado | Comportamento |
| --- | --- | --- |
| `0` | Ignorante | Ainda não acredita ou não recebeu a informação. |
| `1` | Espalhador | Acredita e compartilha a informação. |
| `2` | Inativo | Recebeu a informação, mas não a compartilha mais. |

A propagação usa a vizinhança de Moore, com até oito vizinhos. Em cada geração, um ignorante torna-se espalhador ao atingir o limiar configurado, um espalhador torna-se inativo e um inativo permanece inativo. A próxima geração é sempre calculada a partir de uma grade imutável da geração anterior, evitando resultados dependentes da ordem de percurso.

## Implementações

| Versão | Estratégia |
| --- | --- |
| Sequencial | Código original do professor preservado em `src/sequential/fake_news.py` e núcleo comum para comparações controladas. |
| Paralela | Divisão explícita das linhas entre threads ou processos, buffer duplo e barreira por geração. |
| Distribuída | Coordenador e workers TCP, blocos de linhas locais, troca apenas dos halos e barreira coordenada por geração. |

As versões usam os mesmos kernels de referência e otimizado. Testes comparam matriz final, histórico, número de gerações e hash para garantir equivalência.

## Melhorias e extensões

- Probabilidade de convencimento, com sorteio determinístico por célula e geração.
- Influenciadores com peso configurável.
- Bots que permanecem espalhadores.
- Kernel comum otimizado.
- Divisão estática e dinâmica na versão paralela.
- Redução da comunicação distribuída por troca de halos, sem retransmitir a matriz completa a cada geração.
- Protocolo TCP com JSON, prefixo de tamanho, lotes, validações e timeouts.
- Visualização da propagação e métricas de tempo, speedup, eficiência e comunicação.

Os detalhes e a fundamentação das extensões estão em [docs/extensoes-modelo.md](docs/extensoes-modelo.md).

## Requisitos e instalação

- Python 3.10 ou superior.
- A simulação usa apenas a biblioteca padrão.
- `matplotlib` e `Pillow` são usados para gráficos, GIFs e seus testes.

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

No Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Como executar

### Sequencial

```powershell
python src/sequential/fake_news.py
python src/sequential/run_sequential.py -l 300 -c 300 -g 30 -p 0.02 -t 2
```

O primeiro comando executa o código original fornecido pelo professor. O segundo usa a interface comum configurável.

### Paralela

```powershell
python src/parallel/fake_news_paralelo.py --backend threads --workers 4 --linhas 300 --colunas 300 --geracoes 30
python src/parallel/fake_news_paralelo.py --backend processos --workers 4 --linhas 300 --colunas 300 --geracoes 30
```

### Distribuída automática, em uma máquina

```powershell
python src/distributed/server.py --automaticos --workers 4 --port 0 -l 300 -c 300 -g 30 -p 0.02 -t 2
```

O coordenador abre uma porta TCP livre e inicia os workers locais. Eles continuam sendo processos independentes que se comunicam exclusivamente por sockets.

### Distribuída manual, em terminais separados

Terminal do servidor:

```powershell
python src/distributed/server.py --host 0.0.0.0 --port 5000 --workers 2 -l 300 -c 300 -g 30 -p 0.02 -t 2
```

Em cada um dos dois terminais de worker:

```powershell
python src/distributed/worker.py --host 127.0.0.1 --port 5000
```

Para computadores diferentes, substitua `127.0.0.1` pelo IPv4 do servidor, permita conexões TCP à porta no firewall e use a mesma revisão do código em todas as máquinas. O protocolo atual é a versão 3 e rejeita workers incompatíveis.

## Testes

```powershell
python -B -m unittest discover -s tests -v
```

A suíte cobre regras, kernels, extensões, equivalência das três versões, fragmentação TCP, mensagens grandes em lotes, falhas de worker, benchmarks e geração de imagens.

## Experimentos e gráficos

Teste rápido do pipeline:

```powershell
python benchmarks/run_experiments.py --piloto
```

Matriz recomendada para uma medição final:

```powershell
python benchmarks/run_experiments.py --linhas 500 --colunas 500 --geracoes 30 --espalhadores 0.01 0.02 0.05 --limiar 2 --workers 1 2 4 8 --kernel otimizado --repeticoes 5
python benchmarks/analyze.py benchmarks/results/<experimento>
python benchmarks/plot_results.py benchmarks/results/<experimento>
```

Cada cenário usa a mesma grade inicial nas versões comparadas. `raw.csv` contém as medições, `summary.csv` traz medianas, speedup e eficiência, `metadata.json` registra o ambiente, e `figures/` contém os gráficos. Aquecimentos ficam separados em `warmup.csv` e não entram nas estatísticas.

O speedup principal é calculado contra a versão sequencial com o mesmo kernel. O ganho contra o código original do professor aparece separadamente para não misturar otimização algorítmica com paralelismo.

## Estrutura

```text
fake-news-distributed-simulation/
|-- src/
|   |-- common/          # configuração, estados, kernels e extensões
|   |-- sequential/      # original do professor e adaptador sequencial
|   |-- parallel/        # threads e multiprocessing
|   `-- distributed/     # coordenador, workers e protocolo TCP
|-- tests/               # testes automatizados
|-- benchmarks/          # execução, análise, gráficos e visualização
|   `-- results/         # resultados identificados por experimento
|-- docs/                # projeto, referências, análise e apresentação
|-- README.md
|-- requirements.txt
`-- .gitignore
```

## Documentação

- [Versão paralela](docs/versao-paralela.md)
- [Versão distribuída](docs/versao-distribuida.md)
- [Extensões do modelo](docs/extensoes-modelo.md)
- [Referências e uso de IA](docs/referencias.md)
- [Checklist de entrega](docs/checklist-entrega.md)
- [Roteiro da apresentação](docs/apresentacao.md)

## Integrantes e contribuições

Preencher estes dados antes de exportar a apresentação final:

| Integrante | Contribuição principal |
| --- | --- |
| Miguel | Versão distribuída com sockets TCP. |
| `[nome]` | Versão sequencial e núcleo comum. |
| `[nome]` | Versão paralela. |
| `[nome]` | Benchmarks, análise e visualização. |

## Limitações

- Os benchmarks distribuídos automáticos usam processos locais via loopback; uma execução em rede física deve ser identificada separadamente.
- O coordenador centraliza a troca de halos e pode se tornar gargalo.
- Não há autenticação, criptografia, reconexão nem tolerância a falhas, pois o protocolo foi criado para um ambiente acadêmico controlado.
- No CPython tradicional, o GIL limita o ganho das threads em código Python puro; `multiprocessing` permite paralelismo real.
- Os parâmetros das extensões são ilustrativos e não foram calibrados com dados reais.

## Uso acadêmico

O projeto foi desenvolvido colaborativamente com GitHub, branches e Pull Requests. Ferramentas de IA generativa foram utilizadas como apoio à organização, revisão, documentação, implementação e testes. Todo conteúdo permaneceu sob revisão do grupo; medições são produzidas pelos scripts do repositório. A declaração detalhada e as referências estão em [docs/referencias.md](docs/referencias.md).
