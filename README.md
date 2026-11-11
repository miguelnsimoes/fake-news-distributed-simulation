# Fake News Distributed Simulation

Projeto acadêmico da disciplina de **Sistemas Distribuídos**, desenvolvido em Python para simular a propagação de fake news em uma matriz bidimensional. Cada célula representa uma pessoa, cujo estado evolui ao longo das gerações conforme a vizinhança.

**Status: em desenvolvimento.** Esta etapa prepara a estrutura do repositório e mantém a implementação sequencial fornecida pelo professor. As versões paralela e distribuída, os testes automatizados e os benchmarks serão desenvolvidos posteriormente.

## Objetivo acadêmico

Comparar as abordagens sequencial, paralela e distribuída para a mesma simulação, estudando divisão de trabalho, comunicação entre processos e desempenho. As implementações futuras deverão preservar as regras da versão sequencial para permitir uma comparação consistente.

## Estados da simulação

| Código | Estado | Descrição |
| --- | --- | --- |
| `0` | Ignorante | Ainda não recebeu ou não acredita na informação. |
| `1` | Espalhador | Acredita e compartilha a informação. |
| `2` | Inativo | Recebeu a informação, mas não a compartilha mais. |

Na implementação fornecida, um ignorante se torna espalhador quando possui pelo menos o número configurado de vizinhos espalhadores. Um espalhador se torna inativo na geração seguinte, e um inativo permanece inativo. A vizinhança considera até oito células ao redor de cada pessoa, respeitando os limites da matriz. Cada nova geração é calculada a partir da grade anterior.

## Implementações

| Implementação | Situação | Descrição |
| --- | --- | --- |
| Sequencial | Disponível | Código original do professor, preservado integralmente em `src/sequential/fake_news.py`. |
| Paralela | Planejada | Divisão do processamento usando threads ou `multiprocessing`; a abordagem será definida na etapa de implementação. |
| Distribuída | Planejada | Divisão do processamento entre processos com comunicação por sockets. |

## Tecnologias

- **Atuais:** Python 3 e biblioteca padrão (`random`, `time` e `copy`); Git e GitHub para versionamento e colaboração.
- **Planejadas:** `threading` ou `multiprocessing` para paralelismo e `socket` para comunicação distribuída, priorizando a biblioteca padrão.

O código sequencial não exige pacotes externos. O arquivo `requirements.txt` permanece vazio nesta etapa.

## Estrutura de diretórios

```text
fake-news-distributed-simulation/
├── src/
│   ├── sequential/
│   │   └── fake_news.py
│   ├── parallel/
│   │   └── .gitkeep
│   ├── distributed/
│   │   └── .gitkeep
│   └── common/
│       └── .gitkeep
├── tests/
│   └── .gitkeep
├── benchmarks/
│   └── results/
│       └── .gitkeep
├── docs/
│   └── .gitkeep
├── README.md
├── .gitignore
└── requirements.txt
```

As pastas `parallel`, `distributed` e `common` ficam reservadas para as próximas etapas. `tests` receberá testes automatizados; `benchmarks/results`, resultados das comparações de desempenho; e `docs`, documentação complementar. Os arquivos `.gitkeep` permitem versionar as pastas ainda vazias.

## Executar a versão sequencial

É necessário ter Python 3 instalado e disponível no terminal. Na raiz do repositório, execute:

```sh
python --version
python src/sequential/fake_news.py
```

Em ambientes onde o interpretador é chamado de `python3`, substitua `python` por `python3` nos comandos.

O script executa com os parâmetros originais definidos no bloco `if __name__ == "__main__"`: matriz de 100 × 100, limite de 50 gerações, percentual inicial de espalhadores de 5%, limiar de convencimento de três vizinhos e exibição da grade desativada. A simulação pode terminar antes do limite de gerações caso não existam mais espalhadores. As estatísticas por geração, os totais finais e o tempo de execução são exibidos no terminal.

Não é necessário instalar dependências ou criar um ambiente virtual para executar esta versão.

## Integrantes

| Integrante | Nome |
| --- | --- |
| 1 | A preencher |
| 2 | A preencher |
| 3 | A preencher |
| 4 | A preencher |

## Colaboração

O desenvolvimento será organizado no GitHub com branches de funcionalidades e Pull Requests para revisão das contribuições. As próximas etapas incluem as implementações paralela e distribuída, os testes automatizados e os benchmarks, cada uma em sua branch específica.
