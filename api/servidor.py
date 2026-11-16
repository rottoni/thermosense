"""
servidor.py - Backend do ThermoSense (Flask).

Instalação:
    pip install flask pyserial

Uso (a partir da pasta api/):
    python servidor.py                 # lê o Arduino na COM3
    python servidor.py COM4            # outra porta
    python servidor.py --simular       # dados falsos, para testar sem Arduino

Depois abra  http://localhost:5000

IMPORTANTE: feche o Monitor Serial da IDE do Arduino (e qualquer outro programa
que use a COM), pois a porta só aceita um programa por vez.
"""

import argparse
import math
import queue
import random
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

import limites  # limites.py, na mesma pasta

# Pasta onde estão o index.html, style.css, script.js, imagens e sons
PASTA_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ARQUIVO_HTML = "index.html"

# Imagens e sons (ex.: assets/alerta.png, assets/alerta.wav). O servidor procura em
# thermosense/assets/ e também em thermosense/frontend/assets/, nesta ordem.
PASTA_ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Tempo mínimo (s) sem leituras para considerar o Arduino sem comunicação.
# Com taxas de atualização longas, o limite cresce (3x o intervalo).
TEMPO_MAX_SEM_DADOS = 10

# Histórico dos gráficos, guardado na memória do servidor (zera só ao reiniciar o servidor).
# 20000 leituras = cerca de 11 h com leitura a cada 2 s; passando disso, as mais antigas saem.
MAX_PONTOS = 20000

# Só estes tipos de arquivo são servidos (não expõe o código Python nem o .ino)
EXTENSOES_PUBLICAS = {
    ".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp",
    ".wav", ".mp3",
}

# Páginas abertas em localhost / 127.0.0.1 (qualquer porta, ex.: Live Server)
# podem usar a API. Outros sites não.
ORIGEM_LOCAL = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")

# Campos do formulário -> (chave interna, nome amigável, mínimo, máximo, inteiro?)
CAMPOS_FORMULARIO = {
    "maxTemp":   ("temperatura_max", "Temperatura máxima", -40, 80, False),
    "minTemp":   ("temperatura_min", "Temperatura mínima", -40, 80, False),
    "maxUmid":   ("umidade_max", "Umidade máxima", 0, 100, False),
    "minUmid":   ("umidade_min", "Umidade mínima", 0, 100, False),
    "intervalo": ("intervalo_ms", "Taxa de atualização", 1000, 900000, True),
}
NUMERO = re.compile(r"^-?\d+(?:\.\d+)?$")

CHAVES_COMANDO = {
    "TMAX": "temperatura_max",
    "TMIN": "temperatura_min",
    "UMAX": "umidade_max",
    "UMIN": "umidade_min",
}

# Respostas que o Arduino imprime ao aceitar um comando
CONFIRMA_LIMITE = re.compile(
    r"Novo limite (M\S*XIMO|M\S*NIMO) de (temperatura|umidade) definido para:\s*(-?\d+(?:\.\d+)?)"
)
CONFIRMA_INTERVALO = re.compile(r"Novo intervalo de leitura definido para:\s*(\d+)")

app = Flask(__name__, static_folder=None)

_lock = threading.Lock()  # protege _estado e LIMITES_ATUAIS
_estado = {
    "temperatura": None,
    "umidade": None,
    "status": None,
    "alertas": [],
    "ultima_leitura": None,
    "erro": None,
    "reiniciando": False,
    "porta_ok": False,
    "porta_aberta_desde": None,
}
_fila = queue.Queue()        # pedidos de atualização de limites
_aplicando = threading.Lock()  # só uma atualização por vez

# Identifica esta execução do servidor: muda sempre que ele é reiniciado, e a página
# usa isso para saber que deve descartar o gráfico antigo.
SESSAO = uuid.uuid4().hex
_historico = deque(maxlen=MAX_PONTOS)  # cada ponto: [id, t_ms, temperatura, umidade, intervalo_ms]
_proximo_id = 1


