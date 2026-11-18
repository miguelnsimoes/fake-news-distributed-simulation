"""Worker TCP persistente: mantém sua faixa e calcula uma geração por comando."""

import argparse
import logging
import math
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.core import calcular_faixa, contar_estados

if __package__:
    from .protocol import (codificar_linha, decodificar_linha, enviar_grade,
                           enviar_mensagem, receber_grade, receber_mensagem, receber_tipo)
else:
    from protocol import (codificar_linha, decodificar_linha, enviar_grade,
                          enviar_mensagem, receber_grade, receber_mensagem, receber_tipo)

TEMPO_LIMITE = 30.0


def estado_da_faixa(grade: list, geracao: int, tempo_calculo: float) -> dict:
    """Só bordas e contagens retornam durante as gerações; o miolo fica local."""
    contagem = contar_estados(grade)
    return {
        "tipo": "estado", "geracao": geracao,
        "primeira": codificar_linha(grade[0]) if grade else None,
        "ultima": codificar_linha(grade[-1]) if grade else None,
        "contagens": [contagem[0], contagem[1], contagem[2]],
        "tempo_calculo_s": tempo_calculo,
    }


def processar_tarefas(conexao: socket.socket) -> dict:
    """Recebe o bloco inicial e processa comandos até a finalização do servidor."""
    enviar_mensagem(conexao, {"tipo": "pronto", "protocolo": 1})
    inicio = receber_tipo(conexao, "iniciar")
    linhas, colunas = inicio["linhas"], inicio["colunas"]
    grade = receber_grade(conexao, linhas, colunas)
    enviar_mensagem(conexao, estado_da_faixa(grade, 0, 0.0))
    geracao = 0
    metricas = {"calculo_s": 0.0, "envio_s": 0.0, "recepcao_espera_s": 0.0}

    while True:
        comeco = time.perf_counter()
        comando = receber_mensagem(conexao)
        metricas["recepcao_espera_s"] += time.perf_counter() - comeco
        if comando.get("tipo") == "finalizar":
            enviar_mensagem(conexao, {"tipo": "final", "geracao": geracao, "metricas": metricas})
            enviar_grade(conexao, grade, colunas)
            return metricas
        if comando.get("tipo") != "calcular" or comando.get("geracao") != geracao + 1:
            raise ValueError("Comando ou número de geração inesperado.")

        fatia = []
        for chave, esperado in (("acima", inicio["tem_acima"]), ("abaixo", inicio["tem_abaixo"])):
            texto = comando.get(chave)
            if (texto is not None) != esperado:
                raise ValueError("Halo ausente ou inesperado.")
        if inicio["tem_acima"]:
            fatia.append(decodificar_linha(comando["acima"], colunas))
        offset = len(fatia)
        fatia.extend(grade)
        if inicio["tem_abaixo"]:
            fatia.append(decodificar_linha(comando["abaixo"], colunas))

        comeco = time.perf_counter()
        grade = calcular_faixa(fatia, offset, offset + linhas, inicio["limiar"])
        tempo_calculo = time.perf_counter() - comeco
        metricas["calculo_s"] += tempo_calculo
        geracao += 1
        estado = estado_da_faixa(grade, geracao, tempo_calculo)
        comeco = time.perf_counter()
        enviar_mensagem(conexao, estado)
        metricas["envio_s"] += time.perf_counter() - comeco


def executar_worker(host: str, porta: int, tempo_limite: float = TEMPO_LIMITE) -> dict:
    """Conecta uma vez; o socket permanece aberto durante toda a simulação."""
    with socket.create_connection((host, porta), timeout=tempo_limite) as conexao:
        conexao.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        logging.info("Worker conectado a %s:%s", host, porta)
        try:
            return processar_tarefas(conexao)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as erro:
            try:
                enviar_mensagem(conexao, {"tipo": "erro", "mensagem": str(erro)})
            except (OSError, ValueError):
                pass
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Worker da simulação distribuída via TCP.")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço do servidor.")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--timeout", type=float, default=TEMPO_LIMITE)
    parser.add_argument("--silencioso", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("Use uma porta de 1 a 65535 e um timeout positivo finito.")
    logging.basicConfig(level=logging.WARNING if args.silencioso else logging.INFO, format="%(message)s")
    try:
        metricas = executar_worker(args.host, args.port, args.timeout)
        logging.info("Worker finalizado: %s", metricas)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as erro:
        logging.error("Erro no worker: %s", erro)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
