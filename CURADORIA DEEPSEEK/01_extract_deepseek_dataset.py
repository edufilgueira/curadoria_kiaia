"""
Converte conversations.json (export DeepSeek) para linhas JSONL no mesmo esquema do
pipeline ChatGPT (CURADORIA CHATGPT/01_extract_chatgpt_dataset.py):
conversation_id, segment_id, messages, turn_count, reasoning_hint,
segment_start_time, source, dataset_version.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime
from pathlib import Path


def normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _parse_inserted_at(msg: dict | None) -> float | None:
    if not msg:
        return None
    raw = msg.get("inserted_at")
    if not isinstance(raw, str):
        return None
    s = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except ValueError:
        return None


def get_role_and_text(msg: dict | None) -> tuple[str | None, str, bool]:
    """
    Devolve (role, texto_visível, tinha_THINK).
    Só inclui REQUEST e RESPONSE no texto; THINK/SEARCH/READ_LINK não entram no content.
    """
    if not msg:
        return None, "", False
    fragments = msg.get("fragments") or []
    had_think = any(f.get("type") == "THINK" for f in fragments)

    req_parts: list[str] = []
    resp_parts: list[str] = []
    for f in fragments:
        ft = f.get("type")
        if ft == "REQUEST":
            c = f.get("content")
            if isinstance(c, str) and c:
                req_parts.append(c)
        elif ft == "RESPONSE":
            c = f.get("content")
            if isinstance(c, str) and c:
                resp_parts.append(c)

    if req_parts and not resp_parts:
        return "user", normalize("\n\n".join(req_parts)), had_think
    if resp_parts and not req_parts:
        return "assistant", normalize("\n\n".join(resp_parts)), had_think
    # Nó inesperado ou só ferramentas sem texto
    return None, "", had_think


def reconstruct_conversation(mapping: dict, leaf: str) -> list[dict]:
    chain: list[dict] = []
    node = mapping.get(leaf)
    while node:
        msg = node.get("message")
        if msg:
            role, text, had_think = get_role_and_text(msg)
            if role in ("user", "assistant") and text:
                chain.append(
                    {
                        "role": role,
                        "content": text,
                        "_ts": _parse_inserted_at(msg),
                        "_had_think": had_think,
                    }
                )
        parent = node.get("parent")
        if not parent:
            break
        node = mapping.get(parent)
    chain.reverse()
    return chain


def segment_conversation(chain: list[dict]) -> list[list[dict]]:
    segments: list[list[dict]] = []
    buffer: list[dict] = []
    for msg in chain:
        if msg["role"] == "user":
            if buffer:
                segments.append(buffer)
                buffer = []
        buffer.append(msg)
    if buffer:
        segments.append(buffer)
    return segments


def detect_reasoning(segment: list[dict]) -> str:
    text = " ".join(m["content"] for m in segment).lower()
    reasoning_keywords = [
        "por que",
        "explique",
        "como funciona",
        "demonstre",
        "passo a passo",
        "raciocínio",
        "why",
        "explain",
        "how does",
        "step by step",
    ]
    for kw in reasoning_keywords:
        if kw in text:
            return "explanation"
    if any(m.get("_had_think") for m in segment):
        return "explanation"
    return "none"


def segment_sort_key(segment: list[dict], fallback_index: int) -> tuple[float, int]:
    ts0 = segment[0].get("_ts") if segment else None
    if isinstance(ts0, (int, float)):
        return (float(ts0), fallback_index)
    times = [m["_ts"] for m in segment if isinstance(m.get("_ts"), (int, float))]
    if times:
        return (min(float(t) for t in times), fallback_index)
    return (float("inf"), fallback_index)


def messages_for_export(segment: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["content"]} for m in segment]


def segment_fingerprint(msgs: list[dict]) -> tuple:
    return tuple((m["role"], m["content"]) for m in msgs)


def find_leaf_nodes(mapping: dict) -> list[str]:
    children: set[str] = set()
    for node in mapping.values():
        parent = node.get("parent")
        if parent:
            children.add(parent)
    return [node_id for node_id in mapping if node_id not in children]


def process_conversation(convo: dict, out, source_tag: str, dataset_version: str) -> int:
    mapping = convo.get("mapping")
    conversation_id = convo.get("id") or str(uuid.uuid4())
    if not mapping:
        return 0

    leaves = find_leaf_nodes(mapping)
    pending: list = []
    order = 0

    for leaf in leaves:
        chain = reconstruct_conversation(mapping, leaf)
        segments = segment_conversation(chain)
        for seg in segments:
            if not seg:
                continue
            order += 1
            key = segment_sort_key(seg, order)
            start_ts = key[0]
            if start_ts == float("inf"):
                start_ts_out = None
            else:
                start_ts_out = start_ts
            reasoning = detect_reasoning(seg)
            for m in seg:
                m.pop("_had_think", None)
            pending.append(
                (
                    key,
                    messages_for_export(seg),
                    len(seg),
                    reasoning,
                    start_ts_out,
                )
            )

    pending.sort(key=lambda x: x[0])

    seen_keys: set = set()
    deduped: list = []
    for row in pending:
        msgs = row[1]
        start_ts_out = row[4]
        key_dedup = (segment_fingerprint(msgs), start_ts_out)
        if key_dedup in seen_keys:
            continue
        seen_keys.add(key_dedup)
        deduped.append(row)

    counted = 0
    for seg_index, row in enumerate(deduped, start=1):
        _key, msgs, turn_count, reasoning, start_ts_out = row
        item = {
            "conversation_id": conversation_id,
            "segment_id": f"{conversation_id}_{seg_index}",
            "messages": msgs,
            "turn_count": turn_count,
            "reasoning_hint": reasoning,
            "segment_start_time": start_ts_out,
            "source": source_tag,
            "dataset_version": dataset_version,
        }
        out.write(json.dumps(item, ensure_ascii=False) + "\n")
        counted += 1

    return counted


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Export DeepSeek conversations.json para JSONL estilo GPT.")
    parser.add_argument(
        "--input",
        type=Path,
        default=script_dir / "conversations.json",
        help="Arquivo conversations.json do DeepSeek",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "data" / "processed" / "01_deepseek_segments.jsonl",
        help="Saída JSONL",
    )
    parser.add_argument(
        "--source",
        default="deepseek_export",
        help='Valor do campo "source" (default: deepseek_export)',
    )
    parser.add_argument(
        "--dataset-version",
        default="v1",
        dest="dataset_version",
        help='Valor de dataset_version (default: v1)',
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print("Arquivo não encontrado:", args.input)
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total_segments = 0

    with open(args.output, "w", encoding="utf-8") as out_f:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
        conversations = data if isinstance(data, list) else [data]
        for convo in conversations:
            total_segments += process_conversation(
                convo, out_f, args.source, args.dataset_version
            )

    print("Extração concluída.")
    print("Segmentos:", total_segments)
    print("Salvo em:", args.output)


if __name__ == "__main__":
    main()
