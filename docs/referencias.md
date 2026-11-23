# Referências e declaração de uso de IA

Este documento consolida as fontes usadas para fundamentar o modelo, o paralelismo, a distribuição, as extensões e as ferramentas do projeto. A apresentação deve usar uma seleção curta desta lista.

## Modelo e propagação

1. DALEY, D. J.; KENDALL, D. G. Stochastic rumours. *IMA Journal of Applied Mathematics*, v. 1, n. 1, p. 42–55, 1965. DOI: 10.1093/imamat/1.1.42.
2. MAKI, D. P.; THOMPSON, M. *Mathematical Models and Applications*. Englewood Cliffs: Prentice-Hall, 1973.
3. MOORE, E. F. Machine models of self-reproduction. *Proceedings of Symposia in Applied Mathematics*, v. 14, p. 17–33, 1962.
4. GRANOVETTER, M. Threshold models of collective behavior. *American Journal of Sociology*, v. 83, n. 6, p. 1420–1443, 1978.
5. MORENO, Y.; NEKOVEE, M.; PACHECO, A. F. Dynamics of rumor spreading in complex networks. *Physical Review E*, v. 69, 066130, 2004.

## Influência, bots e aleatoriedade

6. CHA, M.; HADDADI, H.; BENEVENUTO, F.; GUMMADI, K. P. Measuring user influence in Twitter: the million follower fallacy. *ICWSM*, 2010.
7. FERRARA, E. et al. The rise of social bots. *Communications of the ACM*, v. 59, n. 7, p. 96–104, 2016.
8. SHAO, C. et al. The spread of low-credibility content by social bots. *Nature Communications*, v. 9, 4787, 2018.
9. VOSOUGHI, S.; ROY, D.; ARAL, S. The spread of true and false news online. *Science*, v. 359, n. 6380, p. 1146–1151, 2018.
10. SALMON, J. K. et al. Parallel random numbers: as easy as 1, 2, 3. *SC '11*, 2011.

## Computação paralela e distribuída

11. FOSTER, I. *Designing and Building Parallel Programs*. Addison-Wesley, 1995.
12. GRAMA, A.; GUPTA, A.; KARYPIS, G.; KUMAR, V. *Introduction to Parallel Computing*. 2. ed. Addison-Wesley, 2003.
13. AMDAHL, G. M. Validity of the single processor approach to achieving large scale computing capabilities. *AFIPS Spring Joint Computer Conference*, p. 483–485, 1967.
14. GUSTAFSON, J. L. Reevaluating Amdahl's law. *Communications of the ACM*, v. 31, n. 5, p. 532–533, 1988.
15. PYTHON SOFTWARE FOUNDATION. *Socket Programming HOWTO* e documentação de `socket`, `struct`, `json`, `threading` e `multiprocessing`. Disponível em: https://docs.python.org/3/.
16. GROSS, S. *PEP 703 – Making the Global Interpreter Lock Optional in CPython*, 2023. Disponível em: https://peps.python.org/pep-0703/.

## Bibliotecas adicionais

- Matplotlib: criação dos gráficos de desempenho e quadros da visualização.
- Pillow: codificação da animação GIF e validação de imagens nos testes.

As versões reproduzíveis estão registradas em `requirements.txt`. Nenhuma dessas bibliotecas executa o cálculo paralelo ou distribuído da simulação.

## Declaração de uso de IA generativa

O grupo utilizou ferramentas de IA generativa, incluindo ChatGPT/Codex, como apoio nas seguintes atividades:

- organização do repositório e revisão de requisitos;
- explicação de conceitos e apoio ao estudo do código;
- sugestões e revisão de implementação, testes e documentação;
- preparação inicial de checklists, análises e material de apresentação.

O uso de IA não substituiu a execução dos programas nem gerou os valores experimentais apresentados. Os resultados são produzidos pelos scripts do repositório, com parâmetros e ambiente registrados. O grupo é responsável por revisar o código, compreender as decisões, validar os testes, interpretar os resultados e apresentar o trabalho.

Código original fornecido pelo professor permanece identificado em `src/sequential/fake_news.py`. As demais fontes externas e bibliotecas estão declaradas acima ou na documentação específica de cada versão.
