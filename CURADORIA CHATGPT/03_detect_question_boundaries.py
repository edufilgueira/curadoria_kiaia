import json
import re
from pathlib import Path


INPUT_FILE = Path("data/processed/02_chatgpt_filtered.jsonl")
OUTPUT_FILE = Path("data/processed/03_chatgpt_questions.jsonl")


FOLLOWUP_PREFIXES = [
    "e ",
    "mas ",
    "então ",
    "também ",
    "isso ",
    "essa ",
    "esse ",
    "e a ",
    "e o ",
    "e os ",
    "e as ",
    "what about",
    "and ",
    "pronto",
    "quero",
    "sim",
    "não",
    "nao",
    "ok",
]


SHORT_QUESTION_WORDS = 6


def normalize(text):

    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)

    return text


def is_followup(question):

    q = normalize(question)

    for prefix in FOLLOWUP_PREFIXES:
        if q.startswith(prefix):
            return True

    if len(q.split()) <= SHORT_QUESTION_WORDS:
        return True

    return False


def split_by_boundaries(messages):

    segments = []
    current_segment = []

    last_user_question = None

    for msg in messages:

        if msg["role"] == "user":

            question = msg["content"]

            if last_user_question is None:

                current_segment.append(msg)
                last_user_question = question
                continue

            if is_followup(question):

                current_segment.append(msg)

            else:

                if current_segment:
                    segments.append(current_segment)

                current_segment = [msg]

            last_user_question = question

        else:

            current_segment.append(msg)

    if current_segment:
        segments.append(current_segment)

    return segments


def main():

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    total_segments = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as infile, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:

        for line in infile:

            item = json.loads(line)

            messages = item.get("messages", [])

            segments = split_by_boundaries(messages)

            for seg in segments:

                new_item = dict(item)
                new_item["messages"] = seg
                new_item["turn_count"] = len(seg)

                outfile.write(json.dumps(new_item, ensure_ascii=False) + "\n")

                total_segments += 1

    print("\nQuestion boundary detection complete")
    print("New segments created:", total_segments)
    print("Saved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
