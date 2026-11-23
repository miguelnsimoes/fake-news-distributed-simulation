"""Coordenador TCP: distribui faixas, encaminha halos e sincroniza gerações."""

import argparse
from dataclasses import asdict, dataclass, field
import json
import logging
import math
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.argumentos import adicionar_extensoes, extensoes_de
from common.core import (KERNEL_PADRAO, KERNELS, Config, Grade, Resultado, criar_grade,
                         dividir_linhas, hash_grade, preparar_extensoes, registro_historico,
                         somar_contagens)
from common.energia import desligar_economia_de_energia
from common.modelo import Modelo

if __package__:
    from .protocol import (LIMITE_MENSAGEM, decodificar_linha, enviar_grade,
                           enviar_mensagem, receber_grade, receber_tipo)
else:
    from protocol import (LIMITE_MENSAGEM, decodificar_linha, enviar_grade,
                          enviar_mensagem, receber_grade, receber_tipo)

TEMPO_LIMITE = 30.0
# Versão 3: "iniciar" passou a levar o modelo, a linha inicial e os tipos.
VERSAO_PROTOCOLO = 3


@dataclass
class ResultadoDistribuido(Resultado):
    """``Resultado`` com as medições de comunicação."""
    metricas: dict = field(default_factory=dict)

    def para_dict(self, incluir_grade: bool = False) -> dict:
        dados = super().para_dict(incluir_grade)
        dados["metricas"] = self.metricas
        return dados


def validar_config(config: Config, porta: int, tempo_limite: float) -> None:
    for nome in ("linhas", "colunas", "num_processos"):
        valor = getattr(config, nome)
        if type(valor) is not int or valor < 1:
            raise ValueError(f"{nome} deve ser um inteiro positivo.")
    for nome in ("geracoes", "limiar_convencimento"):
        valor = getattr(config, nome)
        if type(valor) is not int or valor < 0:
            raise ValueError(f"{nome} deve ser um inteiro não negativo.")
    if not math.isfinite(config.percentual_espalhadores) or not 0 <= config.percentual_espalhadores <= 1:
        raise ValueError("O percentual deve estar entre 0 e 1.")
    if config.kernel not in KERNELS:
        raise ValueError(f"kernel deve ser um de {sorted(KERNELS)}.")
    # Duas bordas precisam caber numa mensagem de controle.
    if config.colunas > LIMITE_MENSAGEM // 4:
        raise ValueError("A largura máxima é LIMITE_MENSAGEM // 4 colunas.")
    if not 0 <= porta <= 65535 or not math.isfinite(tempo_limite) or tempo_limite <= 0:
        raise ValueError("Porta inválida ou timeout não positivo/finito.")


def receber_estado(conexao: socket.socket, geracao: int, linhas: int, colunas: int) -> dict:
    estado = receber_tipo(conexao, "estado")
    if estado.get("geracao") != geracao:
        raise ValueError("Worker respondeu com uma geração incorreta.")
    contagens = estado.get("contagens")
    if (not isinstance(contagens, list) or len(contagens) != 3
            or any(type(n) is not int or n < 0 for n in contagens)
            or sum(contagens) != linhas * colunas):
        raise ValueError("Contagens do worker inconsistentes.")
    for chave in ("primeira", "ultima"):
        if linhas:
            decodificar_linha(estado.get(chave), colunas)
        elif estado.get(chave) is not None:
            raise ValueError("Worker sem linhas enviou uma fronteira.")
    tempo = estado.get("tempo_calculo_s")
    if not isinstance(tempo, (int, float)) or not math.isfinite(tempo) or tempo < 0:
        raise ValueError("Tempo de cálculo inválido.")
    return estado


def iniciar_workers(quantidade: int, porta: int, tempo_limite: float, processos: list) -> None:
    script = Path(__file__).with_name("worker.py")
    for _ in range(quantidade):
        processos.append(subprocess.Popen(
            [sys.executable, "-B", str(script), "--host", "127.0.0.1",
             "--port", str(porta), "--timeout", str(tempo_limite), "--silencioso"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ))


def encerrar_recursos(conexoes: list, processos: list) -> None:
    for conexao in conexoes:
        try:
            conexao.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        conexao.close()
    limite = time.monotonic() + 3
    for processo in processos:
        try:
            processo.wait(timeout=max(0, limite - time.monotonic()))
        except subprocess.TimeoutExpired:
            processo.terminate()
            try:
                processo.wait(timeout=2)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=2)


