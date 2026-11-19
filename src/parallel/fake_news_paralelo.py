"""Versão paralela: blocos de linhas divididos entre threads ou processos.

Correção:
- buffer duplo: a geração g lê a grade g % 2 e escreve na (g + 1) % 2;
- cada linha de destino tem um único dono (bloco fixo ou pedaço tirado sob lock);
- uma barreira por geração; cada worker conta as próprias linhas em posição
  exclusiva, e todos somam as mesmas parcelas para decidir a parada.

Detalhes e medições em docs/versao-paralela.md.
"""

from __future__ import annotations

import argparse
import multiprocessing
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Sequence, Union

# src/sequential: varredura.py e os testes importam o código original.
_SRC = Path(__file__).resolve().parents[1]
for _pasta in (_SRC, _SRC / "sequential"):
    if str(_pasta) not in sys.path:
        sys.path.insert(0, str(_pasta))

from common import core  # noqa: E402
from common.core import ESPALHADOR, IGNORANTE, INATIVO, criar_grade  # noqa: E402
from common.energia import desligar_economia_de_energia  # noqa: E402
from common.kernels import KERNELS, Kernel, obter_kernel  # noqa: E402

BACKENDS = ("threads", "processos")
DIVISOES = ("estatica", "dinamica")

# Indexada pelo código do estado: (ignorantes, espalhadores, inativos).
Contagem = tuple[int, int, int]
Ler = Callable[[int, int], bytes]
Escrever = Callable[[int, int, bytes], None]


@dataclass
class ResultadoSimulacao:

    grade_final: list[list[int]]
    historico: list[Contagem]
    tempo_geracoes_s: float
    tempo_total_s: float  # inclui criar e encerrar os workers
    tempo_calculo_s: list[float]  # por worker
    tempo_caminho_critico_s: float  # soma do worker mais lento de cada geração
    backend: str
    workers: int
    kernel: str
    divisao: str
    pedaco: int  # 0 na divisão estática

    @property
    def geracoes_executadas(self) -> int:
        return len(self.historico)

    @property
    def desbalanceamento(self) -> float:
        """Worker mais lento / média (1,0 = equilibrado)."""
        medio = sum(self.tempo_calculo_s) / self.workers
        return self.tempo_caminho_critico_s / medio if medio > 0 else 1.0

    @property
    def tempo_sincronizacao_s(self) -> float:
        """Tempo fora do cálculo do worker mais lento: barreiras e coordenação."""
        return max(0.0, self.tempo_geracoes_s - self.tempo_caminho_critico_s)


@dataclass(frozen=True)
class _Tarefa:
    rank: int
    inicio: int  # bloco da divisão estática
    fim: int
    workers: int
    total_linhas: int
    colunas: int
    geracoes: int
    limiar: int
    kernel: Kernel
    pedaco: int  # 0 = divisão estática


def dividir_linhas(total_linhas: int, partes: int) -> list[tuple[int, int]]:
    """``core.dividir_linhas`` em tuplas ``(inicio, fim)``."""
    if partes < 1:
        raise ValueError("É preciso pelo menos 1 worker.")
    return [(faixa.start, faixa.stop) for faixa in core.dividir_linhas(total_linhas, partes)]


