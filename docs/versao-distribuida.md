# Versão distribuída via sockets TCP

A simulação agora divide a matriz entre processos workers. O código usa apenas a biblioteca padrão do Python e reutiliza as regras de `src/common/core.py`. O original do professor, a versão paralela e os arquivos de benchmarks não foram modificados.

## Arquivos

- `server.py`: coordenador, divisão das faixas, encaminhamento dos halos, barreira por geração, histórico e coleta final.
- `worker.py`: conexão persistente, armazenamento da faixa local (linhas `bytes`) e cálculo usando `calcular_linhas` com o kernel escolhido no servidor.
- `protocol.py`: JSON com prefixo de quatro bytes, validação das mensagens e transferência de grades em lotes.
- `distribuida.py`: interface `simular(config) -> Resultado` para os testes e integração do grupo.
- `tests/test_distribuida.py`: protocolo, transferência grande, execução manual, erros e medições.

## Execução automática local

Na raiz do repositório:

```powershell
python src/distributed/server.py --automaticos --workers 2 --port 0
```

A porta zero solicita uma porta livre ao sistema operacional. O coordenador inicia dois interpretadores Python independentes e os encerra ao final. Eles se comunicam exclusivamente por TCP; o cálculo não usa memória compartilhada.

Exemplo com mais gerações e resultado em JSON:

```powershell
python src/distributed/server.py --automaticos --workers 4 --port 0 -l 200 -c 200 -g 30 -p 0.02 -t 2 --saida distribuida.json
```

Use `--kernel otimizado` para o mesmo kernel padrão da versão paralela; o servidor repassa o nome aos workers na mensagem `iniciar` (padrão: `referencia`). Para comparar tempos entre as versões, use sempre o mesmo kernel nas três.

O limiar 2 e 2% de espalhadores normalmente exercitam mais gerações que os parâmetros originais. O critério de parada continua sendo o original; registre sempre quantas gerações realmente foram executadas.

`--saida` salva histórico, hash, configuração e métricas. Acrescente `--incluir-grade` para salvar também a matriz final. `--silencioso` omite os registros e detalhes das métricas do terminal; ainda imprime uma linha final de resumo. Use `--help` para consultar as opções.

## Execução manual com dois workers

Abra três terminais na raiz do repositório.

Terminal 1:

```powershell
python src/distributed/server.py --workers 2 -l 100 -c 100 -g 20 -p 0.02 -t 2
```

Terminal 2:

```powershell
python src/distributed/worker.py
```

Terminal 3:

```powershell
python src/distributed/worker.py
```

Os padrões são host `127.0.0.1` e porta `5000`. O servidor aguarda exatamente a quantidade de workers indicada. Depois de todos conectarem, executa a simulação e encerra. Os workers agora recebem tarefas até o comando de finalização, em vez de responderem somente a uma saudação.

O prazo padrão de comunicação é de 30 segundos; configure `--timeout 120` tanto no servidor quanto nos workers para execuções mais lentas ou para dar mais tempo às conexões manuais. Ctrl+C interrompe a execução. Desconexões, mensagens fora de ordem e timeouts abortam a simulação; resultados parciais não são apresentados como válidos.

## Execução em máquinas diferentes

Na máquina coordenadora:

```powershell
python src/distributed/server.py --host 0.0.0.0 --port 5000 --workers 2 --timeout 120
```

Em cada máquina worker, use o endereço IPv4 real da coordenadora na rede:

```powershell
python src/distributed/worker.py --host 192.168.1.10 --port 5000 --timeout 120
```

Substitua o IP do exemplo. `0.0.0.0` é o endereço de escuta, não o destino dos workers. Todos precisam ter Python e a mesma versão do projeto. Autorize a porta TCP escolhida na rede privada pelo firewall, se necessário. Não use `--automaticos` para workers remotos.

A execução manual foi validada com processos locais separados. A conectividade entre computadores físicos precisa ser testada na rede da apresentação. Os tempos da inicialização manual incluem a espera pelo usuário conectar os workers.

## Como uma geração funciona

1. O servidor cria uma única grade com a semente comum e usa `dividir_linhas` para atribuir faixas contíguas. A diferença entre as faixas é de no máximo uma linha.
2. Cada worker recebe seu bloco uma vez e devolve as bordas iniciais.
3. Para calcular a geração 1, o servidor encaminha as bordas da geração 0: última linha do vizinho de cima e primeira linha do vizinho de baixo.
4. Cada worker monta sua fatia com os halos, chama `calcular_linhas` apenas para as próprias linhas e mantém o novo bloco localmente. Os halos não entram na contagem nem na grade final.
5. Os workers enviam contagens e duas bordas atualizadas, com o número da geração.
6. O servidor aguarda TODOS os estados daquela geração. Essa espera constitui a barreira. Somente então prepara os próximos halos.
7. O servidor soma as contagens e registra o histórico. Se não restarem espalhadores ou o limite de gerações for atingido, envia `finalizar` e recolhe os blocos na ordem das faixas.

As fronteiras externas da matriz não possuem halos. Workers excedentes, quando há mais processos que linhas, recebem blocos vazios e participam da sincronização sem calcular células.

Com zero gerações, a função retorna a grade inicial, sem iniciar workers.

## Protocolo e volume de dados

TCP é um fluxo de bytes; um `recv` não corresponde necessariamente a uma mensagem completa. Cada objeto JSON em UTF-8 possui um prefixo de quatro bytes, inteiro sem sinal em ordem de rede, indicando o tamanho do corpo em bytes. O receptor acumula exatamente essa quantidade antes de interpretar o JSON.

