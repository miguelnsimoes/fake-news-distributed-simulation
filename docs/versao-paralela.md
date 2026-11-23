# Versão paralela

Responsável: Pedro. Código em `src/parallel/`, testes em
`tests/test_paralelo.py`.

## Como rodar

Tudo a partir da raiz do repositório, só com a biblioteca padrão do Python.

```sh
# Uma simulação (mesma saída do código do professor, com o tempo separado)
python src/parallel/fake_news_paralelo.py --workers 4 --backend threads
python src/parallel/fake_news_paralelo.py --workers 8 --backend processos --linhas 1000 --colunas 1000 --limiar 2

# Medição variando o número de workers (tabela com speedup e eficiência)
python src/parallel/varredura.py --linhas 1000 --colunas 1000 --geracoes 30 --limiar 2 \
    --espalhadores 0.02 --backend threads processos --workers 1 2 4 8 16 \
    --repeticoes 3 --sequencial --csv benchmarks/results/paralelo.csv

# Testes de equivalência com o código do professor
python -m unittest discover -s tests -v
```

Para as threads terem paralelismo de verdade, use o Python _free-threaded_ (sem
GIL). Ele é um build oficial do CPython 3.14 e não muda nada no código:

```sh
# com uv (instala numa pasta própria, sem mexer no Python do sistema nem no PATH)
uv python install 3.14t --no-bin
uv run --python 3.14t src/parallel/varredura.py --backend threads --workers 1 2 4 8

# ou com o Python Install Manager do Windows
py install 3.14t
python3.14t src/parallel/varredura.py --backend threads --workers 1 2 4 8
```

A primeira linha que a varredura imprime mostra se o GIL está ativo ou
desligado.

| Opção                                                                            | Valores                   | Para que serve                                                                |
| -------------------------------------------------------------------------------- | ------------------------- | ----------------------------------------------------------------------------- |
| `--backend`                                                                      | `threads`, `processos`    | `threading` ou `multiprocessing`                                              |
| `--workers` (`--threads`)                                                        | inteiro ≥ 1               | quantas threads/processos dividem a matriz                                    |
| `--kernel`                                                                       | `otimizado`, `referencia` | como cada linha é calculada (ver abaixo)                                      |
| `--divisao`                                                                      | `estatica`, `dinamica`    | blocos fixos ou pedaços distribuídos sob demanda (ver abaixo)                 |
| `--pedaco`                                                                       | inteiro ≥ 1               | linhas por pedaço na divisão dinâmica (padrão: cerca de 8 pedaços por worker) |
| `--linhas`, `--colunas`, `--geracoes`, `--espalhadores`, `--limiar`, `--semente` |                           | mesmos parâmetros do código do professor                                      |

## Arquivos

| Arquivo                 | O que faz                                                                                                                                                                        |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regras.py`             | Reexporta os kernels, que agora ficam em `src/common/kernels.py` e são usados pelas três versões: a regra aplicada a **uma linha** (recebe as linhas `i-1`, `i`, `i+1` e devolve a nova linha `i`). Não sabe nada de threads. |
| `fake_news_paralelo.py` | Divide as linhas entre os workers, sincroniza as gerações e junta o resultado. Os dois backends usam o mesmo laço de worker.                                                     |
| `varredura.py`          | Mede tempos variando o número de workers, calcula speedup, eficiência, desbalanceamento e tempo de sincronização, confere se o resultado é idêntico ao do professor e grava CSV. |
| `energia.py`            | Reexporta `src/common/energia.py`, que impede que o Windows 11 rebaixe o processo para os núcleos de economia no meio da medição (ver "Achado 2"). Também é chamado pelo servidor e pelos workers da distribuída. |

## Como a matriz é dividida

A matriz é cortada em **blocos contíguos de linhas**, um por worker. Os blocos
têm o mesmo tamanho (diferença de no máximo uma linha), e cada worker calcula
sempre o mesmo bloco.

```text
 geração g (origem, só leitura)            geração g+1 (destino)
