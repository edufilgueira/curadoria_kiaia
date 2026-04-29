#!/usr/bin/env python3
"""
Procura em todos os ficheiros *.jsonl sob data/exports/ o padrão de duas
citações em bloco (linhas que começam com '>) separadas por uma linha em
branco — ou seja, dois newline seguidos (\\n\\n) entre um '>' e o seguinte.

Exemplo (renderizado):
  > **"Melissa, meu amor…**

  > Você não precisa…

No texto isso é: linha com `> ...`, depois `\\n\\n`, depois outra linha com `>`.

Não analisa: sinteticos/dataset_instrucao_citacao.jsonl (relativamente a --root).

Uso:
  python procurar_citacoes_com_linha_em_branco.py
  python procurar_citacoes_com_linha_em_branco.py --root /caminho/exports
  python procurar_citacoes_com_linha_em_branco.py --contexto 120
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = DIR / "data" / "exports"

# Caminhos relativos a --root: não analisar (ex.: instrução sintética sobre citação).
_FICHEIROS_EXCLUIDOS = frozenset(
    {Path("sinteticos") / "dataset_instrucao_citacao.jsonl"}
)


def _ficheiro_excluido(caminho: Path, root: Path) -> bool:
    try:
        rel = caminho.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return rel in _FICHEIROS_EXCLUIDOS

# Duas linhas "blockquote" (markdown) com linha vazia entre = \\n\\n no texto.
# Aceita fim de linha CRLF; ^ corresponde ao início de cada linha com MULTILINE.
# A segunda citação inclui o resto da linha (até \\n) para o excerto ser legível.
_PADRAO = re.compile(r"(?m)^>[^\n]*\r?\n\r?\n^>[^\n]*")


def _format_json_path(path: tuple[Any, ...]) -> str:
    s = ""
    for x in path:
        if isinstance(x, int):
            s += f"[{x}]"
        else:
            s = f"{s}.{x}" if s else str(x)
    return s


def _iter_strings(obj: Any, path: tuple[Any, ...] = ()) -> Iterator[tuple[str, str]]:
    if isinstance(obj, str):
        yield _format_json_path(path), obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_strings(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_strings(v, path + (i,))


def _excerto(s: str, inicio: int, fim: int, max_total: int) -> str:
    if fim - inicio <= max_total:
        return s[inicio:fim]
    meio = max_total // 2 - 2
    return s[inicio : inicio + meio] + " … " + s[fim - meio : fim]


def procurar_no_texto(
    texto: str, max_contexto: int
) -> list[tuple[int, int, str]]:
    """
    Devolve lista de (start, end, excerto) para cada ocorrência do padrão.
    """
    out: list[tuple[int, int, str]] = []
    for m in _PADRAO.finditer(texto):
        a, b = m.span()
        out.append(
            (a, b, _excerto(texto, a, b, max_contexto))
        )
    return out


def percorrer_ficheiro(
    caminho: Path,
    max_contexto: int,
    erros_json: list[tuple[int, str]],
    quiet: bool = False,
) -> int:
    """Devolve o número de ocorrências."""
    n = 0
    with caminho.open("r", encoding="utf-8", errors="replace") as f:
        for num_linha, linha in enumerate(f, start=1):
            if not linha.strip():
                continue
            try:
                obj = json.loads(linha.strip())
            except json.JSONDecodeError as e:
                erros_json.append((num_linha, str(e)))
                continue
            for json_path, s in _iter_strings(obj):
                ocorrencias = procurar_no_texto(s, max_contexto)
                for start, _end, excerto in ocorrencias:
                    n += 1
                    if not quiet:
                        print(f"{caminho}")
                        print(f"  linha JSONL: {num_linha}  |  campo: {json_path}")
                        print(f"  posição no texto: {start}")
                        print(f"  excerto: {excerto!r}")
                        print()
    return n


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Localiza citações markdown ('>') com \\n\\n entre duas linhas consecutivas."
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Pasta com exports (padrão: {DEFAULT_ROOT})",
    )
    ap.add_argument(
        "--contexto",
        type=int,
        default=200,
        metavar="N",
        help="Tamanho máximo aproximado do excerto mostrado (padrão: 200).",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Só imprime o resumo final.",
    )
    args = ap.parse_args()
    root: Path = args.root.resolve()
    if not root.is_dir():
        print(f"Erro: pasta inexistente: {root}", file=sys.stderr)
        return 1

    todos_jsonl = sorted(root.rglob("*.jsonl"))
    if not todos_jsonl:
        print(f"Nenhum ficheiro .jsonl em {root}", file=sys.stderr)
        return 1
    ficheiros = [p for p in todos_jsonl if not _ficheiro_excluido(p, root)]
    excluidos = len(todos_jsonl) - len(ficheiros)
    if not ficheiros:
        print(
            f"Nenhum ficheiro a analisar (todos excluídos ou pasta só com excluídos).",
            file=sys.stderr,
        )
        return 1

    total = 0
    todos_erros: list[tuple[Path, int, str]] = []
    for fpath in ficheiros:
        erros_json: list[tuple[int, str]] = []
        n_file = percorrer_ficheiro(
            fpath,
            max_contexto=args.contexto,
            erros_json=erros_json,
            quiet=args.quiet,
        )
        total += n_file
        for ln, msg in erros_json:
            todos_erros.append((fpath, ln, msg))

    if not args.quiet and todos_erros:
        print("--- Aviso: JSON inválido em linha(s) ---", file=sys.stderr)
        for fp, ln, msg in todos_erros:
            print(f"  {fp}:{ln} — {msg}", file=sys.stderr)

    msg_resumo = (
        f"Resumo: {total} ocorrência(s) do padrão "
        f"'linha com >' + linha vazia + 'linha com >' em {len(ficheiros)} ficheiro(s) sob {root}"
    )
    if excluidos:
        msg_resumo += f" ({excluidos} ficheiro(s) excluído(s) desta procura)"
    print(msg_resumo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
