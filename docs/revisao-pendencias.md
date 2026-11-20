# Revisão da branch `develop` e lista de pendências

Data da revisão: 18/11/2026. Commit revisado: `87cdce3` (merge do PR #8, simulação distribuída).

Este documento compara o estado atual do repositório com o enunciado do trabalho e lista o que ainda falta, por prioridade. Cada item diz **o que** fazer, **por que** (qual requisito ou critério de avaliação ele atende) e **onde** mexer.

---

## 1. Resumo da situação

| Requisito do enunciado | Situação | Observação |
| --- | --- | --- |
| Versão sequencial funcional | ✅ Pronto | Original preservado em `src/sequential/fake_news.py`; núcleo refatorado em `src/common/core.py`. |
| Versão paralela (threads/multiprocessing) | ✅ Pronto | Bem feita e documentada: buffer duplo, barreira, divisão estática/dinâmica, testes de falha. |
| Versão distribuída (sockets) | ⚠️ Funciona, falta validar | Funciona com processos locais via TCP, com halos. **Não foi testada entre máquinas físicas.** |
| Equivalência lógica entre as versões | ✅ Pronto | Testes comparam histórico, hash e matriz com o código do professor. |
| Experimentos variando tamanho, gerações, % de espalhadores, threads e hosts | ❌ Incompleto | Só existem resultados da paralela. Nenhum resultado distribuído, nenhum com vários hosts e nenhuma variação de % de espalhadores. |
| Speedup, eficiência e gargalos das **três** versões | ❌ Incompleto | Análise ótima da paralela em `docs/versao-paralela.md`; a distribuída não tem análise com números. |
| Configuração experimental | ⚠️ Parcial | Só a máquina do Pedro (paralela). Falta a(s) máquina(s) da distribuída e a rede. |
| Melhorias e extensões do **modelo** | ❌ Nenhuma | Só há melhorias computacionais. Nenhuma extensão do modelo (influenciadores, bots, probabilidades etc.). |
| Referências bibliográficas | ⚠️ Parcial | Boas na paralela; poucas na distribuída; nenhuma sobre o modelo além de Daley-Kendall; falta declarar o uso de IA. |
| Disponível no GitHub | ⚠️ Risco | `main` tem só o commit inicial; todo o trabalho está em `develop` (14 commits à frente). |
| README / instruções de execução | ❌ Desatualizado | O README ainda diz que a distribuída está "Planejada", a árvore de pastas está velha e os integrantes estão "A preencher". |
| Apresentação (PDF), contribuição individual | ❌ Não iniciado | Nada no repositório. |

A suíte de testes roda: **63 testes passam**. Os 2 erros restantes são `ImportError` de `matplotlib` e `Pillow` (`test_plot_results`, `test_visualize`), porque o `requirements.txt` está vazio.

---

## 2. Prioridade ALTA: afeta nota diretamente ou invalida a comparação

### 2.1 As três versões não usam o mesmo kernel, então a comparação de desempenho fica injusta

**Problema.** A paralela usa por padrão o kernel `otimizado` (`src/parallel/regras.py`), cerca de 7 a 11 vezes mais rápido por célula. A distribuída usa `calcular_faixa` de `core.py`, o kernel de referência célula a célula. Os benchmarks (`run_experiments.py`, `varredura.py`) comparam com o código do professor, com `deepcopy`. Existem hoje **três "sequenciais" diferentes**: professor, `core.simular` e kernel otimizado com 1 worker.

Medição feita nesta revisão (400×400, 30 gerações, 2% de espalhadores, limiar 2, macOS, Python 3.13):

| Workers | Sequencial (`core`) | Distribuída (TCP local) | Paralela (processos, kernel otimizado) |
| --- | --- | --- | --- |
| 1 | 4,81 s | 5,01 s | 0,64 s |
| 2 | | 2,47 s | 0,31 s |
| 4 | | 1,30 s | 0,17 s |
| 8 | | 1,09 s | 0,14 s |

Se essas colunas forem para o mesmo gráfico, vai parecer que a distribuída é 8 vezes pior que a paralela. A maior parte dessa diferença é kernel, não comunicação.

**O que fazer.**
1. Mover os kernels (`linha_referencia`, `linha_otimizada`) para `src/common/` e deixar **todas** as versões escolherem o kernel (`--kernel referencia|otimizado`), inclusive a sequencial e o worker distribuído.
2. Definir oficialmente qual é a linha de base do speedup (sugestão: sequencial com o **mesmo** kernel da versão comparada) e escrever isso no README e nos slides.
3. Apresentar o ganho do kernel otimizado separado, como **melhoria de otimização computacional**, igual ao que `docs/versao-paralela.md` já faz.

### 2.2 A distribuída não está no pipeline de benchmarks

**Problema.** `benchmarks/adapters.py` e `benchmarks/run_experiments.py` só conhecem `sequencial`, `threads` e `processos`. A própria `docs/versao-distribuida.md` registra isso como pendência. Não existe nenhum CSV de resultado da distribuída.

**O que fazer.**
- Criar `adapters.executar_distribuido(...)` que chame `executar_servidor` e devolva `ResultadoBenchmark` (registrar `tempo_s` como `tempo_geracoes_s`, `metricas["total_s"]` como `tempo_total_s` e as métricas de comunicação em colunas extras).
- Adicionar o backend `distribuida` em `run_experiments.py` e a coluna `implementacao=distribuida` em `analyze.py`, que hoje classifica tudo que não é `sequencial` como `paralela` (linha 79).
- Incluir colunas de custo de comunicação: `celulas_halo_enviadas`, `envio_coordenador_s`, `recepcao_espera_coordenador_s`, `caminho_critico_calculo_s` e o overhead (`tempo_s − caminho_critico_calculo_s`). Isso cobre o item "análise de custo de comunicação" do enunciado.

### 2.3 Experimentos não variam todos os parâmetros exigidos

O enunciado pede para variar **tamanho da matriz, número de gerações, percentual inicial de espalhadores, número de threads e número de hosts/processos**, com os **mesmos cenários** nas três versões.

| Parâmetro | Situação atual |
| --- | --- |
| Tamanho da matriz | `run_experiments.py` aceita uma lista ✅ |
| Gerações | aceita uma lista ✅ |
| % de espalhadores | **um valor só** (`--espalhadores`, sem `nargs="+"`) ❌ |
| Threads/processos | ✅ |
| Hosts distribuídos | **não suportado** ❌ |

**O que fazer.**
- Fazer `--espalhadores` (e, opcionalmente, `--limiar`) aceitar listas e entrar no produto cartesiano dos cenários.
- Definir uma **matriz de experimentos oficial** e rodar tudo nela, por exemplo:
  - tamanhos: 250², 500², 1000², 2000²
  - gerações: 10, 30, 100 (com limiar 2, para que rodem de fato)
  - espalhadores: 1%, 2%, 5%, 10%
  - workers: 1, 2, 4, 8 (e 16 se a máquina tiver)
  - hosts: 1, 2, 3, 4 máquinas
- Sempre registrar **gerações executadas** além das pedidas (com limiar 3 a propagação morre em 2 a 4 gerações; o grupo já descobriu isso).
- Rodar os três tipos **na mesma máquina** para a comparação sequencial × paralela × distribuída local, e em seguida a distribuída em várias máquinas.

### 2.4 A distribuída nunca rodou em máquinas diferentes

A própria `docs/versao-distribuida.md` admite: "A conectividade entre computadores físicos precisa ser testada". O enunciado pede "múltiplos processos/**máquinas**" e "número de **hosts**", e a apresentação exige **demonstrar** a execução.

**O que fazer.**
- Testar com 2 a 4 notebooks na mesma rede (servidor com `--host 0.0.0.0`, workers com `--host <IP>`), liberando a porta no firewall de cada sistema (Windows Defender, macOS).
- Registrar a rede (Wi-Fi ou cabo, latência medida com `ping`) na configuração experimental.
- Preparar um **plano B** para o dia: hotspot do celular ou roteador próprio, porque a rede da universidade costuma bloquear conexões entre clientes. Também vale gravar um vídeo da execução multi-máquina como reserva.
- Ajustar `--timeout` (padrão de 30 s): no modo manual, se alguém demora mais de 30 s para iniciar o último worker, os primeiros caem.

### 2.5 Nenhuma melhoria ou extensão do **modelo** (até 3,0 pontos)

Cada melhoria vale até 0,5 ponto, com teto de 3,0. Hoje existem melhorias **computacionais** que já dá para documentar como tal:

| Melhoria já existente | Categoria do enunciado | Onde está |
| --- | --- | --- |
| Balanceamento dinâmico de carga (pedaços sob demanda) | balanceamento dinâmico de carga | `fake_news_paralelo.py` |
| Kernel otimizado (soma por colunas, ~11× mais rápido) | otimizações computacionais | `regras.py` |
| Troca só de halos e codificação compacta das linhas | redução de comunicação distribuída | `protocol.py`, `server.py` |
| Animação GIF/PNG da propagação | visualização gráfica | `benchmarks/visualize.py` |
| Métricas de desbalanceamento, sincronização e caminho crítico | estatísticas adicionais | `varredura.py`, `server.py` |
| Python free-threaded (sem GIL) e achado do EcoQoS do Windows | análise/otimização | `docs/versao-paralela.md`, `energia.py` |

Falta **qualquer extensão do modelo em si**, que é a parte mais visível na apresentação. Sugestões, da mais simples para a mais complexa:

1. **Probabilidade de convencimento** (em vez de limiar fixo): cada vizinho espalhador convence com probabilidade *p*.
2. **Resistência / céticos**: um 4º estado imune, ou resistência individual por célula.
3. **Esquecimento / reincidência**: um espalhador vira inativo com probabilidade *q* (modelo Maki-Thompson) em vez de sempre após 1 geração.
4. **Influenciadores**: células com raio de vizinhança maior ou peso maior no convencimento.
5. **Bots**: espalhadores permanentes que nunca ficam inativos.
6. **Múltiplas fake news simultâneas**: estado vira um par (notícia, estado).

**Cuidado técnico importante.** Qualquer regra aleatória quebra a equivalência entre as versões se cada thread ou worker usar o próprio `random`. Para manter "o comportamento lógico da versão sequencial", o número aleatório de cada célula precisa ser uma **função determinística de (semente, geração, i, j)**, por exemplo um hash; ou cada célula usa um gerador próprio. Assim o resultado não depende de como a matriz foi dividida, e os testes de equivalência continuam valendo. Isso também é um ótimo ponto técnico para explicar na arguição.

Cada extensão precisa entrar nas **três** versões (ou no núcleo comum `core.py`/`regras.py`, que já é compartilhado), ter teste de equivalência, ser parametrizável pela CLI (desligada por padrão, para que os testes contra o professor continuem passando) e ser documentada com justificativa e referência.

---

## 3. Prioridade MÉDIA: qualidade e organização do código (1,0 ponto)

### 3.1 Código duplicado entre as versões

O núcleo comum (`src/common/core.py`) existe, mas a paralela e os benchmarks não o usam:

| Item | Definido em |
| --- | --- |
| Constantes `IGNORANTE/ESPALHADOR/INATIVO` | `fake_news.py`, `core.py`, `regras.py` |
| `criar_grade` | `fake_news.py` (com `random.seed` **global**), `core.py`; a paralela importa a do professor |
| `dividir_linhas` | `core.py` (devolve `range`), `fake_news_paralelo.py` (devolve tuplas) |
| Tipo do resultado | `core.Resultado`, `ResultadoSimulacao`, `ResultadoBenchmark`, `ResultadoDistribuido` |
| Formato do histórico | dicts em `core`, tuplas na paralela e nos benchmarks |
| Pipeline de benchmark | `src/parallel/varredura.py` **e** `benchmarks/run_experiments.py`, com esquemas de CSV diferentes |

**O que fazer:** fazer a paralela importar constantes, `criar_grade` e `dividir_linhas` de `common.core`, mover os kernels para `common/` (item 2.1), escolher **um** pipeline de benchmark (sugestão: `benchmarks/`, absorvendo as métricas extras da `varredura.py`) e manter `varredura.py` só como ferramenta da paralela ou removê-la.

### 3.2 Manipulação de `sys.path` em todo arquivo

Cada script faz `sys.path.insert(...)` de um jeito, e `docs/interface.md` já documenta um bug causado por isso (nome de arquivo igual ao da pasta). Os imports dependem de como o script é chamado (`if __package__: from .protocol ... else: from protocol ...`).

**O que fazer:** transformar `src/` em pacote (um `__init__.py` em cada pasta e um `pyproject.toml` mínimo) e executar com `python -m distributed.server`, `python -m parallel.fake_news_paralelo` etc., ou instalar com `pip install -e .`. Isso remove todos os `sys.path.insert` e os `# noqa: E402`.

### 3.3 Dependências e versão do Python

- O `requirements.txt` está vazio, mas `benchmarks/plot_results.py` e `visualize.py` precisam de `matplotlib` e os testes precisam de `Pillow`. Resultado: `python -m unittest discover` falha em uma máquina limpa. Preencher `requirements.txt` (com versões) ou fazer esses testes usarem `skipUnless` quando a biblioteca não estiver instalada.
- `docs/interface.md` diz "Python 3.8+", mas o código usa `tuple[int, int, int]` em tempo de execução (precisa de 3.9+) e a documentação da paralela usa 3.14. Definir a versão mínima (sugestão: 3.10+) no README.

### 3.4 Documentação desatualizada ou inconsistente

- **README.md**: o status diz que só existe a sequencial; a distribuída aparece como "Planejada"; a árvore de diretórios está desatualizada; não há seção "Executar a versão distribuída", nem benchmarks, gráficos ou testes; os integrantes estão "A preencher"; "Tecnologias" omite `socket`, `matplotlib` e `Pillow`.
- `docs/interface.md` cita nomes de responsáveis "(Pedro)", "(Miguel)" e termina com sugestões que já foram implementadas (o limite de 1 MiB já foi resolvido com lotes). Atualizar ou consolidar.
- Os exemplos de `docs/versao-distribuida.md` usam blocos `powershell`; incluir também os comandos para Linux/macOS (`python3`).
- Os arquivos `.txt` em `benchmarks/results/paralelo/` têm linhas em branco duplicadas (CRLF convertido) e um caminho absoluto de pasta temporária do computador de um integrante. Limpar.

### 3.5 Comentários e docstrings

Os módulos já estão bem comentados. Para o critério de "códigos comentados", vale padronizar: um docstring de módulo em todo arquivo (`distribuida.py` e `protocol.py` são bem curtos), docstrings em funções públicas sem documentação (`receber_estado`, `decodificar_linha`, `main`) e comentários em português, em um único estilo.

---

## 4. Melhorias técnicas na versão distribuída (cada uma pode virar "melhoria")

1. **Topologia em estrela: o coordenador é gargalo.** Hoje cada halo vai worker → servidor → worker vizinho (2 saltos e 2 serializações JSON), e o servidor envia e recebe de cada worker **em sequência**. Alternativa: troca direta de halos entre workers vizinhos (cada worker abre conexão com o de cima e o de baixo), com o servidor só agregando contagens. Medir o antes e o depois e apresentar como "redução de comunicação distribuída".
2. **Serialização.** As linhas viajam como texto `"0120..."` dentro de JSON. Enviar `bytes` crus com cabeçalho binário (`struct`) reduz CPU de codificação e decodificação. Dá para comparar com a métrica `envio_s`.
3. **Contagem redundante.** O worker chama `contar_estados(grade)` sobre a faixa inteira a cada geração, uma segunda varredura. `calcular_faixa` pode devolver as contagens junto (a paralela já faz isso).
4. **Cálculo sobreposto à comunicação.** O worker pode calcular primeiro as linhas internas (que não dependem dos halos) enquanto espera os halos, e só depois as duas linhas de borda. É uma otimização clássica de decomposição de domínio (Foster, Grama et al.).
5. **Kernel otimizado no worker** (item 2.1).
6. **`energia.py` não é chamado na distribuída.** A própria doc da paralela pede isso para servidor e workers no Windows; sem isso, os tempos da distribuída ficam distorcidos em comparação à paralela.
7. **Robustez (opcional):** não há autenticação, reconexão ou tolerância a falhas. Basta citar como limitação nos slides; não precisa implementar.

---

## 5. Prioridade MÉDIA: análise de resultados (1,0 ponto)

O que o enunciado exige e ainda não existe para as **três** versões juntas:

- [ ] Tabela comparativa sequencial × paralela (threads, processos) × distribuída (1 host, N hosts) nos mesmos cenários.
- [ ] Gráficos de tempo, speedup e eficiência por número de workers/hosts (já existe `plot_results.py`; falta incluir a distribuída).
- [ ] Gráfico de speedup × tamanho da matriz (mostra onde a distribuída começa a compensar).
- [ ] Gráfico de speedup × % de espalhadores e × gerações (exigidos como variáveis).
- [ ] Análise de custo de comunicação da distribuída: overhead = `tempo_s − caminho_critico_calculo_s`, células de halo por geração e comparação local × rede real.
- [ ] Análise de sincronização da distribuída (barreira no coordenador).
- [ ] Lei de Amdahl/Gustafson aplicada às três versões (já existe para a paralela).
- [ ] Configuração experimental completa de **cada** máquina usada (CPU, núcleos, RAM, SO, versão do Python, rede).
- [ ] Gráficos da propagação em si (curvas de ignorantes/espalhadores/inativos por geração), úteis para explicar o modelo.

Dica: as medições da paralela foram em Windows com Python 3.14; se a distribuída for medida em outra máquina ou SO, a comparação direta não vale. Rodar ao menos um conjunto completo das três versões **na mesma máquina**.

---

## 6. Entregáveis que ainda não existem

### 6.1 Referências e declaração de uso de IA
- [ ] Consolidar uma seção única de referências (README ou `docs/referencias.md`) e citar nos slides.
- [ ] Faltam referências sobre o **modelo**: modelos de boato DK/MK, autômatos celulares aplicados a rumores e fake news (há artigos em IEEE/ACM/Scopus, por exemplo de propagação de rumores em redes sociais com autômatos celulares) e decomposição de domínio com *ghost cells*/halos para a distribuída.
- [ ] A versão distribuída só cita a documentação do Python e Foster.
- [ ] **Declarar o uso de IA generativa.** O enunciado exige que "toda utilização de código externo, IA generativa [...] deve ser devidamente referenciada". Há indícios de uso de IA no repositório (por exemplo, um caminho de pasta do Claude em `benchmarks/results/paralelo/*.txt`). Escrever uma seção "Uso de IA" dizendo onde e como foi usada, inclusive nesta revisão.

---

## 7. Pontos positivos (manter e destacar na apresentação)

- Original do professor intacto e usado como gabarito nos testes.
- Testes de equivalência fortes: hash e histórico, várias sementes, mais workers que linhas, matriz 1×1, zero gerações, falha injetada em worker sem deadlock.
- Paralela com correção bem argumentada (buffer duplo, dono único por linha, uma barreira por geração, contagem sem lock) e validada no Python sem GIL.
- Análise de desempenho da paralela de alto nível (desbalanceamento, caminho crítico, achado do EcoQoS, tabela limiar × % de espalhadores).
- Protocolo da distribuída robusto: prefixo de tamanho, validação de mensagens, envio da grade em lotes, timeouts, encerramento limpo dos processos.

---

## 8. Checklist resumido por ordem sugerida

1. [ ] Preencher `requirements.txt` e definir a versão do Python; deixar a suíte 100% verde.
2. [x] Unificar o núcleo: kernels em `common/`, paralela usando `common.core`, opção `--kernel` em todas as versões.
3. [x] Integrar a distribuída em `adapters.py`, `run_experiments.py` e `analyze.py`, com métricas de comunicação.
4. [ ] ~~Fazer `--espalhadores` aceitar lista~~ (feito, junto com `--limiar`); falta definir a matriz oficial de experimentos.
5. [ ] Testar a distribuída em 2 a 4 máquinas reais; preparar o plano B de rede.
6. [ ] Implementar 2 ou 3 extensões do modelo com aleatoriedade determinística por célula, nas três versões, com testes.
7. [ ] (Opcional) Troca direta de halos entre workers e/ou serialização binária; medir antes e depois.
8. [ ] Rodar todos os experimentos; gerar tabelas e gráficos; escrever a análise das três versões.
9. [ ] Atualizar o README (estrutura, como rodar cada versão, integrantes) e consolidar as referências e a declaração de IA.
10. [ ] Montar os slides (PDF), dividir as falas, ensaiar a demonstração ao vivo.
11. [ ] Gerar o `.zip` final.
