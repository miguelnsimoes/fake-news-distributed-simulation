# Extensões do modelo

Três extensões tornam o modelo original mais próximo da propagação real de desinformação, sem perder a equivalência entre as versões sequencial, paralela e distribuída:

| Extensão | O que muda | Opção na CLI | Campo de `Config` | Padrão (= modelo original) |
| --- | --- | --- | --- | --- |
| Probabilidade de convencimento | Cada exposição convence com chance *p*, em vez de convencer sempre | `--probabilidade` | `probabilidade_convencimento` | `1.0` |
| Influenciadores | Parte da população tem mais alcance: uma exposição a um influenciador vale *w* exposições | `--influenciadores`, `--peso-influenciador` | `percentual_influenciadores`, `peso_influenciador` | `0.0`, `3` |
| Bots | Contas automatizadas que espalham em todas as gerações e nunca ficam inativas | `--bots` | `percentual_bots` | `0.0` |

Com os valores padrão, nenhuma extensão é ativada e o código executa exatamente o caminho do modelo original. Os testes de equivalência com `src/sequential/fake_news.py` continuam valendo.

Código: `src/common/modelo.py` (regras), `src/common/core.py` (`preparar_inicio`, `calcular_linhas`) e `src/common/argumentos.py` (opções da CLI). Testes: `tests/test_extensoes.py`.

---

## 1. Decisão central: aleatoriedade que não depende da divisão da matriz

A probabilidade de convencimento exige sorteios. O jeito ingênuo, que é cada thread, processo ou worker usar seu próprio `random`, quebra a exigência do enunciado de que as versões paralela e distribuída preservem o comportamento da sequencial. A sequência de números passaria a depender de quantos workers existem e da ordem em que cada um calcula suas linhas. Com 2 workers o resultado seria diferente do resultado com 4, e nenhum teste poderia provar a corretude.

**Solução: gerador baseado em contador.** O número sorteado para uma célula é uma função pura das suas coordenadas:

```
u = sorteio(semente, geração, i, j) ∈ [0, 1)
```

`sorteio` combina as quatro entradas num inteiro de 64 bits e aplica o finalizador do SplitMix64 (STEELE; LEA; FLOOD, 2014), que espalha bem os bits mesmo quando as entradas diferem em um só valor. É a mesma ideia dos geradores *counter-based* usados em simulações paralelas de grande escala (SALMON et al., 2011):

- **Independe da divisão.** A célula (i, j) recebe o mesmo número na geração *g* qualquer que seja o worker que a calcula, em qualquer versão e com qualquer número de workers.
- **Sem estado compartilhado.** Não há gerador global para proteger com lock nem para sincronizar entre máquinas, e não há custo extra de comunicação.
- **Reprodutível.** A mesma semente produz a mesma simulação; outra semente produz outra trajetória.

Para isso funcionar, cada versão passa ao kernel a **geração** sendo calculada e o **índice global** da linha. Na distribuída, o worker conhece só a própria faixa, então o servidor envia `linha_inicial` na mensagem `iniciar` (ver seção 5).

Os testes de `TestSorteio`, em `tests/test_extensoes.py`, conferem o determinismo, o intervalo [0, 1), a média próxima de 0,5 e que mudar qualquer coordenada muda o número.

## 2. Mapa de tipos de agente

Influenciadores e bots são **tipos** de pessoa, e não estados: uma pessoa continua ignorante, espalhadora ou inativa, mas o tipo dela muda as regras. O tipo fica num mapa separado, fixo durante a simulação (`COMUM = 0`, `INFLUENCIADOR = 1`, `BOT = 2`):

- **Os três estados continuam os mesmos.** Contagens, histórico, hash, critério de parada e protocolo de bordas não mudam.
- **O mapa é criado uma vez, no coordenador** (`criar_tipos`), com um gerador próprio (`random.Random("tipos:<semente>")`). Ligar influenciadores não altera a grade inicial de espalhadores, que continua idêntica à do código original. Isso permite comparar uma simulação com e sem a extensão a partir do mesmo ponto de partida.
- Como em `criar_grade` do original, cada sorteio escolhe uma célula ao acaso; sorteios repetidos caem na mesma célula. Os bots são sorteados por último e prevalecem sobre influenciadores.

---

## 3. As extensões

Os números abaixo vêm de uma grade de 300×300 com 1% de espalhadores iniciais, semente 42 e até 150 gerações, medida na versão sequencial. "Atingidos" é a fração da população que deixou de ser ignorante ao final.

