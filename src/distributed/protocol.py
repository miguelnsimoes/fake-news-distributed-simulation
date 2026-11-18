"""Mensagens JSON em UTF-8 com prefixo de tamanho de quatro bytes."""

import json
import socket
import struct


TAMANHO_PREFIXO = 4
LIMITE_MENSAGEM = 1024 * 1024  # Um MiB por mensagem, inclusive nos lotes da grade.
CELULAS_POR_LOTE = 64 * 1024


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

    dados = json.dumps(mensagem, ensure_ascii=False, allow_nan=False).encode("utf-8")
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


def receber_tipo(conexao: socket.socket, tipo: str) -> dict:
    """Verifica a etapa do protocolo e propaga erros informados pelo outro lado."""
    mensagem = receber_mensagem(conexao)
    if mensagem.get("tipo") == "erro":
        raise RuntimeError(f"Erro remoto: {mensagem.get('mensagem', 'não informado')}")
    if mensagem.get("tipo") != tipo:
        raise ValueError(f"Esperada mensagem {tipo!r}, recebida {mensagem.get('tipo')!r}.")
    return mensagem


def codificar_linha(linha: list) -> str:
    """Um caractere por célula, em vez de uma lista JSON com vírgulas e espaços."""
    if any(type(estado) is not int or estado not in (0, 1, 2) for estado in linha):
        raise ValueError("Os estados devem ser os inteiros 0, 1 ou 2.")
    return "".join(map(str, linha))


def decodificar_linha(texto: str, colunas: int) -> list:
    if not isinstance(texto, str) or len(texto) != colunas or set(texto) - set("012"):
        raise ValueError("Linha recebida com tamanho ou estados inválidos.")
    return [ord(estado) - ord("0") for estado in texto]


def enviar_grade(conexao: socket.socket, grade: list, colunas: int) -> None:
    """Transfere uma grade em lotes; o limite se aplica a cada mensagem JSON."""
    if colunas < 1 or any(len(linha) != colunas for linha in grade):
        raise ValueError("Dimensões inválidas para a grade.")
    enviar_mensagem(conexao, {"tipo": "grade", "linhas": len(grade), "colunas": colunas})
    pendente = ""
    for linha in grade:
        pendente += codificar_linha(linha)
        while len(pendente) >= CELULAS_POR_LOTE:
            enviar_mensagem(conexao, {"tipo": "dados_grade", "dados": pendente[:CELULAS_POR_LOTE]})
            pendente = pendente[CELULAS_POR_LOTE:]
    if pendente:
        enviar_mensagem(conexao, {"tipo": "dados_grade", "dados": pendente})


def receber_grade(conexao: socket.socket, linhas: int, colunas: int) -> list:
    """Reconstrói a grade e rejeita dimensões, estados e lotes inconsistentes."""
    cabecalho = receber_tipo(conexao, "grade")
    if cabecalho.get("linhas") != linhas or cabecalho.get("colunas") != colunas:
        raise ValueError("Dimensões da grade recebida diferentes das esperadas.")
    partes = []
    recebidas = 0
    total = linhas * colunas
    while recebidas < total:
        dados = receber_tipo(conexao, "dados_grade").get("dados")
        if (not isinstance(dados, str) or not dados or len(dados) > CELULAS_POR_LOTE
                or set(dados) - set("012") or recebidas + len(dados) > total):
            raise ValueError("Lote de células inválido.")
        partes.append(dados)
        recebidas += len(dados)
    texto = "".join(partes)
    return [decodificar_linha(texto[i:i + colunas], colunas)
            for i in range(0, total, colunas)]
