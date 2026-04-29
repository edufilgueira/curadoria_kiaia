#!/usr/bin/env python3
"""
06 — Formata segmentos taggeados (05) para JSONL de treino/refino de LLM.

Saída: uma linha JSON por exemplo, formato compatível com curadoria da Bíblia:
  {"messages": [{"role": "user"|"assistant", "content": "..."}, ...]}

Filtros (padrão): quality_score >= 0.55 (README). Opcional: restringir a um único tipo
(--only-tipo), p.ex. apenas leituras de campo.

Entrada padrão: data/processed/05_tagged_segments.jsonl
Saída padrão:   data/final/06_llm_training_dataset.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# DEFAULT_INPUT = Path("data/processed/05_tagged_segments.jsonl")
# DEFAULT_OUTPUT = Path("data/final/06_llm_training_dataset.jsonl")
DEFAULT_INPUT = Path("data/leitura-de-campo/extra_leitura_de_campo.jsonl")
DEFAULT_OUTPUT = Path("data/leitura-de-campo/extra_leitura_de_campo_training_dataset.jsonl")

MIN_SCORE_TRAINING = 0.55


def main() -> None:
    parser = argparse.ArgumentParser(description="Formatar 05 → JSONL messages-only para treino LLM.")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Caminho do 05_tagged_segments.jsonl (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Arquivo de saída (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=MIN_SCORE_TRAINING,
        help=f"Descartar segmentos com quality_score abaixo disto (default: {MIN_SCORE_TRAINING})",
    )
    parser.add_argument(
        "--only-tipo",
        type=str,
        default=None,
        metavar="TIPO",
        help='Se definido, manter só esse tipo (ex.: "leitura", "conversa", "pergunta_ao_campo").',
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"Arquivo não encontrado: {args.input}")

    args.output.parent.mkdir(parents=True, exist_ok=True)

    total_in = 0
    skipped_score = 0
    skipped_tipo = 0
    skipped_short = 0
    written = 0

    with open(args.input, encoding="utf-8") as inf, open(args.output, "w", encoding="utf-8") as outf:
        for line in inf:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            total_in += 1
            qs = row.get("quality_score")
            if qs is None:
                qs = 0.0
            try:
                qs = float(qs)
            except (TypeError, ValueError):
                qs = 0.0

            if qs < args.min_score:
                skipped_score += 1
                continue

            if args.only_tipo is not None and row.get("tipo") != args.only_tipo:
                skipped_tipo += 1
                continue

            messages = row.get("messages") or []
            if len(messages) < 2:
                skipped_short += 1
                continue

            outf.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
            written += 1

    print(f"Lidos (linhas JSON): {total_in}")
    print(f"Gravados: {written} → {args.output.resolve()}")
    print(f"Descartados (score < {args.min_score}): {skipped_score}")
    if args.only_tipo is not None:
        print(f"Descartados (tipo ≠ {args.only_tipo!r}): {skipped_tipo}")
    print(f"Descartados (< 2 mensagens): {skipped_short}")


if __name__ == "__main__":
    main()