| Cenário | Gerações | Atingidos | Pico de espalhadores (geração) |
| --- | --- | --- | --- |
| Original, limiar 2 | 85 | 7,5% | 0,2% (1) |
| Original, limiar 1 | 21 | 100% | 16,7% (4) |
| Probabilidade 0,30, limiar 1 | 53 | 89,3% | 7,1% (7) |
| Probabilidade 0,15, limiar 1 | 31 | 7,4% | 1,2% (1) |
| Influenciadores 2%, peso 3, limiar 2 | 114 | 85,6% | 1,5% (19) |
| Influenciadores 5%, peso 3, limiar 2 | 72 | 96,8% | 3,0% (15) |
| Bots 0,5%, limiar 2 | 150 (não para) | 70,0% | 2,6% (13) |
| Bots 2%, limiar 2 | 150 (não para) | 96,2% | 10,2% (6) |

### 3.1 Probabilidade de convencimento

**Regra.** Seja *k* o número de exposições de um ignorante, ou seja, de vizinhos espalhando (contando o peso dos influenciadores, seção 3.2). Se *k* ≥ limiar, ele passa a espalhar com probabilidade

```
P(convencer) = 1 − (1 − p)^k
```

isto é, cada exposição é uma tentativa independente com chance *p*. Com *p* = 1 a regra volta a ser o limiar determinístico do original. Com *p* < 1 e nenhuma exposição não há convencimento, mesmo com limiar 0.

**Motivação.** No modelo original a propagação é "tudo ou nada": com limiar 1, toda a população é atingida em 21 gerações; com limiar 2, a notícia quase não se espalha (7,5%). A realidade fica entre esses extremos, porque nem todo mundo que vê uma notícia acredita nela. Os modelos clássicos de boato (DALEY; KENDALL, 1965; MAKI; THOMPSON, 1973) e sua versão em redes (MORENO; NEKOVEE; PACHECO, 2004) usam exatamente uma taxa de transmissão por contato, e não um limiar fixo.

**No que agrega.**
- Dá um parâmetro contínuo que controla a "credibilidade" da notícia e permite estudar como ela muda o alcance.
- Reproduz o **limiar epidêmico** dos processos de propagação em grade, ligados à percolação (GRASSBERGER, 1983): com *p* = 0,30 a notícia atinge 89% da população, e com *p* = 0,15 ela morre cedo (7,4%). Existe um valor crítico de *p* entre os dois, um resultado que vale mostrar na apresentação.
- A combinação com o limiar continua possível: o limiar passa a ser a exposição mínima para alguém sequer considerar a notícia, no espírito dos modelos de limiar de Granovetter (1978).

**Implementação.** `_convence` em `src/common/modelo.py`. No kernel otimizado, o sorteio só é feito para quem já passou do limiar, que costuma ser uma fração pequena das células.

### 3.2 Influenciadores

**Regra.** Uma fração da população é influenciadora. Quando um influenciador está espalhando, cada vizinho conta essa exposição com peso *w* (`--peso-influenciador`, padrão 3) em vez de 1. O peso entra tanto no limiar quanto na probabilidade (*k* soma os pesos).

**Motivação.** Em redes sociais reais o alcance é muito desigual: poucos perfis concentram grande parte da atenção, e alcance e influência não são a mesma coisa (CHA et al., 2010). A escolha de quem "semeia" uma informação determina o tamanho da cascata, e esse é o problema central de maximização de influência (KEMPE; KLEINBERG; TARDOS, 2003).

**No que agrega.**
- Mostra o efeito desproporcional de poucos agentes: com limiar 2, **2% de influenciadores** levam o alcance de **7,5% para 85,6%**, e 5% levam a 96,8%. A notícia que morria passa a dominar a população.
- Gera curvas com pico tardio (geração 15 a 19): a propagação fica "presa" até alcançar um influenciador e então acelera. É um padrão bem diferente do original.

**Por que peso e não um raio de vizinhança maior.** Um influenciador com raio 2 exigiria **duas** linhas de halo, dobrando a comunicação por geração na versão distribuída e mudando a divisão das bordas na paralela. Com o peso, a vizinhança continua de Moore (raio 1), o halo continua com 1 linha, e o custo de comunicação por geração não muda.

### 3.3 Bots

**Regra.** Uma fração da população é bot. Bots começam espalhando e **nunca** ficam inativos: em toda geração continuam como espalhadores e expõem os vizinhos.

**Motivação.** Contas automatizadas tiveram papel desproporcional na amplificação de conteúdo de baixa credibilidade, sobretudo nos primeiros momentos da propagação (SHAO et al., 2018; FERRARA et al., 2016). No modelo original todo espalhador perde o interesse depois de uma geração; um bot não perde.

