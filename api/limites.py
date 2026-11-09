"""
limites.py - Lê os limites e o intervalo definidos no arquivo thermosense.ino.

Uso como módulo:
    from limites import ler_limites
    print(ler_limites())

Uso pelo terminal:
    python limites.py
    python limites.py "C:/Users/Marcelo/thermosense/thermosense.ino"
"""

import json
import re
import sys
from pathlib import Path

# Nome da variável no .ino -> nome da chave devolvida pelo Python
VARIAVEIS = {
    "maxTemperatura": "temperatura_max",
    "minTemperatura": "temperatura_min",
    "maxUmidade": "umidade_max",
    "minUmidade": "umidade_min",
    "intervalo": "intervalo_ms",
}


def encontrar_ino(nome="thermosense.ino"):
    """Procura o .ino na pasta do projeto (a pasta acima de api/)."""
    raiz = Path(__file__).resolve().parent.parent
    for candidato in raiz.rglob(nome):
        return candidato
    raise FileNotFoundError(
        f"Não encontrei '{nome}' dentro de {raiz}. "
        "Passe o caminho completo para ler_limites()."
    )


def ler_limites(caminho_ino=None):
    """Retorna um dicionário com os valores atuais definidos no .ino."""
    caminho = Path(caminho_ino) if caminho_ino else encontrar_ino()
    texto = caminho.read_text(encoding="utf-8", errors="ignore")

    resultado = {}
    for nome_ino, chave in VARIAVEIS.items():
        # Casa declarações como:  float maxUmidade = 50.0;
        # Linhas comentadas (// ...) não casam porque o padrão exige o tipo no início.
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


if __name__ == "__main__":
    caminho_arg = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(ler_limites(caminho_arg), indent=2, ensure_ascii=False))
