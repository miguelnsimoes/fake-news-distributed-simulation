"""
Núcleo compartilhado da simulação de propagação de Fake News.

Este módulo (src/common/core.py) é a BASE COMUM das três versões (sequencial, paralela e distribuída).
Todas devem importar daqui as constantes, a criação da grade, a regra de transição
e as funções de contagem, para garantir que o comportamento lógico seja idêntico.

Estados:
    0 = IGNORANTE  : ainda não recebeu/acredita na informação
    1 = ESPALHADOR : acredita e compartilha a informação
    2 = INATIVO    : recebeu a informação, mas não compartilha mais

Regras (vizinhança de Moore, até 8 vizinhos, geração discreta):
    - IGNORANTE  -> ESPALHADOR se tiver >= limiar vizinhos ESPALHADORES
    - ESPALHADOR -> INATIVO
    - INATIVO    -> INATIVO

CONTRATO DE INTERFACE (todas as versões devem seguir):
    simular(config: Config) -> Resultado

    A função `calcular_faixa` é a peça reutilizável pelas versões paralelas:
    ela calcula apenas um intervalo de linhas, lendo de uma grade (que pode ser
    uma "fatia" com linhas-fantasma/halo), sem nunca escrever na grade de leitura.
"""

import hashlib
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional

IGNORANTE = 0
ESPALHADOR = 1
INATIVO = 2

Grade = List[List[int]]