def carregar_limites():
    """Limites padrão gravados no arduino.ino (o Arduino reinicia ao abrir a serial)."""
    try:
        return limites.ler_limites()
    except Exception as erro:
        print(f"[aviso] Não consegui ler os limites do arduino.ino: {erro}")
        return {
            "temperatura_max": 30.0,
            "temperatura_min": 10.0,
            "umidade_max": 50.0,
            "umidade_min": 5.0,
            "intervalo_ms": 2000,
        }


LIMITES_ATUAIS = carregar_limites()


# ---------------------------------------------------------------------------
# Estado compartilhado
# ---------------------------------------------------------------------------
def registrar(leitura):
    global _proximo_id
    agora = time.time()
    with _lock:
        _estado.update(
            temperatura=leitura["temperatura"],
            umidade=leitura["umidade"],
            status=leitura["status"],
            alertas=leitura["alertas"],
            ultima_leitura=agora,
            erro=None,
        )
        # Só leituras válidas entram no gráfico (com erro o sensor devolve -999)
        if leitura["status"] == "OK":
            _historico.append([
                _proximo_id,
                int(agora * 1000),
                leitura["temperatura"],
                leitura["umidade"],
                LIMITES_ATUAIS["intervalo_ms"],
            ])
            _proximo_id += 1


def marcar_porta(aberta, erro=None):
    with _lock:
        _estado["porta_ok"] = aberta
        _estado["erro"] = erro
        if aberta:
            _estado["porta_aberta_desde"] = time.time()


def marcar_reinicio():
    with _lock:
        _estado.update(
            reiniciando=True,
            temperatura=None,
            umidade=None,
            status=None,
            alertas=[],
            ultima_leitura=None,
        )


def finalizar(pedido, ok, erro=None):
    with _lock:
        _estado["reiniciando"] = False
    pedido["resultado"] = {"ok": ok, "erro": erro}
    pedido["pronto"].set()


def proximo_pedido():
    while True:
        try:
            pedido = _fila.get_nowait()
        except queue.Empty:
            return None
        if not pedido.get("cancelado"):
            return pedido


# ---------------------------------------------------------------------------
# Serial (Arduino real)
# ---------------------------------------------------------------------------
def processar_linha(linha):
    """Trata uma linha vinda do Arduino. Devolve 'leitura', 'confirmacao' ou None."""
    leitura = limites.interpretar_linha(linha)
    if leitura:
        registrar(leitura)
        return "leitura"

    achado = CONFIRMA_LIMITE.search(linha)
    if achado:
        lado = "max" if "XIMO" in achado.group(1) else "min"
        with _lock:
            LIMITES_ATUAIS[f"{achado.group(2)}_{lado}"] = float(achado.group(3))
        return "confirmacao"

    achado = CONFIRMA_INTERVALO.search(linha)
    if achado:
        with _lock:
            LIMITES_ATUAIS["intervalo_ms"] = int(achado.group(1))
        return "confirmacao"

    return None


def enviar_comando(arduino, comando, tentativas=2):
    """Envia um comando e espera o Arduino confirmar. Devolve True se confirmou."""
    for _ in range(tentativas):
        arduino.write((comando + "\n").encode("utf-8"))
        prazo = time.time() + 3
        while time.time() < prazo:
            bruto = arduino.readline().decode("utf-8", errors="ignore").strip()
            if bruto and processar_linha(bruto) == "confirmacao":
                return True
    return False


def executar_pedido(arduino, pedido):
    falhas = [c.split()[0] for c in pedido["comandos"] if not enviar_comando(arduino, c)]
    if falhas:
        finalizar(
            pedido, False,
            "O Arduino não confirmou: " + ", ".join(falhas)
            + ". Confira se o sketch tem o comando e se está gravado.",
        )
    else:
        finalizar(pedido, True)