A sequência de mensagens é:

```text
worker -> servidor: pronto (versão do protocolo, atualmente 2)
servidor -> worker: iniciar (dimensões, limiar, kernel, halos esperados) + grade em lotes
worker -> servidor: estado da geração 0
servidor -> worker: calcular (geração e halos)
worker -> servidor: estado (geração, contagens, bordas e tempo de cálculo)
                    ... repete até a parada ...
servidor -> worker: finalizar
worker -> servidor: final (métricas) + grade em lotes
```

O limite continua sendo 1 MiB POR MENSAGEM. Grades maiores são transferidas em lotes de até 65.536 células, representadas por texto como `"001201"`. Um lote pode conter várias linhas ou parte de uma linha. Os cabeçalhos informam as dimensões e o receptor rejeita estados e quantidades inconsistentes.

Durante as gerações não se retransmite a matriz inteira: apenas halos, bordas e contagens. O volume de células de fronteira cresce com trabalhadores × colunas, em vez de linhas × colunas a cada geração. `celulas_halo_enviadas` conta as células encaminhadas pelo servidor; não é uma contagem dos bytes totais do TCP.

Para manter duas bordas na mesma mensagem de controle, a implementação limita a largura a `LIMITE_MENSAGEM // 4` colunas (262.144 atualmente). A altura pode exigir quantos lotes forem necessários.

## Interface e integração

Com `src/` no caminho de importação:

```python
from common.core import Config
from distributed.distribuida import simular

resultado = simular(Config(linhas=100, colunas=100, num_processos=2))
print(resultado.hash_grade)
print(resultado.metricas)
```

A interface automática usa loopback e uma porta livre por chamada, sem depender de terminais externos. A saída herda `Resultado`, portanto mantém configuração, histórico, gerações executadas, tempo, grade e hash. `para_dict()` acrescenta as métricas sem incluir a grade, a menos que solicitado.

A distribuída está integrada aos benchmarks como o backend `distribuida` (`benchmarks/adapters.py: executar_distribuido`), separada dos processos com memória compartilhada. O executor mede o modo local automático; `executar_servidor(..., grade_inicial=grade)` permite usar a mesma grade de cada cenário. Além dos tempos, o `raw.csv` registra `caminho_critico_s`, `overhead_s` (comunicação, serialização e espera) e `celulas_halo`.

A versão 2 do protocolo acrescentou o kernel; servidor e workers de versões diferentes recusam a conexão ("Versão de protocolo incompatível").

## Medições e limites de interpretação

- `resultado.tempo_s`: tempo de parede do laço das gerações no coordenador, incluindo controle, comunicação, espera e agregação das contagens.
- `inicializacao_s`: abrir o servidor, conectar/iniciar workers, distribuir os blocos e receber as primeiras bordas.
- `finalizacao_s`: enviar a parada e receber métricas e blocos finais.
- `total_s`: execução completa após criar a grade inicial, incluindo recolher os processos locais. Não inclui criar a grade, calcular o hash final ou salvar JSON.
- `envio_coordenador_s`: chamadas de envio durante o laço, incluindo serialização.
- `recepcao_espera_coordenador_s`: chamadas de recebimento durante o laço, incluindo validação, espera pelo cálculo dos workers e sincronização.
- `workers[k].calculo_s`: tempo acumulado apenas em `calcular_linhas`; não inclui contagem ou codificação de bordas.
- `workers[k].envio_s`: envio dos estados das gerações.
- `workers[k].recepcao_espera_s`: espera/recebimento dos comandos, incluindo a barreira e o comando final.
- `caminho_critico_calculo_s`: soma do maior tempo de cálculo observado entre os workers em cada geração.

Os tempos são medidos localmente com `perf_counter`; não se subtraem relógios de computadores diferentes. Recepção e espera NÃO medem somente o tráfego da rede. Envio pode terminar quando o sistema operacional aceita os bytes. Esses valores não isolam latência de rede ou transmissão física.

Tempos de workers concorrentes não devem ser somados e tratados como tempo de parede. As medições de comunicação e de cálculo podem se sobrepor. Registre separadamente o escopo do laço e o escopo total nas comparações.

O coordenador é centralizado e pode virar um gargalo. Não há reconexão automática ou recuperação de falhas. O protocolo foi projetado para os testes acadêmicos em rede confiável, sem autenticação ou criptografia. O uso de sockets, por si só, não garante aceleração: inicialização, serialização e comunicação podem superar o ganho do cálculo.

## Validação

```powershell
python -B -m unittest discover -s tests -p test_distribuida.py -v
python -B -m unittest discover -s tests -p test_equivalence.py -v
python -B -m unittest discover -s tests -v
```

A suíte comum agora encontra `distributed.distribuida`: compara histórico, gerações, hash e matriz com o sequencial em vários cenários e números de workers. Inclui faixas desiguais, matriz com uma linha/coluna, ausência de espalhadores e mais workers que linhas.

As funcionalidades gráficas dos outros integrantes exigem suas dependências externas; a implementação distribuída e seus testes específicos usam somente a biblioteca padrão.

## Referências para estudo

- PYTHON SOFTWARE FOUNDATION. Socket Programming HOWTO. https://docs.python.org/3/howto/sockets.html
- PYTHON SOFTWARE FOUNDATION. Documentação de `socket`, `struct`, `json`, `subprocess` e `time`. https://docs.python.org/3/library/
- FOSTER, Ian. Designing and Building Parallel Programs. Addison-Wesley, 1995. Particionamento, comunicação e sincronização.