┌────────────────────────────────┐       ┌────────────────────────────────┐
│ linhas   0–249   worker 0      │ ────▶ │ linhas   0–249   só o worker 0 │
│ linhas 250–499   worker 1      │ ────▶ │ linhas 250–499   só o worker 1 │
│ linhas 500–749   worker 2      │ ────▶ │ linhas 500–749   só o worker 2 │
│ linhas 750–999   worker 3      │ ────▶ │ linhas 750–999   só o worker 3 │
└────────────────────────────────┘       └────────────────────────────────┘
 O worker 1 também LÊ as linhas 249 e 500 (fronteiras), mas nunca escreve nelas.
         ─── barreira ─── na geração seguinte os papéis das grades se invertem
```

Por que linhas:

- Pela vizinhança de Moore, a linha `i` da próxima geração depende só das linhas
  `i-1`, `i` e `i+1`. Um bloco de linhas precisa ler apenas **duas linhas de
  fronteira** dos vizinhos.
- Uma linha é um pedaço contíguo de memória (`bytes`), então ler e escrever uma
  linha inteira é uma cópia só.
- A mesma divisão serve para a versão distribuída: cada worker remoto precisaria
  receber só as duas linhas de fronteira por geração.

### Divisão dinâmica (melhoria: balanceamento de carga)

Na divisão estática, a geração só termina quando o worker mais lento termina.
Num processador híbrido como o i5-13450HX (6 núcleos P rápidos + 4 núcleos E
mais lentos), quem cai num núcleo E ou divide um núcleo com hyper-threading
atrasa todo mundo na barreira.

Na divisão dinâmica (`--divisao dinamica`), as linhas são cortadas em pedaços
pequenos (por padrão, cerca de 8 por worker). A cada geração, cada worker pega o
número do próximo pedaço livre num contador compartilhado e calcula aquele
pedaço, até os pedaços acabarem. Quem está num núcleo rápido pega mais pedaços.

- O contador é protegido por um lock (`threading.Lock` ou
  `multiprocessing.Lock`), o que garante que cada pedaço vai para um único
  worker. O lock é pego uma vez por pedaço, não por linha nem por célula.
- Existe um contador para cada paridade de geração. O fluxo principal zera o
  contador da geração `g` logo depois da barreira de `g`. Ninguém volta a usá-lo
  antes da geração `g+2`, que só começa depois da barreira seguinte, então zerar
  não precisa de lock.
- Pedaço pequeno equilibra melhor, mas aumenta as disputas pelo lock e a
  releitura de linhas de fronteira (cada pedaço lê 2 linhas a mais).

## Consistência entre gerações e ausência de condição de corrida

1. **Buffer duplo.** Existem duas grades. Na geração `g`, todos **leem** a grade
   `g % 2` e **escrevem** na grade `(g + 1) % 2`. É o mesmo cuidado do professor
   (calcular a nova grade a partir da antiga), sem o `deepcopy` a cada geração.
2. **Dono único.** Cada linha da grade de destino é escrita por um único worker:
   na divisão estática, pelo dono do bloco; na dinâmica, por quem recebeu o
   pedaço do contador protegido por lock. Ninguém escreve na grade de origem
   durante a geração, então as fronteiras podem ser lidas sem lock e sem cópia.
3. **Uma barreira por geração.** Ninguém começa a geração `g+1` antes de todos
   terminarem a `g`. Uma barreira basta: para alguém escrever na grade que outro
   ainda está lendo, ele teria que estar duas gerações à frente, e a barreira
   impede isso.
4. **Contagem sem lock.** Cada worker conta os estados das próprias linhas e
   grava num espaço só dele, também separado pela paridade da geração. Depois da
   barreira, todos somam as mesmas parcelas e tomam a **mesma** decisão de parar
   (nenhum espalhador), sem lock e sem mensagem extra.
5. **Sem deadlock em caso de erro.** Se um worker lança exceção, ele chama
   `barreira.abort()`. Os outros recebem `BrokenBarrierError`, saem do laço, e a
   função principal levanta `RuntimeError`. Há um teste que injeta essa falha e
   confere que nada trava.

Linha do tempo de uma geração:

```text
worker 0   ██████████░░░░░ espera ░░┐
worker 1   ████████████████████████─┤ barreira ─▶ geração seguinte
worker 2   ███████████░░░░ espera ░░┤
principal  ░░░░░░░░░░░░░░ espera ░░░┘ registra a contagem da geração
           ▲ todos esperam o worker mais lento: o desbalanceamento vira tempo perdido
