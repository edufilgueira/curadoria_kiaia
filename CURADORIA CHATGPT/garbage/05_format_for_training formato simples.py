import json
from pathlib import Path

INPUT_FILE = Path("data/processed/04_scored_segments.jsonl")
OUTPUT_FILE = Path("05_llm_training_dataset.jsonl")

USER_TOKEN = "<|user|>"
ASSISTANT_TOKEN = "<|assistant|>"


def format_messages(messages):

    parts = []

    for msg in messages:

        role = msg.get("role")
        content = msg.get("content", "").strip()

        if not content:
            continue

        if role == "user":
            parts.append(f"{USER_TOKEN} {content}")

        elif role == "assistant":
            parts.append(f"{ASSISTANT_TOKEN} {content}")

    return "\n".join(parts)


def process():

    if not INPUT_FILE.exists():
        print("ERRO: arquivo não encontrado:", INPUT_FILE)
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    total_in = 0
    total_out = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as infile, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:

        for line in infile:

            total_in += 1

            try:
                data = json.loads(line)
            except:
                continue

            messages = data.get("messages", [])

            if not messages:
                continue

            text = format_messages(messages)

            if not text:
                continue

            example = {
                "text": text,
                "quality_score": data.get("quality_score", 0.5)
            }

            outfile.write(json.dumps(example, ensure_ascii=False) + "\n")

            total_out += 1

    print("Linhas lidas:", total_in)
    print("Exemplos gerados:", total_out)
    print("Arquivo salvo em:", OUTPUT_FILE)


if __name__ == "__main__":
    process()
