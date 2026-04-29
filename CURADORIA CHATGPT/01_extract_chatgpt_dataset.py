import json
import re
import uuid
from pathlib import Path


INPUT_DIR = Path("data/raw")
OUTPUT_FILE = Path("data/processed/01_chatgpt_segments.jsonl")
# Segmentos por conversa: ordenados por message.create_time; cópias vindas de ramos paralelos
# (várias folhas no mapping) são fundidas se o par (mensagens, segment_start_time) for idêntico.


def normalize(text):
    """Preserva quebras de linha para manter estrutura markdown (títulos, listas, parágrafos)."""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    # Colapsa múltiplos espaços/tabs na mesma linha, mas preserva quebras de linha
    text = re.sub(r"[ \t]+", " ", text)
    # Normaliza 3+ quebras consecutivas em no máximo 2 (\n\n)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def get_text_from_message(msg):

    if not msg:
        return ""

    content = msg.get("content")
    if not content:
        return ""

    parts = content.get("parts")

    if not parts:
        return ""

    part = parts[0]

    if isinstance(part, str):
        return normalize(part)

    if isinstance(part, dict):
        return normalize(part.get("text", ""))

    return ""


def _message_create_time(msg):
    if not msg:
        return None
    ts = msg.get("create_time")
    if isinstance(ts, (int, float)):
        return float(ts)
    return None


def reconstruct_conversation(mapping, leaf):

    chain = []
    node = mapping.get(leaf)

    while node:

        msg = node.get("message")

        if msg:

            role = msg.get("author", {}).get("role")
            text = get_text_from_message(msg)

            if role in ["user", "assistant"] and text:

                chain.append({
                    "role": role,
                    "content": text,
                    "_ts": _message_create_time(msg),
                })

        parent = node.get("parent")

        if not parent:
            break

        node = mapping.get(parent)

    chain.reverse()

    return chain


def segment_conversation(chain):

    segments = []
    buffer = []

    for msg in chain:

        if msg["role"] == "user":

            if buffer:
                segments.append(buffer)
                buffer = []

        buffer.append(msg)

    if buffer:
        segments.append(buffer)

    return segments


def detect_reasoning(segment):

    text = " ".join([m["content"] for m in segment]).lower()

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
        "step by step"
    ]

    for kw in reasoning_keywords:
        if kw in text:
            return "explanation"

    return "none"


def segment_sort_key(segment, fallback_index):
    """Ordena segmentos pelo create_time da exportação (início do bloco user→…)."""
    ts0 = segment[0].get("_ts") if segment else None
    if isinstance(ts0, (int, float)):
        return (float(ts0), fallback_index)
    times = [
        m["_ts"] for m in segment
        if isinstance(m.get("_ts"), (int, float))
    ]
    if times:
        return (min(float(t) for t in times), fallback_index)
    return (float("inf"), fallback_index)


def messages_for_export(segment):
    return [{"role": m["role"], "content": m["content"]} for m in segment]


def segment_fingerprint(msgs):
    """Identifica turnos idênticos vindos de ramos diferentes (várias folhas na árvore)."""
    return tuple((m["role"], m["content"]) for m in msgs)


def find_leaf_nodes(mapping):

    children = set()

    for node in mapping.values():

        parent = node.get("parent")

        if parent:
            children.add(parent)

    leaves = []

    for node_id in mapping:

        if node_id not in children:
            leaves.append(node_id)

    return leaves


def process_conversation(convo, output_file):

    mapping = convo.get("mapping")
    conversation_id = convo.get("id", str(uuid.uuid4()))

    if not mapping:
        return 0

    leaves = find_leaf_nodes(mapping)

    pending = []
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

            pending.append((
                key,
                messages_for_export(seg),
                len(seg),
                detect_reasoning(seg),
                start_ts_out,
            ))

    pending.sort(key=lambda x: x[0])

    seen_keys: set = set()
    deduped = []
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
            "source": "chatgpt_export",
            "dataset_version": "v1",
        }
        output_file.write(json.dumps(item, ensure_ascii=False) + "\n")
        counted += 1

    return counted


def main():

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(INPUT_DIR.glob("conversations*.json"))

    if not files:
        print("No conversation files found in:", INPUT_DIR)
        return

    print(f"Found {len(files)} conversation files\n")

    total_segments = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:

        for file in files:

            print("Processing:", file.name)

            with open(file, "r", encoding="utf-8") as f:

                data = json.load(f)

                if isinstance(data, list):
                    conversations = data
                else:
                    conversations = [data]

                for convo in conversations:

                    total_segments += process_conversation(convo, out)

    print("\nExtraction complete")
    print("Segments extracted:", total_segments)
    print("Saved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