**No que agrega.**
- Introduz uma fonte permanente: **0,5% de bots** levam o alcance de 7,5% para **70%** com limiar 2.
- Muda a dinâmica qualitativamente: como sempre há espalhadores, o critério de parada original ("nenhum espalhador") nunca é atingido e a simulação roda todas as gerações pedidas. Isso é coerente com o fenômeno e mostra um limite do critério de parada original.
- Abre espaço para discutir que o efeito dos bots é tema debatido na literatura: Vosoughi, Roy e Aral (2018) observaram que, no Twitter, bots aceleraram notícias falsas e verdadeiras na mesma proporção, e que a diferença vinha das pessoas.

**Implementação.** `aplicar_bots` coloca os bots como espalhadores na grade inicial. O kernel otimizado ajusta as posições de bot no fim de cada linha com `bytes.find`, sem percorrer todas as células.

---

## 4. Custo computacional

Tempo por geração na versão sequencial, kernel otimizado, grade de 300×300 (mediana de 3 execuções):

| Cenário | ms por geração | Em relação ao original |
| --- | --- | --- |
| Original (limiar 2) | 14,5 | 1,0× |
| Probabilidade 0,30 | 17,2 | ~1,2× |
| Influenciadores 2% | 26,1 | ~1,8× |
| Bots 0,5% | 13,3 | ~1,0× |

- **Probabilidade:** o custo extra são os sorteios, feitos só para quem passou do limiar.
- **Influenciadores:** cada linha que contém um influenciador precisa somar exposições com peso, célula a célula, em vez do atalho com `bytes.translate`. Linhas sem influenciador continuam no caminho rápido.
- **Bots:** custo desprezível.
- No kernel `referencia`, o tempo por geração depende de quantos ignorantes existem (só eles olham os vizinhos), então ele mede mais a dinâmica do que o custo da extensão.

**Comunicação.** Nenhuma extensão aumenta a comunicação por geração na distribuída: os halos continuam com 1 linha, e os sorteios não precisam de troca de mensagens. O único custo novo é enviar, uma vez no início, o mapa de tipos da faixa de cada worker (com as linhas do halo) e os parâmetros do modelo.

**Memória.** Na paralela com processos, cada worker recebe uma cópia do mapa de tipos (1 byte por pessoa), porque a divisão dinâmica pode dar a ele qualquer linha.

## 5. Como cada versão usa as extensões

- **Sequencial:** `core.preparar_inicio(config)` devolve `(grade, tipos, modelo)`; `core.evoluir` passa a geração e o índice de linha ao kernel estendido.
- **Paralela:** `simular_paralelo(..., modelo=..., tipos=...)`. O mapa de tipos vai em cada tarefa como tupla de `bytes` (somente leitura, sem lock), e `_calcular_faixa` passa ao kernel a geração e o índice global da linha.
- **Distribuída (protocolo versão 3):** a mensagem `iniciar` passou a levar `modelo` (parâmetros), `linha_inicial` (índice global da primeira linha da faixa) e `tem_tipos`. Se houver tipos, o servidor envia logo depois da grade, em lotes, as linhas de tipo da faixa mais as do halo. O worker monta o mesmo alinhamento da fatia e chama `calcular_linhas` com `indice_global = linha_inicial − offset`. Servidor e worker de versões diferentes recusam a conexão.

## 6. Testes (`tests/test_extensoes.py`)

- **Sorteio:** determinismo, intervalo, média e sensibilidade a cada coordenada.
- **Parâmetros:** os padrões desligam as extensões; valores inválidos geram `ValueError`; o mapa de tipos é reprodutível e não altera a grade inicial.
- **Semântica:**
  - *p* = 1 reproduz o modelo original;
  - a taxa de convencimento medida segue *p* com 1 exposição e segue 1 − (1 − *p*)^*k* com 2 e 3 exposições;
  - o influenciador vale *w* exposições só quando está espalhando;
  - bots nunca ficam inativos, e a simulação roda todas as gerações.
- **Dois kernels independentes:** `linha_estendida_referencia` (especificação célula a célula) e `linha_estendida_otimizada` dão o mesmo resultado em 30 grades, tipos e parâmetros aleatórios.
- **Equivalência das versões:** para cada extensão isolada e para todas juntas, a paralela (threads com 1, 2 e 5 workers, divisão estática e dinâmica; processos com 3 workers) e a distribuída (1, 3 e 30 workers, mais workers que linhas) produzem histórico e hash idênticos aos da sequencial.

## 7. Como executar

```sh
# Sequencial
python src/sequential/run_sequential.py -l 300 -c 300 -g 150 -p 0.01 -t 1 --probabilidade 0.3
python src/sequential/run_sequential.py -l 300 -c 300 -g 150 -p 0.01 -t 2 --influenciadores 0.02 --peso-influenciador 3
python src/sequential/run_sequential.py -l 300 -c 300 -g 150 -p 0.01 -t 2 --bots 0.005

# Paralela e distribuída: mesmas opções
python src/parallel/fake_news_paralelo.py --linhas 300 --colunas 300 --geracoes 150 --espalhadores 0.01 \
    --limiar 2 --bots 0.005 --influenciadores 0.02 --backend processos -w 4
python src/distributed/server.py --automaticos --workers 4 --port 0 -l 300 -c 300 -g 150 -p 0.01 -t 2 \
    --bots 0.005 --influenciadores 0.02
```

