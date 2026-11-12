"""Mensagens JSON em UTF-8 com prefixo de tamanho de quatro bytes."""

import json
import socket
import struct


TAMANHO_PREFIXO = 4
LIMITE_MENSAGEM = 1024 * 1024  # Um MiB por mensagem nesta etapa.


def receber_bytes(conexao: socket.socket, quantidade: int) -> bytes:
    """Lê exatamente a quantidade solicitada, mesmo com recepção parcial."""
    dados = bytearray()
    while len(dados) < quantidade:
        parte = conexao.recv(quantidade - len(dados))
        if not parte:
            raise ConnectionError("O outro participante encerrou a conexão.")
        dados.extend(parte)
    return bytes(dados)


def enviar_mensagem(conexao: socket.socket, mensagem: dict) -> None:
    """Envia o tamanho em bytes seguido do objeto JSON codificado em UTF-8."""
    if not isinstance(mensagem, dict):
        raise ValueError("A mensagem deve ser um objeto JSON (dicionário).")

    dados = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
    if len(dados) > LIMITE_MENSAGEM:
        raise ValueError("A mensagem excede o limite de um MiB.")

    # !I: inteiro sem sinal de quatro bytes em ordem de rede (big-endian).
    prefixo = struct.pack("!I", len(dados))
    conexao.sendall(prefixo + dados)


def receber_mensagem(conexao: socket.socket) -> dict:
    """Recebe o prefixo e depois exatamente os bytes de uma mensagem JSON."""
    prefixo = receber_bytes(conexao, TAMANHO_PREFIXO)
    tamanho = struct.unpack("!I", prefixo)[0]
    if not 0 < tamanho <= LIMITE_MENSAGEM:
        raise ValueError("Tamanho de mensagem inválido; permitido de 1 byte a um MiB.")

    dados = receber_bytes(conexao, tamanho)
    mensagem = json.loads(dados.decode("utf-8"))
    if not isinstance(mensagem, dict):
        raise ValueError("A mensagem deve ser um objeto JSON (dicionário).")
    return mensagem
