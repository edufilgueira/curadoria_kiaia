#!/usr/bin/env python3
"""
Percorre todas as subpastas a partir de --root e valida ficheiros *.jsonl:
cada linha não vazia tem de ser um único objeto JSON válido (padrão JSONL).

Útil antes de treino LoRA para evitar linhas truncadas ou JSON partido.

Uso:
  python validar_jsonl_recursivo.py
  python validar_jsonl_recursivo.py --root /caminho/para/data
  python validar_jsonl_recursivo.py --quiet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = DIR


def validar_ficheiro(caminho: Path) -> tuple[list[tuple[int, str]], int]:
    """
    Uma passagem pelo ficheiro.
    Devolve (lista de erros (linha, msg), número de linhas não vazias).
    lineno -1 = erro de abertura/leitura.
    """
    erros: list[tuple[int, str]] = []
    linhas_json = 0
    try:
        with caminho.open("r", encoding="utf-8") as f:
            for num_linha, linha in enumerate(f, start=1):
                if not linha.strip():
                    continue
                linhas_json += 1
                try:
                    json.loads(linha.strip())
                except json.JSONDecodeError as e:
                    erros.append((num_linha, str(e)))
    except UnicodeDecodeError as e:
        erros.append((-1, f"UTF-8 inválido: {e}"))
    except OSError as e:
        erros.append((-1, str(e)))
    return erros, linhas_json


def rel_path(caminho: Path, root: Path) -> Path:
    try:
        return caminho.relative_to(root)
    except ValueError:
        return caminho


def main() -> int:
    ap = argparse.ArgumentParser(description="Valida JSONL em todas as subpastas.")
    ap.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Diretório raiz para pesquisa (default: {DEFAULT_ROOT})",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Só imprime erros e resumo final.",
    )
    args = ap.parse_args()
    root: Path = args.root.resolve()

    if not root.is_dir():
        print(f"Erro: não é um diretório: {root}", file=sys.stderr)
        return 1

    jsonls = sorted(root.rglob("*.jsonl"))

    if not jsonls:
        print(f"Nenhum ficheiro .jsonl encontrado em {root}", flush=True)
        return 0

    if not args.quiet:
        print(
            f"A validar {len(jsonls)} ficheiro(s) sob {root}\n",
            flush=True,
        )

    total_linhas = 0
    total_erros = 0
    ficheiros_com_erro = 0

    for caminho in jsonls:
        erros, n_linhas = validar_ficheiro(caminho)
        total_linhas += n_linhas
        rel = rel_path(caminho, root)
        if erros:
            ficheiros_com_erro += 1
            total_erros += len(erros)
            for num, msg in erros:
                if num < 0:
                    print(f"{rel}: {msg}", file=sys.stderr)
                else:
                    print(f"{rel}:{num}: {msg}", file=sys.stderr)

    if total_erros:
        print(
            f"\nResumo: {len(jsonls)} ficheiro(s), {total_linhas} linha(s) JSON, "
            f"{total_erros} erro(s) em {ficheiros_com_erro} ficheiro(s).",
            file=sys.stderr,
        )
        return 1

    msg_final = (
        f"OK: {len(jsonls)} ficheiro(s), {total_linhas} linha(s) JSON válida(s), 0 erros."
    )
    if args.quiet:
        print(msg_final, flush=True)
    else:
        print(f"\n{msg_final}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