Com a mesma semente e os mesmos parâmetros, as três versões imprimem o mesmo hash final.

### Nos benchmarks

As mesmas opções existem em `benchmarks/run_experiments.py` e aceitam listas, que entram no produto cartesiano dos cenários. Exemplo comparando o modelo original com cada extensão:

```sh
python benchmarks/run_experiments.py --linhas 500 --colunas 500 --geracoes 60 --espalhadores 0.01 \
    --limiar 2 --workers 1 2 4 8 --bots 0 0.005 --influenciadores 0 0.02
python benchmarks/analyze.py benchmarks/results/<experimento>
python benchmarks/plot_results.py benchmarks/results/<experimento>
```

- Os parâmetros das extensões ficam em colunas próprias do `raw.csv` e do `summary.csv` (`probabilidade`, `influenciadores`, `peso_influenciador`, `bots`) e aparecem no título dos gráficos.
- O código original não implementa as extensões, então os cenários com extensões **não** rodam o sequencial `professor`. A referência de correção passa a ser o sequencial do núcleo com o mesmo kernel, e `ganho_vs_sequencial` é calculado contra ele.
- Sem influenciadores o peso não tem efeito, e o executor não repete o cenário para cada peso.

## 8. Limitações

- A população continua numa grade regular com vizinhança de Moore. Redes sociais reais têm estrutura de grafo (poucos nós muito conectados), que um influenciador com peso só aproxima.
- Os parâmetros (*p*, *w* e percentuais) são ilustrativos, não calibrados com dados reais.
- Com bots, a simulação só para pelo limite de gerações. Um critério extra (por exemplo, nenhuma mudança de estado entre duas gerações) seria uma extensão natural.
- Os tempos da seção 4 vêm de uma medição da versão sequencial; os custos nas versões paralela e distribuída devem sair dos experimentos da Fase 2, com `run_experiments.py`.

## Referências

- CHA, M.; HADDADI, H.; BENEVENUTO, F.; GUMMADI, K. P. Measuring user influence in Twitter: the million follower fallacy. In: *International AAAI Conference on Weblogs and Social Media (ICWSM)*, 2010.
- DALEY, D. J.; KENDALL, D. G. Stochastic rumours. *IMA Journal of Applied Mathematics*, v. 1, n. 1, p. 42–55, 1965.
- FERRARA, E.; VAROL, O.; DAVIS, C.; MENCZER, F.; FLAMMINI, A. The rise of social bots. *Communications of the ACM*, v. 59, n. 7, p. 96–104, 2016.
- GRANOVETTER, M. Threshold models of collective behavior. *American Journal of Sociology*, v. 83, n. 6, p. 1420–1443, 1978.
- GRASSBERGER, P. On the critical behavior of the general epidemic process and dynamical percolation. *Mathematical Biosciences*, v. 63, n. 2, p. 157–172, 1983.
- KEMPE, D.; KLEINBERG, J.; TARDOS, É. Maximizing the spread of influence through a social network. In: *ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 2003, p. 137–146.
- MAKI, D. P.; THOMPSON, M. *Mathematical Models and Applications*. Englewood Cliffs: Prentice-Hall, 1973.
- MORENO, Y.; NEKOVEE, M.; PACHECO, A. F. Dynamics of rumor spreading in complex networks. *Physical Review E*, v. 69, n. 6, 066130, 2004.
- SALMON, J. K.; MORAES, M. A.; DROR, R. O.; SHAW, D. E. Parallel random numbers: as easy as 1, 2, 3. In: *International Conference for High Performance Computing, Networking, Storage and Analysis (SC '11)*, 2011.
- SHAO, C.; CIAMPAGLIA, G. L.; VAROL, O.; YANG, K.-C.; FLAMMINI, A.; MENCZER, F. The spread of low-credibility content by social bots. *Nature Communications*, v. 9, 4787, 2018.
- STEELE, G. L.; LEA, D.; FLOOD, C. H. Fast splittable pseudorandom number generators. In: *ACM SIGPLAN International Conference on Object-Oriented Programming, Systems, Languages, and Applications (OOPSLA)*, 2014, p. 453–472.
- VOSOUGHI, S.; ROY, D.; ARAL, S. The spread of true and false news online. *Science*, v. 359, n. 6380, p. 1146–1151, 2018.

Confira os dados de cada referência (páginas, volume, DOI) na fonte original antes de usá-los nos slides.
