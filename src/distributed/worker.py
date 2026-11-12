"""Worker TCP: recebe a saudação do servidor e envia uma resposta JSON."""

import argparse
import socket

from protocol import enviar_mensagem, receber_mensagem


TEMPO_LIMITE = 10  # Segundos de espera por operações de comunicação.


def executar_worker(host: str, porta: int) -> None:
    """Conecta, recebe uma mensagem, responde e fecha a conexão."""
    with socket.create_connection((host, porta), timeout=TEMPO_LIMITE) as conexao:
        print(f"Conectado ao servidor {host}:{porta}.")
        mensagem = receber_mensagem(conexao)
        print(f"Mensagem recebida: {mensagem}")

        resposta = {
            "tipo": "resposta",
            "mensagem": "Worker recebeu a mensagem com sucesso.",
        }
        enviar_mensagem(conexao, resposta)
        print("Resposta enviada. Encerrando conexão.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Worker TCP de demonstração.")
    parser.add_argument("--host", default="127.0.0.1", help="Endereço do servidor.")
    parser.add_argument("--port", type=int, default=5000, help="Porta TCP (padrão: 5000).")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("A porta deve estar entre 1 e 65535.")

    try:
        executar_worker(args.host, args.port)
    except KeyboardInterrupt:
        print("\nWorker encerrado.")
    except (OSError, ValueError) as erro:
        print(f"Erro de comunicação: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