def validar_grade(grade: Grade, config: Config) -> List[List[int]]:
    copia = [list(linha) for linha in grade]
    if len(copia) != config.linhas or any(len(linha) != config.colunas for linha in copia):
        raise ValueError("A grade inicial não tem as dimensões de config.")
    if any(celula not in (0, 1, 2) for linha in copia for celula in linha):
        raise ValueError("Os estados da grade devem ser 0, 1 ou 2.")
    return copia


def executar_servidor(config: Config, host: str = "127.0.0.1", porta: int = 5000,
                      *, automaticos: bool = False, tempo_limite: float = TEMPO_LIMITE,
                      grade_inicial: Optional[Grade] = None, tipos: Optional[Grade] = None,
                      modelo: Optional[Modelo] = None) -> ResultadoDistribuido:
    """Executa uma simulação; no modo manual, aguarda num_processos workers.

    ``tempo_s`` mede o laço de gerações (com TCP e barreira); o restante fica em
    ``metricas``. Com ``grade_inicial``, o estado inicial vem pronto do chamador
    (com ``tipos`` e ``modelo``, como em ``core.preparar_inicio``) e os campos de
    config sobre espalhadores, semente e extensões são ignorados.
    """
    validar_config(config, porta, tempo_limite)
    if grade_inicial is None:
        if tipos is not None or modelo is not None:
            raise ValueError("tipos e modelo só valem junto com grade_inicial.")
        grade = criar_grade(config.linhas, config.colunas, config.percentual_espalhadores,
                            config.semente)
        tipos, modelo = preparar_extensoes(config, grade)
    else:
        grade = validar_grade(grade_inicial, config)
        if tipos is not None:
            if modelo is None:
                raise ValueError("tipos exige um modelo.")
            tipos = validar_grade(tipos, config)
    metricas = {
        "inicializacao_s": 0.0, "finalizacao_s": 0.0, "total_s": 0.0,
        "envio_coordenador_s": 0.0, "recepcao_espera_coordenador_s": 0.0,
        "caminho_critico_calculo_s": 0.0, "celulas_halo_enviadas": 0, "workers": [],
    }
    if config.geracoes == 0:
        return ResultadoDistribuido(versao="distribuida", config=config, grade_final=grade,
                                    hash_grade=hash_grade(grade), metricas=metricas)

    faixas = dividir_linhas(config.linhas, config.num_processos)
    conexoes, processos, estados, historico = [], [], [], []
    inicio_total = time.perf_counter()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
            servidor.bind((host, porta))
            servidor.listen(config.num_processos)
            porta_real = servidor.getsockname()[1]
            logging.info("Servidor ouvindo em %s:%s; aguardando %s workers.",
                         host, porta_real, config.num_processos)
            if automaticos:
                if host != "127.0.0.1":
                    raise ValueError("Workers automáticos usam apenas o host local 127.0.0.1.")
                iniciar_workers(config.num_processos, porta_real, tempo_limite, processos)

            # Prazo global para todos os workers conectarem.
            limite = time.monotonic() + tempo_limite
            for rank in range(config.num_processos):
                servidor.settimeout(max(0.001, limite - time.monotonic()))
                conexao, endereco = servidor.accept()
                conexoes.append(conexao)
                conexao.settimeout(max(0.001, limite - time.monotonic()))
                conexao.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                if receber_tipo(conexao, "pronto").get("protocolo") != VERSAO_PROTOCOLO:
                    raise ValueError("Versão de protocolo incompatível: atualize o worker.")
                logging.info("Worker %s conectado: %s", rank, endereco)
                conexao.settimeout(tempo_limite)

            for conexao, faixa in zip(conexoes, faixas):
                tem_acima = bool(faixa) and faixa.start > 0
                tem_abaixo = bool(faixa) and faixa.stop < config.linhas
                enviar_mensagem(conexao, {
                    "tipo": "iniciar", "linhas": len(faixa), "colunas": config.colunas,
                    "limiar": config.limiar_convencimento, "kernel": config.kernel,
                    "tem_acima": tem_acima, "tem_abaixo": tem_abaixo,
                    "linha_inicial": faixa.start,
                    "modelo": None if modelo is None else asdict(modelo),
                    "tem_tipos": tipos is not None,
                })
                enviar_grade(conexao, grade[faixa.start:faixa.stop], config.colunas)
                if tipos is not None:
                    # Os tipos são fixos: vão uma vez, já com as linhas do halo.
                    enviar_grade(conexao, tipos[faixa.start - tem_acima:faixa.stop + tem_abaixo],
                                 config.colunas)
                estados.append(receber_estado(conexao, 0, len(faixa), config.colunas))
            metricas["inicializacao_s"] = time.perf_counter() - inicio_total

            inicio_geracoes = time.perf_counter()
            for geracao in range(1, config.geracoes + 1):
                for rank, (conexao, faixa) in enumerate(zip(conexoes, faixas)):
                    acima = estados[rank - 1]["ultima"] if faixa and faixa.start > 0 else None
                    abaixo = estados[rank + 1]["primeira"] if faixa and faixa.stop < config.linhas else None
                    comeco = time.perf_counter()
                    enviar_mensagem(conexao, {
                        "tipo": "calcular", "geracao": geracao, "acima": acima, "abaixo": abaixo,
                    })
                    metricas["envio_coordenador_s"] += time.perf_counter() - comeco
                    metricas["celulas_halo_enviadas"] += len(acima or "") + len(abaixo or "")

                # Barreira: os próximos halos só saem depois de todos responderem.
                comeco = time.perf_counter()
                estados = [receber_estado(c, geracao, len(f), config.colunas)
                           for c, f in zip(conexoes, faixas)]
                metricas["recepcao_espera_coordenador_s"] += time.perf_counter() - comeco
                metricas["caminho_critico_calculo_s"] += max(e["tempo_calculo_s"] for e in estados)
                contagem = somar_contagens([dict(enumerate(e["contagens"])) for e in estados])
                historico.append(registro_historico(geracao, contagem))
                if contagem[1] == 0:
                    break
            tempo_geracoes = time.perf_counter() - inicio_geracoes

            inicio_finalizacao = time.perf_counter()
            for conexao in conexoes:
                enviar_mensagem(conexao, {"tipo": "finalizar"})
            grade = []
            for conexao, faixa in zip(conexoes, faixas):
                final = receber_tipo(conexao, "final")
                if final.get("geracao") != len(historico):
                    raise ValueError("Geração final do worker inconsistente.")
                metricas["workers"].append(final["metricas"])
                grade.extend(receber_grade(conexao, len(faixa), config.colunas))
            metricas["finalizacao_s"] = time.perf_counter() - inicio_finalizacao
    finally:
        encerrar_recursos(conexoes, processos)
    metricas["total_s"] = time.perf_counter() - inicio_total
    return ResultadoDistribuido(
        versao="distribuida", config=config, historico=historico,
        geracoes_executadas=len(historico), tempo_s=tempo_geracoes,
        grade_final=grade, hash_grade=hash_grade(grade), metricas=metricas,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulação distribuída com workers TCP.")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço de escuta do servidor.")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--automaticos", action="store_true", help="Inicia workers locais automaticamente.")
    parser.add_argument("--timeout", type=float, default=TEMPO_LIMITE)
    parser.add_argument("-l", "--linhas", type=int, default=100)
    parser.add_argument("-c", "--colunas", type=int, default=100)
    parser.add_argument("-g", "--geracoes", type=int, default=50)
    parser.add_argument("-p", "--percentual", type=float, default=0.05)
    parser.add_argument("-t", "--limiar", type=int, default=3)
    parser.add_argument("-s", "--semente", type=int, default=42)
    parser.add_argument("--kernel", choices=sorted(KERNELS), default=KERNEL_PADRAO,
                        help="Cálculo de cada linha (common/kernels.py), repassado aos workers.")
    adicionar_extensoes(parser)
    parser.add_argument("--saida", type=Path)
    parser.add_argument("--incluir-grade", action="store_true")
    parser.add_argument("--silencioso", action="store_true")
    args = parser.parse_args()
    config = Config(linhas=args.linhas, colunas=args.colunas, geracoes=args.geracoes,
                    percentual_espalhadores=args.percentual, limiar_convencimento=args.limiar,
                    semente=args.semente, num_processos=args.workers, kernel=args.kernel,
                    **extensoes_de(args))
    logging.basicConfig(level=logging.WARNING if args.silencioso else logging.INFO, format="%(message)s")
    desligar_economia_de_energia()
    try:
        resultado = executar_servidor(config, args.host, args.port,
                                      automaticos=args.automaticos, tempo_limite=args.timeout)
        if args.saida:
            args.saida.write_text(json.dumps(resultado.para_dict(args.incluir_grade),
                                            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"distribuida geracoes={resultado.geracoes_executadas} "
              f"tempo_s={resultado.tempo_s:.6f} hash={resultado.hash_grade}")
        if not args.silencioso:
            print(json.dumps(resultado.metricas, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as erro:
        logging.error("Erro no servidor: %s", erro)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