def ler_serial(porta):
    """Thread: dona da porta. Lê leituras, reinicia o Arduino e aplica novos limites."""
    import serial

    pedido = None
    while True:
        try:
            with serial.Serial(port=porta, baudrate=9600, timeout=1) as arduino:
                time.sleep(2.5)  # abrir a porta reinicia o Arduino; espera ele voltar
                arduino.reset_input_buffer()
                marcar_porta(True)

                if pedido is not None:
                    executar_pedido(arduino, pedido)
                    pedido = None

                while True:
                    pedido = proximo_pedido()
                    if pedido is not None:
                        marcar_reinicio()
                        break  # sai do "with": fecha a porta; ao reabrir, o Arduino reinicia
                    bruto = arduino.readline().decode("utf-8", errors="ignore").strip()
                    if bruto:
                        processar_linha(bruto)
            time.sleep(0.5)  # pausa entre fechar e reabrir, para o reset acontecer
        except Exception as erro:
            marcar_porta(False, str(erro))
            if pedido is not None:
                finalizar(pedido, False, f"Falha na porta serial: {erro}")
                pedido = None
            print(f"[serial] {erro} - nova tentativa em 3 s "
                  "(Monitor Serial aberto? Porta correta?)")
            time.sleep(3)


# ---------------------------------------------------------------------------
# Simulador (sem Arduino)
# ---------------------------------------------------------------------------
def aplicar_comando_simulado(comando):
    nome, valor = comando.split()
    with _lock:
        if nome == "INTERVALO":
            LIMITES_ATUAIS["intervalo_ms"] = int(valor)
        else:
            LIMITES_ATUAIS[CHAVES_COMANDO[nome]] = float(valor)


def simular():
    """Thread: gera leituras falsas e aceita novos limites, como o Arduino faria."""
    marcar_porta(True)
    passo = 0
    ultimo = 0.0
    while True:
        pedido = proximo_pedido()
        if pedido is not None:
            marcar_reinicio()
            time.sleep(2)  # "reinício"
            for comando in pedido["comandos"]:
                aplicar_comando_simulado(comando)
            marcar_porta(True)
            ultimo = 0.0
            finalizar(pedido, True)

        with _lock:
            lim = dict(LIMITES_ATUAIS)
        if time.time() - ultimo >= lim["intervalo_ms"] / 1000:
            temperatura = 24 + 8 * math.sin(passo / 20) + random.uniform(-0.3, 0.3)
            umidade = 45 + 12 * math.sin(passo / 15) + random.uniform(-0.5, 0.5)
            alertas = []
            if temperatura > lim["temperatura_max"]:
                alertas.append("PERIGO (TEMPERATURA ALTA)")
            if temperatura < lim["temperatura_min"]:
                alertas.append("PERIGO (TEMPERATURA BAIXA)")
            if umidade > lim["umidade_max"]:
                alertas.append("PERIGO (UMIDADE ALTA)")
            if umidade < lim["umidade_min"]:
                alertas.append("PERIGO (UMIDADE BAIXA)")
            registrar({
                "status": "OK",
                "temperatura": round(temperatura, 1),
                "umidade": round(umidade, 1),
                "alertas": alertas or ["Dentro dos limites (TUDO ESTÁ OK!)"],
            })
            passo += 1
            ultimo = time.time()
        time.sleep(0.2)


