#!/usr/bin/env python3
"""
Concatena os .jsonl de ``data/exports`` num único ficheiro para treino LoRA.

A **ordem dos blocos** é fixada abaixo em ``EXPORT_BLOCKS`` (editável).
Dentro de cada pasta, todos os ``*.jsonl`` são incluídos, ordenados por caminho.

Ordem predefinida:
  1. LIVROS
  2. MENSAGENS_BIBLICAS
  3. BASE_DE_CONHECIMENTO
  4. REGISTROS
  5. SINTETICOS
  6. LEITURA_DE_CAMPO

Saída predefinida: ``data/final/dataset_final.jsonl``

Uso:
  python exportacao_dataset_final.py
  python exportacao_dataset_final.py --dry-run
  python exportacao_dataset_final.py --output data/final/outro.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
DEFAULT_EXPORTS = DIR / "data" / "exports"
DEFAULT_OUTPUT = DIR / "data" / "final" / "dataset_final.jsonl"

# (rótulo para relatório, subpasta relativa a data/exports)
EXPORT_BLOCKS: list[tuple[str, str]] = [
    ("LIVROS", "livros"),
    ("MENSAGENS_BIBLICAS", "mensagens_biblicas"),
    ("BASE_DE_CONHECIMENTO", "base_de_conhecimento"),
    ("REGISTROS", "registros"),
    ("SINTETICOS", "sinteticos"),
    ("LEITURA_DE_CAMPO", "leituras_de_campo"),
]


def jsonl_files_in_block(exports_root: Path, subdir: str) -> list[Path]:
    base = exports_root / subdir
    if not base.is_dir():
        return []
    return sorted(base.rglob("*.jsonl"))


def collect_plan(exports_root: Path) -> list[tuple[str, Path]]:
    plan: list[tuple[str, Path]] = []
    for label, sub in EXPORT_BLOCKS:
        for fp in jsonl_files_in_block(exports_root, sub):
            plan.append((label, fp))
    return plan


def main() -> None:
    ap = argparse.ArgumentParser(description="Dataset único LoRA a partir de data/exports")
    ap.add_argument(
        "--exports",
        type=Path,
        default=DEFAULT_EXPORTS,
        help="Pasta raiz dos exports (predef.: data/exports)",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Ficheiro JSONL de saída (predef.: data/final/dataset_final.jsonl)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista ficheiros e contagens, não grava",
    )
    args = ap.parse_args()

    exports_root = args.exports.resolve()
    if not exports_root.is_dir():
        print(f"Pasta não encontrada: {exports_root}", file=sys.stderr)
        sys.exit(1)

    plan = collect_plan(exports_root)
    if not plan:
        print(f"Nenhum .jsonl encontrado sob os blocos definidos em {exports_root}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print(f"Exports: {exports_root}\n")
        total_lines = 0
        by_label: dict[str, int] = {}
        for label, fp in plan:
            rel = fp.relative_to(exports_root)
            n = 0
            with fp.open(encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        n += 1
            total_lines += n
            by_label[label] = by_label.get(label, 0) + n
            print(f"  [{label}] {rel}  ({n} linhas)")
        print(f"\nTotal: {len(plan)} ficheiros, {total_lines} linhas")
        for label in [b[0] for b in EXPORT_BLOCKS]:
            if label in by_label:
                print(f"  {label}: {by_label[label]} linhas")
        return

    out_path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    by_label: dict[str, int] = {}
    with out_path.open("w", encoding="utf-8") as out:
        for label, fp in plan:
            with fp.open(encoding="utf-8") as inf:
                for line in inf:
                    raw = line.strip()
                    if not raw:
                        continue
                    json.loads(raw)
                    out.write(raw + "\n")
                    written += 1
                    by_label[label] = by_label.get(label, 0) + 1

    print(f"Escrito {written} linhas em {out_path}", file=sys.stderr)
    for label in [b[0] for b in EXPORT_BLOCKS]:
        if label in by_label:
            print(f"  {label}: {by_label[label]}", file=sys.stderr)


if __name__ == "__main__":
    main()
