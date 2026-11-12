"""Servidor TCP: recebe workers e realiza uma troca de mensagens com cada um."""

import argparse
import logging
import socket
import threading

from protocol import enviar_mensagem, receber_mensagem


TEMPO_LIMITE = 10  # Segundos de espera por operações de comunicação.


def atender_worker(conexao: socket.socket, endereco: tuple) -> None:
    """Atende uma conexão; o contexto fecha o socket mesmo em caso de erro."""
    with conexao:
        conexao.settimeout(TEMPO_LIMITE)
        try:
            logging.info("Worker conectado: %s", endereco)
            enviar_mensagem(conexao, {
                "tipo": "boas_vindas",
                "mensagem": "Olá, worker! Conexão estabelecida.",
            })
            resposta = receber_mensagem(conexao)
            logging.info("Resposta de %s: %s", endereco, resposta)
        except (OSError, ValueError) as erro:
            logging.error("Erro de comunicação com %s: %s", endereco, erro)

    logging.info("Conexão encerrada: %s", endereco)


def executar_servidor(host: str, porta: int) -> None:
    """Aceita conexões continuamente, usando uma thread por worker."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.bind((host, porta))
        servidor.listen()
        # Permite verificar Ctrl+C periodicamente, mesmo sem novas conexões.
        servidor.settimeout(1)
        logging.info("Servidor ouvindo em %s:%s. Encerre com Ctrl+C.", host, porta)

        while True:
            try:
                conexao, endereco = servidor.accept()
            except socket.timeout:
                continue

            # Cada thread atende apenas seu socket; não há estado compartilhado.
            thread = threading.Thread(
                target=atender_worker,
                args=(conexao, endereco),
                daemon=True,
            )
            thread.start()


def main() -> int:
    # O logging evita misturar os registros escritos por threads diferentes.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Servidor TCP de demonstração.")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço de escuta.")
    parser.add_argument("--port", type=int, default=5000, help="Porta TCP (padrão: 5000).")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("A porta deve estar entre 1 e 65535.")

    try:
        executar_servidor(args.host, args.port)
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    except OSError as erro:
        print(f"Não foi possível executar o servidor: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