def tamanho_pedaco_automatico(total_linhas: int, workers: int) -> int:
    """Cerca de 8 pedaços por worker: equilibra sem disputar demais o lock."""
    return max(1, total_linhas // (workers * 8))


def _posicao(paridade: int, rank: int, workers: int) -> int:
    return (paridade * workers + rank) * 3


def _somar(contagens: Sequence[int], paridade: int, workers: int) -> Contagem:
    inicio = paridade * workers * 3
    parcelas = contagens[inicio : inicio + workers * 3]
    return (sum(parcelas[0::3]), sum(parcelas[1::3]), sum(parcelas[2::3]))


def _faixas(tarefa: _Tarefa, paridade: int, fila: Any) -> Iterator[tuple[int, int]]:
    if tarefa.pedaco == 0:
        if tarefa.inicio < tarefa.fim:
            yield tarefa.inicio, tarefa.fim
        return

    proximo, trava = fila  # um contador por paridade de geração
    while True:
        with trava:
            numero = proximo[paridade]
            proximo[paridade] = numero + 1
        inicio = numero * tarefa.pedaco
        if inicio >= tarefa.total_linhas:
            return
        yield inicio, min(inicio + tarefa.pedaco, tarefa.total_linhas)


def _calcular_faixa(
    tarefa: _Tarefa, inicio: int, fim: int, origem: int, destino: int,
    ler: Ler, escrever: Escrever,
) -> tuple[int, int]:
    """Devolve (ignorantes, espalhadores) das linhas calculadas."""
    calcular = tarefa.kernel
    limiar = tarefa.limiar
    ultima = tarefa.total_linhas - 1
    ignorantes = espalhadores = 0
    acima = ler(origem, inicio - 1) if inicio > 0 else None
    atual = ler(origem, inicio)
    for i in range(inicio, fim):
        abaixo = ler(origem, i + 1) if i < ultima else None
        nova = calcular(acima, atual, abaixo, limiar)
        escrever(destino, i, nova)
        ignorantes += nova.count(IGNORANTE)
        espalhadores += nova.count(ESPALHADOR)
        acima, atual = atual, abaixo
    return ignorantes, espalhadores


def _trabalhar(
    tarefa: _Tarefa, ler: Ler, escrever: Escrever,
    contagens: Any, tempos: Any, barreira: Any, fila: Any,
) -> None:
    """Laço de um worker, igual para threads e processos."""
    barreira.wait()  # largada: o tempo só começa com todos prontos

    for geracao in range(tarefa.geracoes):
        origem = geracao % 2
        destino = 1 - origem
        comeco = time.perf_counter()

        ignorantes = espalhadores = linhas = 0
        for inicio, fim in _faixas(tarefa, origem, fila):
            ign, esp = _calcular_faixa(tarefa, inicio, fim, origem, destino, ler, escrever)
            ignorantes += ign
            espalhadores += esp
            linhas += fim - inicio

        base = _posicao(origem, tarefa.rank, tarefa.workers)
        contagens[base + IGNORANTE] = ignorantes
        contagens[base + ESPALHADOR] = espalhadores
        contagens[base + INATIVO] = linhas * tarefa.colunas - ignorantes - espalhadores
        tempos[tarefa.rank * tarefa.geracoes + geracao] = time.perf_counter() - comeco

        barreira.wait()
        if _somar(contagens, origem, tarefa.workers)[ESPALHADOR] == 0:
            return


def _coordenar(
    barreira: Any, contagens: Any, workers: int, geracoes: int, proximo: Any
) -> tuple[list[Contagem], float]:
    """Laço do fluxo principal: registra as contagens de cada geração."""
    barreira.wait()
    comeco = time.perf_counter()
    historico: list[Contagem] = []
    for geracao in range(geracoes):
        barreira.wait()
        paridade = geracao % 2
        totais = _somar(contagens, paridade, workers)
        historico.append(totais)
        # Só volta a ser usado em geracao + 2, depois da próxima barreira: zerar sem lock é seguro.
        proximo[paridade] = 0
        if totais[ESPALHADOR] == 0:
            break
    return historico, time.perf_counter() - comeco


# (linhas finais, histórico, tempo das gerações, tempos[worker * geracoes + geração])
_SaidaBackend = tuple[list[bytes], list[Contagem], float, Sequence[float]]


def _rodar_threads(linhas: list[bytes], tarefas: list[_Tarefa]) -> _SaidaBackend:
    workers = len(tarefas)
    geracoes = tarefas[0].geracoes
    # Linhas imutáveis: escrever é trocar a referência, e a leitura nunca vê linha pela metade.
    grades: list[list[bytes]] = [list(linhas), list(linhas)]
    contagens = [0] * (2 * workers * 3)
    tempos = [0.0] * (workers * geracoes)
    proximo = [0, 0]
    fila = (proximo, threading.Lock())
    barreira = threading.Barrier(workers + 1)
    falhas: list[BaseException] = []

    def ler(grade: int, i: int) -> bytes:
        return grades[grade][i]

    def escrever(grade: int, i: int, linha: bytes) -> None:
        grades[grade][i] = linha

    def trabalhar(tarefa: _Tarefa) -> None:
        try:
            _trabalhar(tarefa, ler, escrever, contagens, tempos, barreira, fila)
        except threading.BrokenBarrierError:
            pass  # quem falhou já registrou o erro
        except BaseException as erro:
            falhas.append(erro)
            barreira.abort()  # evita deadlock dos demais

    threads = [
        threading.Thread(
            target=trabalhar, args=(tarefa,), name=f"worker-{tarefa.rank}", daemon=True
        )
        for tarefa in tarefas
    ]
    for thread in threads:
        thread.start()

    historico: Optional[list[Contagem]] = None
    tempo = 0.0
    try:
        historico, tempo = _coordenar(barreira, contagens, workers, geracoes, proximo)
    except threading.BrokenBarrierError:
        pass
    except BaseException:
        barreira.abort()
        raise
    finally:
        for thread in threads:
            thread.join()

    if falhas:
        raise RuntimeError(f"Uma thread falhou: {falhas[0]!r}") from falhas[0]
    if historico is None:
        raise RuntimeError("A barreira foi quebrada sem erro registrado.")
    return grades[len(historico) % 2], historico, tempo, tempos


def _trabalhador_processo(
    tarefa: _Tarefa, memoria: Any, contagens: Any, tempos: Any,
    barreira: Any, proximo: Any, trava: Any,
) -> None:
    """Ponto de entrada de cada processo (global por causa do spawn)."""
    desligar_economia_de_energia()  # não é herdado do processo pai
    visao = memoryview(memoria).cast("B")
    tamanho_grade = tarefa.total_linhas * tarefa.colunas
    colunas = tarefa.colunas

    def ler(grade: int, i: int) -> bytes:
        posicao = grade * tamanho_grade + i * colunas
        return bytes(visao[posicao : posicao + colunas])

    def escrever(grade: int, i: int, linha: bytes) -> None:
        posicao = grade * tamanho_grade + i * colunas
        visao[posicao : posicao + colunas] = linha

    try:
        _trabalhar(tarefa, ler, escrever, contagens, tempos, barreira, (proximo, trava))
    except threading.BrokenBarrierError:
        raise SystemExit(2) from None  # outro participante falhou
    except BaseException:
        barreira.abort()  # evita deadlock dos demais
        raise
    finally:
        visao.release()


def _rodar_processos(linhas: list[bytes], tarefas: list[_Tarefa]) -> _SaidaBackend:
    workers = len(tarefas)
    geracoes = tarefas[0].geracoes
    colunas = tarefas[0].colunas
    tamanho_grade = len(linhas) * colunas

    # As duas grades do buffer duplo, lado a lado.
    memoria = multiprocessing.RawArray("B", 2 * tamanho_grade)
    visao = memoryview(memoria).cast("B")
    for i, linha in enumerate(linhas):
        visao[i * colunas : (i + 1) * colunas] = linha

    # Sem lock: cada processo escreve só nas próprias posições.
    contagens = multiprocessing.RawArray("q", 2 * workers * 3)
    tempos = multiprocessing.RawArray("d", max(1, workers * geracoes))
    proximo = multiprocessing.RawArray("q", 2)
    trava = multiprocessing.Lock()
    barreira = multiprocessing.Barrier(workers + 1)

    processos = [
        multiprocessing.Process(
            target=_trabalhador_processo,
            args=(tarefa, memoria, contagens, tempos, barreira, proximo, trava),
            name=f"worker-{tarefa.rank}",
            daemon=True,
        )
        for tarefa in tarefas
    ]
    for processo in processos:
        processo.start()

    historico: Optional[list[Contagem]] = None
    tempo = 0.0
    try:
        historico, tempo = _coordenar(barreira, contagens, workers, geracoes, proximo)
    except threading.BrokenBarrierError:
        pass
    except BaseException:
        barreira.abort()
        raise
    finally:
        for processo in processos:
            processo.join()

    com_erro = [p.name for p in processos if p.exitcode != 0]
    if historico is None or com_erro:
        visao.release()
        raise RuntimeError(
            f"Processo(s) com erro: {', '.join(com_erro) or '?'} "
            "(o traceback aparece acima)."
        )

    inicio = (len(historico) % 2) * tamanho_grade
    final = [
        bytes(visao[inicio + i * colunas : inicio + (i + 1) * colunas])
        for i in range(len(linhas))
    ]
    visao.release()
    return final, historico, tempo, tempos[:]


def _tempos_de_calculo(
    tempos: Sequence[float], workers: int, geracoes: int, executadas: int
) -> tuple[list[float], float]:
    """(tempo de cálculo por worker, soma do worker mais lento de cada geração)."""
    por_worker = [
        list(tempos[rank * geracoes : rank * geracoes + executadas])
        for rank in range(workers)
    ]
    caminho_critico = sum(max(geracao) for geracao in zip(*por_worker))
    return [sum(serie) for serie in por_worker], caminho_critico


def simular_paralelo(
    grade_inicial: Sequence[Sequence[int]],
    geracoes: int,
    limiar_convencimento: int = 2,
    workers: int = 4,
    backend: str = "threads",
    kernel: Union[str, Kernel] = "otimizado",
    divisao: str = "estatica",
    pedaco: Optional[int] = None,
) -> ResultadoSimulacao:
    """Mesma regra e parada da sequencial. ``pedaco`` só vale na divisão dinâmica."""
    if backend not in BACKENDS:
        raise ValueError(f"backend deve ser um de {BACKENDS}, não {backend!r}.")
    if divisao not in DIVISOES:
        raise ValueError(f"divisao deve ser uma de {DIVISOES}, não {divisao!r}.")
    if workers < 1:
        raise ValueError("É preciso pelo menos 1 worker.")
    if geracoes < 0:
        raise ValueError("O número de gerações não pode ser negativo.")
    if pedaco is not None and pedaco < 1:
        raise ValueError("O pedaço precisa ter pelo menos 1 linha.")

    linhas = [bytes(linha) for linha in grade_inicial]
    if not linhas or not linhas[0]:
        raise ValueError("A grade precisa ter pelo menos 1 linha e 1 coluna.")
    colunas = len(linhas[0])
    if any(len(linha) != colunas for linha in linhas):
        raise ValueError("Todas as linhas da grade precisam ter o mesmo tamanho.")

    calcular = obter_kernel(kernel)
    nome_kernel = kernel if isinstance(kernel, str) else getattr(kernel, "__name__", "?")
    tamanho_pedaco = 0
    if divisao == "dinamica":
        tamanho_pedaco = pedaco or tamanho_pedaco_automatico(len(linhas), workers)
    tarefas = [
        _Tarefa(rank, inicio, fim, workers, len(linhas), colunas, geracoes,
                limiar_convencimento, calcular, tamanho_pedaco)
        for rank, (inicio, fim) in enumerate(dividir_linhas(len(linhas), workers))
    ]

    comeco = time.perf_counter()
    rodar = _rodar_threads if backend == "threads" else _rodar_processos
    final, historico, tempo_geracoes, tempos = rodar(linhas, tarefas)
    tempo_total = time.perf_counter() - comeco
    por_worker, caminho_critico = _tempos_de_calculo(
        tempos, workers, geracoes, len(historico))

    return ResultadoSimulacao(
        grade_final=[list(linha) for linha in final],
        historico=historico,
        tempo_geracoes_s=tempo_geracoes,
        tempo_total_s=tempo_total,
        tempo_calculo_s=por_worker,
        tempo_caminho_critico_s=caminho_critico,
        backend=backend,
        workers=workers,
        kernel=nome_kernel,
        divisao=divisao,
        pedaco=tamanho_pedaco,
    )


def gil_ativo() -> bool:
    """False só no CPython free-threaded (3.13t+) com o GIL desligado."""
    verificar = getattr(sys, "_is_gil_enabled", None)
    return True if verificar is None else bool(verificar())


def _argumentos(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulação paralela de propagação de fake news."
    )
    parser.add_argument("--linhas", type=int, default=100)
    parser.add_argument("--colunas", type=int, default=100)
    parser.add_argument("--geracoes", type=int, default=50)
    parser.add_argument("--espalhadores", type=float, default=0.05,
                        help="Fração inicial de espalhadores (0.05 = 5%%).")
    parser.add_argument("--limiar", type=int, default=3,
                        help="Vizinhos espalhadores necessários para convencer.")
    parser.add_argument("--semente", type=int, default=42)
    parser.add_argument("-w", "--workers", "--threads", dest="workers", type=int,
                        default=4, help="Número de threads ou processos.")
    parser.add_argument("--backend", choices=BACKENDS, default="threads")
    parser.add_argument("--kernel", choices=sorted(KERNELS), default="otimizado")
    parser.add_argument("--divisao", choices=DIVISOES, default="estatica")
    parser.add_argument("--pedaco", type=int,
                        help="Linhas por pedaço na divisão dinâmica (padrão: automático).")
    parser.add_argument("--sem-geracoes", action="store_true",
                        help="Não imprime a linha de cada geração.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _argumentos(argv)
    desligar_economia_de_energia()
    grade = criar_grade(args.linhas, args.colunas, args.espalhadores, args.semente)
    total = args.linhas * args.colunas
    espalhadores_iniciais = sum(linha.count(ESPALHADOR) for linha in grade)

    print("=== SIMULAÇÃO PARALELA DE PROPAGAÇÃO DE FAKE NEWS ===")
    divisao = args.divisao
    if args.divisao == "dinamica":
        pedaco = args.pedaco or tamanho_pedaco_automatico(args.linhas, args.workers)
        divisao += f" ({pedaco} linhas por pedaço)"
    print(f"Backend: {args.backend} | Workers: {args.workers} | Divisão: {divisao} | "
          f"Kernel: {args.kernel} | GIL: {'ativo' if gil_ativo() else 'desligado'}")
    print(f"Tamanho da grade: {args.linhas} x {args.colunas} ({total:,} pessoas)")
    print(f"Gerações: {args.geracoes}")
    print(f"Percentual inicial de espalhadores: {args.espalhadores * 100:.2f}% "
          f"({espalhadores_iniciais:,} espalhadores reais)")
    print(f"Limiar de convencimento: {args.limiar} vizinhos")
    print()

    resultado = simular_paralelo(grade, args.geracoes, args.limiar, args.workers,
                                 args.backend, args.kernel, args.divisao, args.pedaco)

    # Impresso depois para não entrar no tempo medido.
    if not args.sem_geracoes:
        for numero, (ign, esp, ina) in enumerate(resultado.historico, start=1):
            print(f"Geração {numero:03d} | Ignorantes: {ign:>10,} | "
                  f"Espalhadores: {esp:>10,} | Inativos: {ina:>10,}")
        if resultado.historico and resultado.historico[-1][ESPALHADOR] == 0:
            print("\nA propagação terminou: não há mais espalhadores.")

    ign, esp, ina = resultado.historico[-1] if resultado.historico else (
        total - espalhadores_iniciais, espalhadores_iniciais, 0)
    print()
    print("=== RESULTADO FINAL ===")
    print(f"Tempo das gerações: {resultado.tempo_geracoes_s:.4f} s "
          f"(total com criação dos workers: {resultado.tempo_total_s:.4f} s)")
    print(f"Desbalanceamento: {resultado.desbalanceamento:.2f} | "
          f"Sincronização: {resultado.tempo_sincronizacao_s:.4f} s")
    print(f"Ignorantes finais: {ign:,} ({ign / total * 100:,.2f}%)")
    print(f"Espalhadores finais: {esp:,} ({esp / total * 100:,.2f}%)")
    print(f"Inativos finais: {ina:,} ({ina / total * 100:,.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
