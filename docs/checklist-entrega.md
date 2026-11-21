# Checklist final de entrega

Última revisão: 21/11/2026. Prazo informado no enunciado: 23/11/2026 às 23:59.

## Código e validação

- [x] Código sequencial original preservado.
- [x] Versão paralela com threads e divisão explícita da matriz.
- [x] Backend adicional com `multiprocessing` para paralelismo real em CPython.
- [x] Versão distribuída com sockets TCP e processos independentes.
- [x] Divisão da matriz em faixas de linhas.
- [x] Sincronização de fronteiras por halos.
- [x] Barreira entre gerações e buffer duplo.
- [x] Equivalência lógica entre sequencial, paralela e distribuída.
- [x] Tratamento básico de erros, timeouts e encerramento.
- [x] Extensões: probabilidade, influenciadores e bots.
- [x] Testes automatizados das regras, protocolo e integrações.

## Experimentos

- [x] Executor comum às três versões.
- [x] Variação de tamanho, gerações, percentual inicial e workers.
- [x] Repetições, aquecimento separado e mesma entrada para todas as versões.
- [x] Medição de tempo, speedup, eficiência e overhead.
- [x] Registro automático do ambiente experimental quando disponível.
- [ ] Gerar e versionar os resultados locais finais.
- [ ] Gerar gráficos e tabela-resumo finais.
- [ ] Repetir o experimento em outro computador, se o grupo quiser apresentar múltiplos hosts físicos.
- [ ] Registrar manualmente detalhes da rede caso haja teste entre máquinas.

## Documentação e apresentação

- [x] README com instalação, execução, testes e limitações.
- [x] Documentação das versões paralela e distribuída.
- [x] Melhorias e extensões justificadas.
- [x] Referências consolidadas.
- [x] Declaração do uso de IA.
- [x] Roteiro de slides cobrindo os itens do enunciado.
- [ ] Análise dos resultados locais finais.
- [ ] Substituir os três campos `[nome]` pelos integrantes reais.
- [ ] Revisar e confirmar a contribuição individual de cada integrante.
- [ ] Dividir as falas para que todos participem.
- [ ] Ensaiar a apresentação de 15 a 20 minutos e a demonstração ao vivo.
- [ ] Exportar a versão final dos slides para PDF após inserir nomes e revisar os resultados.

## Publicação

- [ ] Revisar o `git diff` em grupo.
- [ ] Criar commit e Pull Request das alterações finais.
- [ ] Fazer merge de `develop` em `main` somente após aprovação do grupo.
- [ ] Conferir o GitHub a partir de uma janela anônima.
- [ ] Gerar o ZIP do código a partir da revisão final de `main`.
- [ ] Enviar ZIP e PDF no Moodle antes do prazo.

Os itens sem marcação dependem de informações ou decisões humanas e não devem ser preenchidos automaticamente com dados inventados.
