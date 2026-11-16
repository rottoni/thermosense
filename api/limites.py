import json
import re
import sys
import time
from pathlib import Path
 
NOME_INO = "arduino.ino"
 
# Nome da variável no .ino -> nome da chave devolvida pelo Python
VARIAVEIS = {
    "maxTemperatura": "temperatura_max",
    "minTemperatura": "temperatura_min",
    "maxUmidade": "umidade_max",
    "minUmidade": "umidade_min",
    "intervalo": "intervalo_ms",
}
 
 
# ---------------------------------------------------------------------------
# 1) Limites gravados no código (.ino)
# ---------------------------------------------------------------------------
def encontrar_ino(nome=NOME_INO):
    """Procura o .ino na pasta do projeto (a pasta acima de api/)."""
    raiz = Path(__file__).resolve().parent.parent
    for candidato in raiz.rglob(nome):
        return candidato
    raise FileNotFoundError(
        f"Não encontrei '{nome}' dentro de {raiz}. "
        "Passe o caminho completo para ler_limites()."
    )
 
 
def ler_limites(caminho_ino=None):
    """Retorna um dicionário com os valores padrão definidos no .ino."""
    caminho = Path(caminho_ino) if caminho_ino else encontrar_ino()
    texto = caminho.read_text(encoding="utf-8", errors="ignore")
 
    resultado = {}
    for nome_ino, chave in VARIAVEIS.items():
        padrao = (
            rf"^\s*(?:const\s+)?(?:unsigned\s+)?(?:float|int|long)\s+"
            rf"{nome_ino}\s*=\s*(-?\d+(?:\.\d+)?)\s*;"
        )
        achado = re.search(padrao, texto, re.MULTILINE)
        if achado is None:
            raise ValueError(f"Variável '{nome_ino}' não encontrada em {caminho}")
        valor = float(achado.group(1))
        resultado[chave] = int(valor) if chave == "intervalo_ms" else valor
 
    return resultado
 
 
# ---------------------------------------------------------------------------
# 2) Leitura ao vivo (temperatura e umidade atuais) pela serial
# ---------------------------------------------------------------------------
def interpretar_linha(linha):
    """
    Converte uma linha enviada pelo Arduino em um dicionário.
    Formato esperado:
        OK,   2012,   45.3,   23.1,   Dentro dos limites (TUDO ESTÁ OK!)
        status, tempo, umidade, temperatura, alerta(s)...
    Devolve None para linhas que não são leituras (cabeçalho, respostas a comandos).
    """
    partes = [p.strip() for p in linha.split(",")]
    if len(partes) < 5:
        return None
    try:
        return {
            "status": partes[0],
            "tempo_leitura_ms": int(partes[1]),
            "umidade": float(partes[2]),
            "temperatura": float(partes[3]),
            "alertas": [p for p in partes[4:] if p],
        }
    except ValueError:
        return None  # cabeçalho ou texto qualquer
 
 
def monitorar(porta="COM3", baudrate=9600):
    """Gerador: abre a serial e devolve um dicionário a cada leitura do Arduino."""
    import serial  # importado aqui para ler_limites() funcionar sem pyserial
 
    with serial.Serial(port=porta, baudrate=baudrate, timeout=1) as arduino:
        time.sleep(2)  # o Arduino reinicia ao abrir a porta
        while True:
            bruto = arduino.readline().decode("utf-8", errors="ignore").strip()
            if not bruto:
                continue
            leitura = interpretar_linha(bruto)
            if leitura:
                yield leitura
 
 
def formatar(leitura):
    alerta = " | ".join(leitura["alertas"]) if leitura["alertas"] else "-"
    return (
        f"Temperatura: {leitura['temperatura']:5.1f} °C   "
        f"Umidade: {leitura['umidade']:5.1f} %   "
        f"[{leitura['status']}]   {alerta}"
    )
 
 
if __name__ == "__main__":
    args = sys.argv[1:]
    so_limites = "--so-limites" in args
    args = [a for a in args if not a.startswith("--")]
    porta = args[0] if args else "COM3"
 
    print("Limites padrão (arduino.ino):")
    print(json.dumps(ler_limites(), indent=2, ensure_ascii=False))
 
    if not so_limites:
        print(f"\nLendo {porta}... (Ctrl+C para sair)\n")
        try:
            for leitura in monitorar(porta):
                # \r volta ao início da linha: o valor é atualizado no lugar
                print("\r" + formatar(leitura).ljust(110), end="", flush=True)
        except KeyboardInterrupt:
            print("\n\nEncerrado.")
        except Exception as erro:
            print(f"\nErro ao acessar {porta}: {erro}")
            print("Feche o Monitor Serial da IDE e confira a porta COM.")