# ---------------------------------------------------------------------------
# Validação do formulário
# ---------------------------------------------------------------------------
def validar(corpo):
    """Devolve (lista_de_comandos, lista_de_erros). Campos vazios mantêm o valor atual."""
    if not isinstance(corpo, dict):
        return None, ["Requisição inválida."]

    novos, erros = {}, []
    for campo, (chave, nome, minimo, maximo, inteiro) in CAMPOS_FORMULARIO.items():
        bruto = str(corpo.get(campo) or "").strip().replace(",", ".")
        if not bruto:
            continue
        if len(bruto) > 20 or not NUMERO.match(bruto):
            erros.append(f"{nome}: digite apenas um número.")
            continue
        valor = float(bruto)
        if not (minimo <= valor <= maximo):
            erros.append(f"{nome}: deve estar entre {minimo} e {maximo}.")
            continue
        if inteiro and valor != int(valor):
            erros.append(f"{nome}: deve ser um número inteiro (em ms).")
            continue
        novos[chave] = int(valor) if inteiro else valor

    if not erros and not novos:
        erros.append("Preencha pelo menos um campo.")
    if erros:
        return None, erros

    # Valida o conjunto final (campos novos + valores atuais dos que ficaram vazios)
    with _lock:
        final = dict(LIMITES_ATUAIS)
    final.update(novos)
    if final["temperatura_max"] < final["temperatura_min"]:
        erros.append("A temperatura máxima deve ser maior ou igual à mínima "
                     f"({final['temperatura_max']:g} < {final['temperatura_min']:g}).")
    if final["umidade_max"] < final["umidade_min"]:
        erros.append("A umidade máxima deve ser maior ou igual à mínima "
                     f"({final['umidade_max']:g} < {final['umidade_min']:g}).")
    if erros:
        return None, erros

    comandos = [
        f"TMAX {final['temperatura_max']:.2f}",
        f"TMIN {final['temperatura_min']:.2f}",
        f"UMAX {final['umidade_max']:.2f}",
        f"UMIN {final['umidade_min']:.2f}",
        f"INTERVALO {int(final['intervalo_ms'])}",
    ]
    return comandos, []


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
def origem_permitida(origem):
    return bool(ORIGEM_LOCAL.match(origem)) or origem == request.host_url.rstrip("/")


@app.after_request
def cabecalhos(resposta):
    origem = request.headers.get("Origin")
    if origem and origem_permitida(origem):
        resposta.headers["Access-Control-Allow-Origin"] = origem
        resposta.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resposta.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resposta.headers["Vary"] = "Origin"
    if request.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-store"
    else:
        # Arquivos do site (inclusive o favicon) podem ser guardados pelo navegador, mas ele
        # confere com o servidor antes de usar. Com "no-store" o Chrome pode não guardar o
        # ícone da aba.
        resposta.headers["Cache-Control"] = "no-cache"
    return resposta


@app.get("/api/dados")
def dados():
    with _lock:
        copia = dict(_estado)
        lim = dict(LIMITES_ATUAIS)
    agora = time.time()

    # Referência do silêncio: última leitura ou, se ainda não houve, a abertura da porta
    referencia = copia["ultima_leitura"] or copia["porta_aberta_desde"]
    silencio_max = max(TEMPO_MAX_SEM_DADOS, 3 * lim["intervalo_ms"] / 1000)
    copia["conectado"] = bool(
        copia["porta_ok"] and referencia and (agora - referencia) <= silencio_max
    )
    ultima = copia["ultima_leitura"]
    copia["segundos_desde_leitura"] = None if ultima is None else round(agora - ultima, 1)
    copia["limites"] = lim
    for interno in ("porta_ok", "porta_aberta_desde"):
        copia.pop(interno)
    return jsonify(copia)


@app.get("/api/historico")
def historico():
    """Pontos do gráfico. A página pede só os novos (?desde=<último id recebido>)."""
    desde = request.args.get("desde", 0, type=int)
    if request.args.get("sessao", "") != SESSAO:
        desde = 0  # servidor reiniciado (ou primeira visita): manda tudo
    with _lock:
        pontos = [p for p in _historico if p[0] > desde] if desde > 0 else list(_historico)
        ultimo = _proximo_id - 1
        lim = dict(LIMITES_ATUAIS)
    return jsonify(sessao=SESSAO, ultimo_id=ultimo, max=MAX_PONTOS, pontos=pontos, limites=lim)


