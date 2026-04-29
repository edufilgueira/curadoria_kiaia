import json
import re
from pathlib import Path


INPUT_FILE = Path("data/processed/03_chatgpt_questions.jsonl")
OUTPUT_FILE = Path("data/processed/04_scored_segments.jsonl")


MIN_ASSISTANT_LENGTH = 40


EXPLANATION_KEYWORDS = [
    "porque",
    "por que",
    "isso ocorre",
    "isso acontece",
    "a razão",
    "o motivo",
    "explica",
    "exemplo",
    "por exemplo",
    "ou seja",
    "em outras palavras",
]


REASONING_KEYWORDS = [
    "passo",
    "etapa",
    "primeiro",
    "segundo",
    "terceiro",
    "então",
    "logo",
    "portanto",
    "consequentemente",
]


def normalize(text):

    text = text.lower()
    text = re.sub(r"\s+", " ", text)

    return text


def contains_keywords(text, keywords):

    for kw in keywords:
        if kw in text:
            return True

    return False


def get_assistant_text(messages):

    texts = []

    for m in messages:
        if m["role"] == "assistant":
            texts.append(m["content"])

    return " ".join(texts)


def score_length(text):

    length = len(text)

    if length < MIN_ASSISTANT_LENGTH:
        return 0.2

    if length < 120:
        return 0.5

    if length < 300:
        return 0.8

    return 1.0


def score_explanation(text):

    if contains_keywords(text, EXPLANATION_KEYWORDS):
        return 1.0

    return 0.4


def score_reasoning(text):

    if contains_keywords(text, REASONING_KEYWORDS):
        return 1.0

    return 0.5


def compute_quality(messages):

    assistant_text = get_assistant_text(messages)

    if not assistant_text:
        return 0.0

    assistant_text = normalize(assistant_text)

    length_score = score_length(assistant_text)
    explanation_score = score_explanation(assistant_text)
    reasoning_score = score_reasoning(assistant_text)

    quality = (
        length_score * 0.4 +
        explanation_score * 0.3 +
        reasoning_score * 0.3
    )

    return round(quality, 3)


def main():

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    total = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as infile, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:

        for line in infile:

            item = json.loads(line)

            messages = item.get("messages", [])

            score = compute_quality(messages)

            item["quality_score"] = score

            outfile.write(json.dumps(item, ensure_ascii=False) + "\n")

            total += 1

    print("\nQuality scoring complete")
    print("Segments scored:", total)
    print("Saved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
