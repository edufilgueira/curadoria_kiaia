#!/usr/bin/env python3
"""
Normaliza dataset_abertura de conversas.jsonl: campo `dataset`, ordenação,
deduplicação exata. Uso:
  python organizar_dataset_abertura_conversas.py
  python organizar_dataset_abertura_conversas.py --input ... --output ...
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = DIR / "data/select/dataset_abertura de conversas.jsonl"
DEFAULT_OUTPUT = DIR / "data/exports/sinteticos/dataset_abertura de conversas.normalizado.jsonl"

# Regras por prefixo mais longo primeiro (conversation_id).
DATASET_RULES: list[tuple[str, str]] = [
    ("transicao_oraculo", "ORACULO"),
    ("transicao_kiaia", "ORACULO"),
    ("transicao_pai", "PAI"),
    ("transicao_deus", "DEUS"),
    ("transicao_jesus", "JESUS"),
    ("transicao_espirito", "ESPIRITO"),
    ("transicao_universo", "UNIVERSO"),
    ("transicao_", "TRANSICAO"),
    ("abertura_oraculo", "ORACULO"),
    ("abertura_kiaia", "ORACULO"),
    ("abertura_pai", "PAI"),
    ("abertura_deus", "DEUS"),
    ("abertura_jesus", "JESUS"),
    ("abertura_espirito", "ESPIRITO"),
    ("abertura_universo", "UNIVERSO"),
    ("abertura_generica", "GENERICA"),
    ("abertura_", "ABERTURA"),
    ("entrada_", "ENTRADA"),
]

DATASET_ORDER = [
    "ABERTURA",
    "TRANSICAO",
    "ENTRADA",
    "PAI",
    "DEUS",
    "JESUS",
    "ESPIRITO",
    "UNIVERSO",
    "ORACULO",
    "GENERICA",
]


def infer_dataset(conversation_id: str) -> str:
    cid = (conversation_id or "").strip().lower()
    for prefix, name in DATASET_RULES:
        if cid.startswith(prefix):
            return name
    # Novo padrão: primeiro token antes de _
    m = re.match(r"^([a-z]+)_", cid)
    if m:
        return m.group(1).upper()
    return "OUTROS"


def numeric_tail(s: str) -> tuple[int, ...]:
    """Extrai todos os grupos numéricos para ordenação estável."""
    parts = re.findall(r"\d+", s or "")
    return tuple(int(p) for p in parts) if parts else (0,)


def sort_key_row(obj: dict) -> tuple:
    cid = obj.get("conversation_id") or ""
    sid = obj.get("segment_id") or ""
    ds = obj.get("dataset") or ""
    try:
        ord_i = DATASET_ORDER.index(ds)
    except ValueError:
        ord_i = len(DATASET_ORDER) + hash(ds) % 1000
    return (ord_i, numeric_tail(cid), numeric_tail(sid), cid, sid)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dedupe_exact(rows: list[dict]) -> list[dict]:
    """Remove linhas com o mesmo conteúdo canónico (incl. conversation_id + segment_id + messages)."""
    seen: set[str] = set()
    out: list[dict] = []
    for obj in rows:
        key = json.dumps(obj, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(obj)
    return out


def normalize_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for obj in rows:
        cid = obj.get("conversation_id", "")
        ds = infer_dataset(str(cid))
        new_obj = {"dataset": ds}
        for k, v in obj.items():
            new_obj[k] = v
        out.append(new_obj)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    rows = load_jsonl(args.input)
    rows = dedupe_exact(rows)
    rows = normalize_rows(rows)
    rows.sort(key=sort_key_row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for obj in rows:
            f.write(
                json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    by_ds: dict[str, int] = {}
    for obj in rows:
        d = obj.get("dataset", "?")
        by_ds[d] = by_ds.get(d, 0) + 1
    print(f"Escritos {len(rows)} registos em {args.output}")
    for k in sorted(by_ds.keys(), key=lambda x: (DATASET_ORDER.index(x) if x in DATASET_ORDER else 99, x)):
        print(f"  {k}: {by_ds[k]}")


if __name__ == "__main__":
    main()
