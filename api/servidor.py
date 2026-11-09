"""
servidor.py - Backend do ThermoSense (Flask).

Uma thread lê a porta serial do Arduino continuamente (usando o limites.py) e
guarda a última leitura. A página web consulta essa leitura pela rota
/api/dados.

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
import random
import threading
import time
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

import limites 

# Pasta onde está o front end
PASTA_FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ARQUIVO_HTML = "index.html"

# Se passar esse tempo sem leitura nova, a página mostra "sem dados"
TEMPO_MAX_SEM_DADOS = 10  # segundos

# Só estes tipos de arquivo são servidos (não expõe o código Python nem o .ino)
EXTENSOES_PUBLICAS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp"}

app = Flask(__name__, static_folder=None)

_lock = threading.Lock()
_estado = {
    "temperatura": None,
    "umidade": None,
    "status": None,
    "alertas": [],
    "ultima_leitura": None,
    "erro": None,
}


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
# Coleta de dados
# ---------------------------------------------------------------------------
def registrar(leitura):
    with _lock:
        _estado.update(
            temperatura=leitura["temperatura"],
            umidade=leitura["umidade"],
            status=leitura["status"],
            alertas=leitura["alertas"],
            ultima_leitura=time.time(),
            erro=None,
        )


def ler_serial(porta):
    """Thread: mantém a serial aberta e tenta reconectar se algo falhar."""
    while True:
        try:
            for leitura in limites.monitorar(porta):
                registrar(leitura)
        except Exception as erro:
            with _lock:
                _estado["erro"] = str(erro)
            print(f"[serial] {erro} - nova tentativa em 3 s "
                  "(Monitor Serial aberto? Porta correta?)")
            time.sleep(3)


def simular():
    """Thread: gera leituras falsas para testar a página sem o Arduino."""
    passo = 0
    while True:
        temperatura = 24 + 8 * math.sin(passo / 20) + random.uniform(-0.3, 0.3)
        umidade = 45 + 12 * math.sin(passo / 15) + random.uniform(-0.5, 0.5)
        alertas = []
        if temperatura > LIMITES_ATUAIS["temperatura_max"]:
            alertas.append("PERIGO (TEMPERATURA ALTA)")
        if temperatura < LIMITES_ATUAIS["temperatura_min"]:
            alertas.append("PERIGO (TEMPERATURA BAIXA)")
        if umidade > LIMITES_ATUAIS["umidade_max"]:
            alertas.append("PERIGO (UMIDADE ALTA)")
        if umidade < LIMITES_ATUAIS["umidade_min"]:
            alertas.append("PERIGO (UMIDADE BAIXA)")
        registrar({
            "status": "OK",
            "temperatura": round(temperatura, 1),
            "umidade": round(umidade, 1),
            "alertas": alertas or ["Dentro dos limites (TUDO ESTÁ OK!)"],
        })
        passo += 1
        time.sleep(2)


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
@app.get("/api/dados")
def dados():
    with _lock:
        copia = dict(_estado)
    ultima = copia["ultima_leitura"]
    agora = time.time()
    copia["conectado"] = ultima is not None and (agora - ultima) <= TEMPO_MAX_SEM_DADOS
    copia["segundos_desde_leitura"] = None if ultima is None else round(agora - ultima, 1)
    copia["limites"] = LIMITES_ATUAIS
    return jsonify(copia)


@app.after_request
def liberar_cors(resposta):
    # Permite a página aberta pelo Live Server (outra porta) consultar a API.
    resposta.headers["Access-Control-Allow-Origin"] = "*"
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


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

    # debug/reloader desligados: o reloader abriria a porta serial duas vezes
    app.run(host=args.host, port=args.http_port, debug=False, threaded=True)
