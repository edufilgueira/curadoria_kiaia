#!/usr/bin/env python3
"""
Extrai segmentos de leitura de campo para tratamento separado.

O arquivo 04_scored_segments.jsonl não contém o campo "tipo" (definido no passo 05).
Este script:
  1) Lê 05_tagged_segments.jsonl e coleta segment_id onde tipo == "leitura"
  2) Copia do 04_scored_segments.jsonl apenas as linhas com esses segment_id

Saída: leitura-de-campo/04_leitura_de_campo.jsonl (JSONL, mesmo formato do 04)
"""

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PATH_04 = SCRIPT_DIR / "data/processed/04_scored_segments.jsonl"
PATH_05 = SCRIPT_DIR / "data/processed/05_tagged_segments.jsonl"
OUT_DIR = SCRIPT_DIR / "data/leitura-de-campo"
DEFAULT_OUT = OUT_DIR / "extra_leitura_de_campo.jsonl"


def load_leitura_segment_ids(path_05: Path) -> set[str]:
    ids: set[str] = set()
    with open(path_05, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("tipo") == "leitura" and rec.get("segment_id"):
                ids.add(rec["segment_id"])
    return ids


def filter_04(path_04: Path, segment_ids: set[str], path_out: Path) -> tuple[int, int]:
    written = 0
    total_04 = 0
    with open(path_04, "r", encoding="utf-8") as fin, open(path_out, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            total_04 += 1
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = rec.get("segment_id")
            if sid in segment_ids:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                written += 1
    return total_04, written


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrai segmentos tipo leitura (via 05) do arquivo 04")
    parser.add_argument(
        "--input-04",
        type=Path,
        default=PATH_04,
        help="Fonte dos registros completos (padrão: data/processed/04_scored_segments.jsonl)",
    )
    parser.add_argument(
        "--input-05",
        type=Path,
        default=PATH_05,
        help="Arquivo com campo tipo (padrão: data/processed/05_tagged_segments.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="JSONL de saída",
    )
    args = parser.parse_args()

    if not args.input_05.exists():
        print(f"Erro: não encontrado {args.input_05}")
        return 1
    if not args.input_04.exists():
        print(f"Erro: não encontrado {args.input_04}")
        return 1

    segment_ids = load_leitura_segment_ids(args.input_05)
    if not segment_ids:
        print("Nenhum segment_id com tipo leitura em", args.input_05)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total_04, written = filter_04(args.input_04, segment_ids, args.output)

    missing = len(segment_ids) - written
    print(f"IDs tipo leitura (05): {len(segment_ids)}")
    print(f"Linhas no 04: {total_04}")
    print(f"Gravadas (interseção): {written} → {args.output}")
    if missing > 0:
        print(f"Aviso: {missing} segment_id de leitura não apareceram no 04 (pipeline desatualizado?)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