```

## Os dois backends

|                     | `threads`                                        | `processos`                                                                          |
| ------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Workers             | `threading.Thread`                               | `multiprocessing.Process`                                                            |
| Grade compartilhada | lista de linhas (`bytes`) na memória do processo | um `multiprocessing.RawArray` com as duas grades lado a lado (memória compartilhada) |
| Barreira            | `threading.Barrier`                              | `multiprocessing.Barrier`                                                            |
| Paralelismo real    | só no Python sem GIL (`python3.14t`)             | sim, em qualquer CPython                                                             |
| Custo fixo          | criar threads (barato)                           | criar processos (caro no Windows: cada um reimporta o programa)                      |

**O GIL.** No CPython padrão, o _Global Interpreter Lock_ deixa só uma thread
executar bytecode Python por vez. Como a simulação é só cálculo em Python puro,
as threads se revezam em vez de rodar juntas, e o speedup fica perto de 1. Isso
não é defeito da divisão: a mesma divisão roda com speedup real no backend de
processos e no build _free-threaded_ do Python 3.14 (PEP 703 e PEP 779), em que
o GIL é desligado.

**Sem GIL, a ausência de condição de corrida passa a ser testada de verdade.**
Com GIL, um erro de sincronização pode ficar escondido porque as threads nunca
rodam ao mesmo tempo. Por isso a suíte de testes foi executada 5 vezes seguidas
no Python 3.14t, com até 16 threads simultâneas, e o resultado foi idêntico ao
do professor em todas. A varredura também confere, em cada execução, se a grade
final e o histórico batem com a referência (coluna `ok`).

**Por que as threads não precisam de lock nas grades sem GIL.** No build
_free-threaded_, `list` e `bytes` continuam seguras para operações isoladas: ler
`grades[g][i]` ou trocar a referência em `grades[g][i] = linha` nunca deixa um
objeto pela metade. A correção do algoritmo vem do buffer duplo, do dono único
de cada linha e da barreira. O GIL nunca foi o que garantia isso.

## Os dois kernels (otimização de algoritmo)

| Kernel       | Como calcula a linha                                                                                                                                                                                                                                                                      |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `referencia` | Igual ao professor: para cada célula ignorante olha os 8 vizinhos com teste de limites.                                                                                                                                                                                                   |
| `otimizado`  | Converte cada linha para 1 (espalhador) ou 0 (resto), soma as três linhas coluna a coluna e usa uma janela de 3 colunas. A janela 3x3 de uma célula ignorante é exatamente o número de vizinhos espalhadores (ela mesma vale 0), e um zero em cada ponta faz o papel do teste de limites. |

Os dois dão resultado idêntico ao `proxima_geracao` do professor (testado com
limiar de 0 a 9, grades de 1x1 a 23x17 e os três estados misturados). O ganho do
kernel otimizado **é de algoritmo, não de paralelismo**, e por isso aparece
separado nas tabelas:

- **speedup** = tempo com 1 worker / tempo com N workers, no mesmo backend e
  kernel (ganho só do paralelismo);
- **vs prof.** = tempo do código original do professor / tempo com N workers
  (ganho total).

Nenhuma biblioteca de paralelização implícita é usada (NumPy, Numba etc.). O
kernel otimizado é Python puro: compreensões de lista, `zip` e
`bytes.translate`, todos da biblioteca padrão e executados numa thread só.

## Achado que vale para o grupo inteiro: o limiar 3 mata a propagação

Com o limiar padrão do professor (3), a fake news some em 2 a 4 gerações,
qualquer que seja o percentual inicial. Variar o "número de gerações" nos
experimentos não muda nada nesse caso. Grade 1000x1000, semente 42, até 300
gerações:

| Limiar | 1% espalhadores              | 2%            | 5%           | 10%          |
| ------ | ---------------------------- | ------------- | ------------ | ------------ |
| 1      | 27 gerações (todos inativos) | 15            | 10           | 7            |
| **2**  | **264** (14% atingidos)      | **163** (25%) | **56** (58%) | **29** (91%) |
| 3      | 2 (1%)                       | 3 (2%)        | 3 (5%)       | 4 (13%)      |

Recomendação para os benchmarks das três versões: **limiar 2** e espalhadores
entre 1% e 2%, para que as gerações pedidas realmente rodem. A tabela de
resultados deve mostrar as gerações executadas.

## Achado 2: o Windows 11 rebaixa processos em segundo plano para os núcleos lentos

Na primeira rodada de medições, o mesmo código com 1 worker levou **5,5 s em
thread e 2,8 s em processo**, e o código do professor levou 61 s. Investigando
com `GetCurrentProcessorNumber` (em qual CPU o código está rodando):

| Momento da execução                      | Tempo por geração              | Amostras em núcleo P / E |
| ---------------------------------------- | ------------------------------ | ------------------------ |
| primeiros 3 s                            | 94–101 ms                      | 80 / 0                   |
| depois de ~3 s                           | 127 ms e subindo (até ~190 ms) | 58 / 22                  |
| depois de desligar a economia de energia | 94–103 ms                      | 80 / 0                   |

O Windows 11 classifica um processo de console sem janela em primeiro plano como
"segundo plano" depois de uns 3 segundos e passa a executá-lo nos núcleos de
eficiência (_EcoQoS_). O processo principal (onde rodam o sequencial e as
threads) era rebaixado, e os processos filhos, recém-criados, escapavam. **A
comparação ficava 2x a favor dos processos sem motivo nenhum.**

Correção: `energia.py` chama `SetProcessInformation` com
`ProcessPowerThrottling` (API documentada pela Microsoft) para pedir que o
processo não seja rebaixado. A varredura chama isso no processo principal, e
cada processo filho chama ao nascer, porque o pedido não é herdado. Depois da
correção, o professor caiu de 61 s para 30,7 s, e 1 worker passou a levar 2,8 s
nos dois backends.

**Vale para o grupo todo:** os benchmarks do sequencial e do distribuído
(servidor e workers) precisam chamar `desligar_economia_de_energia()` no começo
de cada processo. A alternativa é rodar com a janela do terminal em primeiro
plano e o Windows no modo de energia "Melhor desempenho", sem mexer no
computador durante a medição.

## Resultados

### Configuração experimental

| Item                | Valor                                                                                                                             |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Processador         | Intel Core i5-13450HX (13ª geração, híbrido): 6 núcleos P com hyper-threading + 4 núcleos E = 10 núcleos e 16 threads lógicas     |
| Memória             | 32 GB                                                                                                                             |
| Sistema operacional | Windows 11 Home Single Language, build 26200                                                                                      |
| Interpretadores     | CPython 3.14.7 (padrão, com GIL) e CPython 3.14.6 _free-threaded_ (sem GIL, instalado com `uv`)                                   |
| Ambiente            | notebook na tomada; economia de energia do Windows desligada em cada processo (Achado 2); nenhum outro programa pesado aberto     |
| Cenário principal   | grade 1000x1000 (1 milhão de pessoas), 30 gerações (todas executadas), 2% de espalhadores, limiar 2, semente 42                   |
| Método              | 5 repetições por configuração, todas as configurações intercaladas em ordem embaralhada (semente fixa); a tabela mostra a mediana |
| Tempo medido        | só o laço das gerações (`time.perf_counter`), sem prints; o tempo total, com criação dos workers, aparece separado                |

Dados brutos (uma linha por execução) e tabelas completas:
`benchmarks/results/paralelo/`. Nas **418 execuções paralelas**, a grade final e
o histórico de todas as gerações saíram idênticos aos do código do professor.

### Tempo e speedup

Tempo das 30 gerações e, entre parênteses, o speedup em relação a 1 worker da
mesma coluna.

| Workers | Threads com GIL | Threads sem GIL (estática) | Threads sem GIL (dinâmica) | Processos (estática) | Processos (dinâmica) |
| ------- | --------------- | -------------------------- | -------------------------- | -------------------- | -------------------- |
| 1       | 2,81 s (1,00)   | 2,94 s (1,00)              | 3,00 s (1,00)              | 2,85 s (1,00)        | 2,83 s (1,00)        |
| 2       | 2,82 s (1,00)   | 1,45 s (2,02)              | 1,45 s (2,07)              | 1,45 s (1,96)        | 1,43 s (1,97)        |
| 4       | 2,81 s (1,00)   | 0,76 s (3,86)              | 0,75 s (4,00)              | 0,73 s (3,87)        | 0,74 s (3,81)        |
| 6       | 2,87 s (0,98)   | 0,56 s (5,26)              | 0,52 s (5,81)              | 0,50 s (5,68)        | 0,52 s (5,40)        |
| 8       | 2,87 s (0,98)   | 0,54 s (5,39)              | 0,46 s (6,51)              | 0,53 s (5,34)        | 0,44 s (6,39)        |
| 10      | 2,82 s (1,00)   | 0,51 s (5,75)              | 0,43 s (6,97)              | 0,46 s (6,14)        | 0,40 s (7,09)        |
| 12      | 2,82 s (1,00)   | 0,44 s (6,62)              | 0,42 s (7,22)              | 0,41 s (6,91)        | 0,37 s (7,67)        |
| 16      | 2,83 s (0,99)   | 0,38 s (7,67)              | 0,37 s (8,20)              | 0,40 s (7,16)        | 0,34 s (8,41)        |

Os processos foram medidos no Python com GIL; no Python sem GIL os números deles
são parecidos (tabela completa em `benchmarks/results/paralelo/`).

### Eficiência (speedup / workers)

| Workers | Threads sem GIL (dinâmica) | Processos (estática) | Processos (dinâmica) |
| ------- | -------------------------- | -------------------- | -------------------- |
| 2       | 104%                       | 98%                  | 98%                  |
| 4       | 100%                       | 97%                  | 95%                  |
| 6       | 97%                        | 95%                  | 90%                  |
| 8       | 81%                        | 67%                  | 80%                  |
| 12      | 60%                        | 58%                  | 64%                  |
| 16      | 51%                        | 45%                  | 53%                  |

Eficiência acima de 100% com 2 workers está dentro da variação da medição (cerca
de 5%).

### Ganho total em relação ao código do professor

| Versão                                        | Tempo (30 gerações) | Ganho                                      |
| --------------------------------------------- | ------------------- | ------------------------------------------ |
| Código original do professor                  | 30,69 s             | 1x                                         |
| Kernel otimizado, 1 worker (só algoritmo)     | 2,81 s              | 10,9x                                      |
| Threads com GIL, 16 threads                   | 2,83 s              | 10,9x (nada a mais que 1 thread)           |
| Threads sem GIL, 16 threads, divisão dinâmica | 0,37 s              | 85x (professor no Python sem GIL: 31,15 s) |
| Processos, 16 processos, divisão dinâmica     | 0,34 s              | 91x                                        |

Dos 91x, **10,9x vêm do algoritmo** (kernel otimizado e fim do `deepcopy`) e
**8,4x vêm do paralelismo**. Só o segundo número é speedup paralelo.

### Divisão estática x dinâmica

Processos, Python com GIL. "Desbal." é o tempo do worker mais lento dividido
pela média, geração a geração.

| Workers | Estática: tempo (desbal.) | Dinâmica: tempo (desbal.) | Diferença |
| ------- | ------------------------- | ------------------------- | --------- |
| 4       | 0,734 s (1,01)            | 0,741 s (1,02)            | +1%       |
| 6       | 0,501 s (1,04)            | 0,523 s (1,07)            | +4%       |
| 8       | 0,533 s (1,28)            | 0,442 s (1,05)            | **−17%**  |
| 10      | 0,463 s (1,23)            | 0,398 s (1,05)            | **−14%**  |
| 12      | 0,412 s (1,18)            | 0,368 s (1,05)            | **−11%**  |
| 16      | 0,397 s (1,18)            | 0,336 s (1,06)            | **−15%**  |

Até 6 workers, cada worker tem um núcleo P só para ele, não há desbalanceamento
para corrigir, e a divisão dinâmica só acrescenta custo: lock por pedaço e
releitura das fronteiras. Acima de 6, a estática fica esperando o worker que
caiu num núcleo E ou dividiu um núcleo com hyper-threading. A dinâmica derruba o
desbalanceamento de até 1,28 para 1,05 e ganha de 11% a 17%.

### Custo fixo: grade pequena (250x250, 30 gerações, Python sem GIL)

| Workers | Threads: gerações / total | Processos: gerações / total |
| ------- | ------------------------- | --------------------------- |
| 1       | 0,182 s / 0,182 s         | 0,189 s / 0,323 s           |
| 4       | 0,048 s / 0,050 s         | 0,050 s / 0,208 s           |
| 16      | 0,038 s / 0,044 s         | 0,038 s / 0,373 s           |

Com a grade pequena, criar 16 processos no Windows custa mais que a simulação
inteira. Somando a criação, 16 processos (0,373 s) demoram mais que 1 processo
(0,323 s). As threads custam quase nada para criar.

### Análise

**Gargalos, do maior para o menor:**

1. **GIL.** No Python padrão, as threads ficam em 1,0x com qualquer número de
   workers. A divisão está certa, porque a mesma divisão dá 8,2x no Python sem
   GIL.
2. **Hardware acima de 6 workers.** Até 6 workers a eficiência fica entre 90% e
   100%: cada worker tem um núcleo P. Acima disso, os workers extras caem em
   núcleos E, mais lentos, ou dividem um núcleo P com hyper-threading, e o
   notebook não sustenta o turbo máximo com todos os núcleos ligados. O kernel
   de referência, 7x mais pesado por célula (500x500, 20 gerações), escala
   igual: 8,10x com 16 processos contra 8,41x do otimizado. Como mais cálculo
   por geração não melhora a eficiência, a perda não vem da sincronização. Vem
   da capacidade do processador. Nesta máquina o teto prático fica perto de
   8,4x.
3. **Desbalanceamento na divisão estática** acima de 6 workers: até 28% de
   espera na barreira. A divisão dinâmica resolve.
4. **Criação de processos no Windows** (método _spawn_: cada processo reimporta
   o programa): 0,1 a 0,33 s. É irrelevante na grade grande e domina na grade
   pequena.

**Sincronização.** Uma barreira por geração. O tempo fora do cálculo do worker
mais lento (coluna `sinc.`) fica entre 0,004 e 0,008 s nas 30 gerações da grade
1000x1000, menos de 2% do tempo. A contagem dos estados não usa lock, e a
divisão dinâmica pega o lock uma vez por pedaço, cerca de 8 vezes por worker por
geração, sem custo visível. Com GIL, a coluna `sinc.` das threads sobe para até
2,6 s: é a espera pelo GIL, não pela barreira.

**Comunicação.** Na memória compartilhada não há troca de mensagens: as linhas
de fronteira são lidas direto da grade de origem. No backend de processos, ler
uma linha é uma cópia de 1.000 bytes da memória compartilhada, sem custo
visível. Por isso a comunicação não aparece como gargalo aqui, ao contrário da
versão distribuída, em que as fronteiras viajam pela rede a cada geração.

**Threads sem GIL x processos.** No tempo das gerações os dois empatam: 8,2x
contra 8,4x com 16 workers. No tempo total as threads ganham sempre, porque não
pagam a criação de processos. Com 1 worker, as threads sem GIL ficaram cerca de
10% mais lentas que um processo no mesmo interpretador (2,94 s contra 2,64 s). A
causa provável é o custo extra de contagem de referências de objetos
compartilhados entre threads no Python sem GIL (PEP 703); isso não foi isolado.

**Amdahl.** A parte sequencial do programa por geração (somar as contagens e
passar pela barreira) é desprezível perto do cálculo. Pela lei de Amdahl o
speedup poderia chegar perto do número de workers. O que limita aqui é o
hardware heterogêneo, não a fração sequencial.

## Limitações

- **GIL**: no CPython padrão o backend de threads não acelera. A versão com
  threads é correta e segura, mas o ganho só aparece sem GIL.
- **Custo de criar processos**: no Windows cada processo reimporta o programa
  (método _spawn_). Em grades pequenas esse custo fixo é maior que o cálculo
  inteiro. O tempo das gerações e o tempo total são medidos separados por isso.
- **Núcleos diferentes**: com mais workers do que núcleos P, parte do trabalho
  roda em núcleos E ou em hyper-threading, que rendem menos. A divisão dinâmica
  distribui melhor o trabalho, mas não cria núcleos rápidos que não existem.
- **Python puro**: mesmo o kernel otimizado gasta perto de 100 ns por célula. O
  paralelismo divide esse custo, mas não muda a ordem de grandeza.
- **Ambiente de medição**: no Windows 11 é preciso desligar a economia de
  energia de cada processo (Achado 2), e o notebook precisa estar na tomada. Os
  tempos variam alguns por cento entre execuções, por isso cada configuração
  roda 5 vezes (3 no kernel de referência) e a tabela mostra a mediana.

## Referências

1. DALEY, D. J.; KENDALL, D. G. Epidemics and rumours. _Nature_, v. 204, p.
   1118, 1964. (Modelo de boato com ignorantes, espalhadores e inativos.)
2. MAKI, D. P.; THOMPSON, M. _Mathematical Models and Applications_. Englewood
   Cliffs: Prentice-Hall, 1973.
3. MOORE, E. F. Machine models of self-reproduction. _Proceedings of Symposia in
   Applied Mathematics_, v. 14, p. 17–33, 1962. (Vizinhança de Moore.)
4. WOLFRAM, S. Statistical mechanics of cellular automata. _Reviews of Modern
   Physics_, v. 55, n. 3, p. 601–644, 1983. (Atualização síncrona de autômatos
   celulares.)
5. FOSTER, I. _Designing and Building Parallel Programs_. Reading:
   Addison-Wesley, 1995. (Metodologia de particionamento, comunicação,
   aglomeração e mapeamento.)
6. GRAMA, A.; GUPTA, A.; KARYPIS, G.; KUMAR, V. _Introduction to Parallel
   Computing_. 2. ed. Addison-Wesley, 2003. (Decomposição de domínio, barreiras,
   speedup e eficiência.)
7. AMDAHL, G. M. Validity of the single processor approach to achieving large
   scale computing capabilities. In: _AFIPS Spring Joint Computer Conference_,
   1967, p. 483–485.
8. GUSTAFSON, J. L. Reevaluating Amdahl's law. _Communications of the ACM_, v.
   31, n. 5, p. 532–533, 1988.
9. GROSS, S. _PEP 703 – Making the Global Interpreter Lock Optional in
   CPython_, 2023. Disponível em: <https://peps.python.org/pep-0703/>.
10. WOUTERS, T.; PAGE, M.; GROSS, S. _PEP 779 – Criteria for supported status
    for free-threaded Python_, 2025. Disponível em:
    <https://peps.python.org/pep-0779/>.
11. BEAZLEY, D. Understanding the Python GIL. _PyCon_, 2010.
12. PYTHON SOFTWARE FOUNDATION. _threading_ e _multiprocessing_ (Barrier,
    RawArray). Documentação do Python 3.14. Disponível em:
    <https://docs.python.org/3/library/>.
13. MICROSOFT. _SetProcessInformation function (processthreadsapi.h)_ e _Quality
    of Service_. Microsoft Learn. Disponível em:
    <https://learn.microsoft.com/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation>.
