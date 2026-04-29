#!/usr/bin/env python3
"""
Conta tokens (tiktoken, encoding cl100k_base — alinhado a exportacao_estatisticas_tokens.py).

1) Cola o texto na variável TEXT abaixo e executa:
     python3 contar_tokens.py

2) Ou passa o texto no terminal (sem editar o ficheiro):
     python3 contar_tokens.py "Olá mundo"
     python3 contar_tokens.py < ficheiro.txt
"""

from __future__ import annotations

import argparse
import sys

# --- Cola o teu texto aqui (string multilinha) ---
TEXT = """
"""

ENCODING_NAME = "cl100k_base"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Conta tokens de um texto (cl100k_base).",
    )
    ap.add_argument(
        "texto",
        nargs="*",
        help="Texto opcional; se omitido, usa a variável TEXT deste script ou stdin",
    )
    args = ap.parse_args()

    if args.texto:
        body = " ".join(args.texto)
    elif not sys.stdin.isatty():
        body = sys.stdin.read()
    else:
        body = TEXT.strip("\n")

    if not body.strip():
        print(
            "Nada para contar: define TEXT em contar_tokens.py, ou:\n"
            '  python3 contar_tokens.py "teu texto"\n'
            "  python3 contar_tokens.py < ficheiro.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import tiktoken

        enc = tiktoken.get_encoding(ENCODING_NAME)
    except ImportError:
        print("Instale: pip install tiktoken", file=sys.stderr)
        sys.exit(1)

    n = len(enc.encode(body))
    chars = len(body)
    print(f"Encoding:  {ENCODING_NAME}")
    print(f"Caracteres: {chars}")
    print(f"Tokens:     {n}")


if __name__ == "__main__":
    main()