# ---------------------------------------------------------------------------
# Configuração e resultado padronizados
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Parâmetros de entrada, iguais para as três versões."""
    linhas: int = 100
    colunas: int = 100
    geracoes: int = 50
    percentual_espalhadores: float = 0.05
    limiar_convencimento: int = 3
    semente: int = 42
    # Só usados pelas versões paralela/distribuída (a sequencial ignora):
    num_threads: int = 1
    num_processos: int = 1


@dataclass
class Resultado:
    """Saída padronizada, igual para as três versões."""
    versao: str
    config: Config
    # um dict por geração: {"geracao", "ignorantes", "espalhadores", "inativos"}
    historico: List[Dict[str, int]] = field(default_factory=list)
    geracoes_executadas: int = 0
    tempo_s: float = 0.0
    grade_final: Optional[Grade] = None
    hash_grade: str = ""

    def contagem_final(self) -> Dict[str, int]:
        return self.historico[-1] if self.historico else {}

    def para_dict(self, incluir_grade: bool = False) -> dict:
        d = {
            "versao": self.versao,
            "config": asdict(self.config),
            "geracoes_executadas": self.geracoes_executadas,
            "tempo_s": self.tempo_s,
            "hash_grade": self.hash_grade,
            "historico": self.historico,
        }
        if incluir_grade:
            d["grade_final"] = self.grade_final
        return d


# ---------------------------------------------------------------------------
# Criação da grade
# ---------------------------------------------------------------------------

def criar_grade(linhas: int, colunas: int,
                percentual_espalhadores: float = 0.02,
                semente: int = 42) -> Grade:
    """
    Cria a grade inicial. A grade é SEMPRE gerada inteira, no processo
    coordenador, com a mesma semente; depois cada versão a distribui.

    Usa um gerador local (random.Random) em vez do global, mas a sequência de
    números é idêntica à do código original (random.seed + random.randint),
    então a grade inicial é exatamente a mesma do código do professor.
    """
    rng = random.Random(semente)
    grade = [[IGNORANTE] * colunas for _ in range(linhas)]

    total_espalhadores = int(linhas * colunas * percentual_espalhadores)
    for _ in range(total_espalhadores):
        i = rng.randint(0, linhas - 1)
        j = rng.randint(0, colunas - 1)
        grade[i][j] = ESPALHADOR

    return grade


# ---------------------------------------------------------------------------
# Regra de transição
# ---------------------------------------------------------------------------

def contar_vizinhos_espalhadores(grade: Grade, i: int, j: int) -> int:
    """
    Conta vizinhos ESPALHADORES (Moore, até 8) da célula (i, j).
    Os limites são os da `grade` recebida: células fora dela não existem.
    Isso permite usar a mesma função em uma fatia com halo (versão distribuída).
    """
    linhas = len(grade)
    colunas = len(grade[0])
    total = 0

    for di in (-1, 0, 1):
        ni = i + di
        if ni < 0 or ni >= linhas:
            continue
        linha_viz = grade[ni]
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            nj = j + dj
            if 0 <= nj < colunas and linha_viz[nj] == ESPALHADOR:
                total += 1

    return total


def calcular_faixa(grade: Grade, linha_ini: int, linha_fim: int,
                   limiar_convencimento: int) -> Grade:
    """
    Calcula a próxima geração APENAS das linhas [linha_ini, linha_fim)
    e devolve essas linhas já atualizadas (lista de novas linhas).

    Propriedades importantes para paralelismo:
      - LÊ de `grade` e NUNCA escreve nela -> sem condição de corrida de leitura.
      - Devolve linhas NOVAS -> cada thread/processo escreve só na sua faixa.
      - Os índices são relativos à `grade` recebida. Na versão distribuída, o
        worker passa a fatia local (com halo) e calcula só as linhas internas.
    """
    nova_faixa: Grade = []

    for i in range(linha_ini, linha_fim):
        linha_atual = grade[i]
        nova_linha = []
        for j, estado in enumerate(linha_atual):
            if estado == IGNORANTE:
                if contar_vizinhos_espalhadores(grade, i, j) >= limiar_convencimento:
                    nova_linha.append(ESPALHADOR)
                else:
                    nova_linha.append(IGNORANTE)
            else:
                # ESPALHADOR -> INATIVO ; INATIVO -> INATIVO
                nova_linha.append(INATIVO)
        nova_faixa.append(nova_linha)

    return nova_faixa


def proxima_geracao(grade: Grade, limiar_convencimento: int = 2) -> Grade:
    """Próxima geração da grade inteira (versão sequencial)."""
    return calcular_faixa(grade, 0, len(grade), limiar_convencimento)


# ---------------------------------------------------------------------------
# Contagem, hash e utilitários
# ---------------------------------------------------------------------------

def contar_estados(grade: Grade) -> Dict[int, int]:
    """Conta células por estado na grade inteira."""
    contagem = {IGNORANTE: 0, ESPALHADOR: 0, INATIVO: 0}
    for linha in grade:
        for celula in linha:
            contagem[celula] += 1
    return contagem


def somar_contagens(contagens: List[Dict[int, int]]) -> Dict[int, int]:
    """Soma contagens parciais (ex.: uma por thread/worker) em uma total."""
    total = {IGNORANTE: 0, ESPALHADOR: 0, INATIVO: 0}
    for c in contagens:
        for estado in total:
            total[estado] += c[estado]
    return total


def registro_historico(geracao: int, contagem: Dict[int, int]) -> Dict[str, int]:
    """Formato único de cada entrada do histórico (usado por todas as versões)."""
    return {
        "geracao": geracao,
        "ignorantes": contagem[IGNORANTE],
        "espalhadores": contagem[ESPALHADOR],
        "inativos": contagem[INATIVO],
    }


def hash_grade(grade: Grade) -> str:
    """
    Impressão digital da grade. Duas grades iguais => mesmo hash.
    É o jeito mais barato de provar que as três versões chegaram ao mesmo estado.
    """
    h = hashlib.sha256()
    h.update(f"{len(grade)}x{len(grade[0])}".encode())
    for linha in grade:
        h.update(bytes(linha))  # estados são 0, 1 ou 2: cabem em 1 byte
    return h.hexdigest()


def dividir_linhas(total_linhas: int, partes: int) -> List[range]:
    """
    Divide `total_linhas` em `partes` faixas contíguas e balanceadas
    (diferença de no máximo 1 linha entre faixas). Retorna uma lista de `range`.
    Se partes > total_linhas, as faixas excedentes ficam vazias.
    Pensada para ser usada por threads (Pedro) e workers (Miguel).
    """
    base, resto = divmod(total_linhas, partes)
    faixas = []
    inicio = 0
    for k in range(partes):
        tamanho = base + (1 if k < resto else 0)
        faixas.append(range(inicio, inicio + tamanho))
        inicio += tamanho
    return faixas


# ---------------------------------------------------------------------------
# Simulação sequencial (referência para as outras versões)
# ---------------------------------------------------------------------------

def simular(config: Config,
            ao_final_de_geracao: Optional[Callable[[int, Grade, Dict[int, int]], None]] = None
            ) -> Resultado:
    """
    Executa a simulação sequencial completa.

    `ao_final_de_geracao(geracao, grade, contagem)` é um gancho opcional
    (impressão, visualização). O tempo medido inclui a chamada do gancho,
    então NÃO passe gancho nas medições de benchmark.

    Critério de parada (igual ao original): roda até `geracoes` ou até não
    restarem espalhadores. O tempo NÃO inclui a criação da grade inicial.
    """
    grade = criar_grade(config.linhas, config.colunas,
                        config.percentual_espalhadores, config.semente)

    historico: List[Dict[str, int]] = []
    executadas = 0

    inicio = time.perf_counter()

    for geracao in range(1, config.geracoes + 1):
        grade = proxima_geracao(grade, config.limiar_convencimento)
        contagem = contar_estados(grade)
        historico.append(registro_historico(geracao, contagem))
        executadas = geracao

        if ao_final_de_geracao is not None:
            ao_final_de_geracao(geracao, grade, contagem)

        if contagem[ESPALHADOR] == 0:
            break

    tempo = time.perf_counter() - inicio

    return Resultado(
        versao="sequencial",
        config=config,
        historico=historico,
        geracoes_executadas=executadas,
        tempo_s=tempo,
        grade_final=grade,
        hash_grade=hash_grade(grade),
    )
