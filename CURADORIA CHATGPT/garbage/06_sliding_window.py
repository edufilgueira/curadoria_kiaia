import json
from pathlib import Path

INPUT_FILE = Path("data/processed/05_scored_segments.jsonl")
OUTPUT_FILE = Path("data/processed/06_training_dataset.jsonl")

MAX_CONTEXT_TURNS = 6  # tamanho máximo da janela


def sliding_window(messages, max_turns):
    windows = []

    for i in range(1, len(messages), 2):
        start = max(0, i - max_turns)
        context = messages[start:i]
        target = messages[i]

        if target["role"] != "assistant":
            continue

        windows.append({
            "context": context,
            "response": target["content"]
        })

    return windows


def process():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    total_segments = 0
    total_examples = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as infile, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:

        for line in infile:
            data = json.loads(line)

            messages = data.get("messages", [])

            if len(messages) < 2:
                continue

            windows = sliding_window(messages, MAX_CONTEXT_TURNS)

            for w in windows:
                example = {
                    "conversation_id": data.get("conversation_id"),
                    "segment_id": data.get("segment_id"),
                    "context": w["context"],
                    "response": w["response"],
                    "quality_score": data.get("quality_score", 0.5)
                }

                outfile.write(json.dumps(example, ensure_ascii=False) + "\n")

                total_examples += 1

            total_segments += 1

    print(f"Segments processados: {total_segments}")
    print(f"Exemplos gerados: {total_examples}")


if __name__ == "__main__":
    process()