@app.post("/api/limites")
def definir_limites():
    origem = request.headers.get("Origin")
    if origem and not origem_permitida(origem):
        return jsonify(ok=False, erros=["Origem não permitida."]), 403

    comandos, erros = validar(request.get_json(silent=True))
    if erros:
        return jsonify(ok=False, erros=erros), 400

    with _lock:
        porta_ok = _estado["porta_ok"]
    if not porta_ok:
        return jsonify(ok=False, erros=["O Arduino não está conectado ao servidor."]), 503

    if not _aplicando.acquire(blocking=False):
        return jsonify(ok=False, erros=["Já há uma atualização em andamento. Aguarde."]), 409
    try:
        pedido = {"comandos": comandos, "pronto": threading.Event(), "resultado": None}
        _fila.put(pedido)
        if not pedido["pronto"].wait(timeout=45):
            pedido["cancelado"] = True
            return jsonify(ok=False, erros=["Tempo esgotado ao aplicar as alterações."]), 504
        resultado = pedido["resultado"]
    finally:
        _aplicando.release()

    if not resultado["ok"]:
        return jsonify(ok=False, erros=[resultado["erro"]]), 502
    with _lock:
        aplicados = dict(LIMITES_ATUAIS)
    return jsonify(ok=True, limites=aplicados)


@app.get("/favicon.ico")
def favicon():
    # Alguns navegadores pedem /favicon.ico por conta própria; entrega o favicon.png
    for pasta in (PASTA_ASSETS, PASTA_FRONTEND / "assets", PASTA_FRONTEND):
        if (pasta / "favicon.png").is_file():
            return send_from_directory(pasta, "favicon.png", mimetype="image/png")
    abort(404)


@app.get("/assets/<path:nome>")
def asset(nome):
    pastas = (PASTA_ASSETS, PASTA_FRONTEND / "assets")
    if Path(nome).suffix.lower() in EXTENSOES_PUBLICAS:
        for pasta in pastas:
            if (pasta / nome).is_file():
                # send_from_directory recusa caminhos que tentam sair da pasta (../)
                return send_from_directory(pasta, nome)
    # Não achou: mostra no terminal onde procurou e o que existe lá (ajuda a achar erro de nome)
    print(f"[assets] 404 para '{nome}'. Procurei em:")
    for pasta in pastas:
        conteudo = sorted(p.name for p in pasta.iterdir()) if pasta.is_dir() else "(a pasta não existe)"
        print(f"         {pasta} -> {conteudo}")
    abort(404)


@app.get("/")
def index():
    return send_from_directory(PASTA_FRONTEND, ARQUIVO_HTML)


@app.get("/<path:nome>")
def arquivo(nome):
    if nome.startswith("api/") or Path(nome).suffix.lower() not in EXTENSOES_PUBLICAS:
        abort(404)
    return send_from_directory(PASTA_FRONTEND, nome)


# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backend do ThermoSense")
    parser.add_argument("porta", nargs="?", default="COM3", help="porta serial (padrão: COM3)")
    parser.add_argument("--simular", action="store_true", help="usa dados falsos, sem Arduino")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=5000)
    args = parser.parse_args()

    alvo = simular if args.simular else (lambda: ler_serial(args.porta))
    threading.Thread(target=alvo, daemon=True).start()

    modo = "SIMULADO" if args.simular else args.porta
    print(f"ThermoSense rodando em http://localhost:{args.http_port}  (fonte: {modo})")
    for rotulo, pasta in (("frontend", PASTA_FRONTEND), ("assets  ", PASTA_ASSETS)):
        situacao = "ok" if pasta.is_dir() else "NÃO ENCONTRADA"
        print(f"  {rotulo}: {pasta}  [{situacao}]")

    # debug/reloader desligados: o reloader abriria a porta serial duas vezes
    app.run(host=args.host, port=args.http_port, debug=False, threaded=True)