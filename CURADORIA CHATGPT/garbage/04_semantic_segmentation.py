import json
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


INPUT_FILE = Path("data/processed/03_chatgpt_questions.jsonl")
OUTPUT_FILE = Path("data/processed/04_semantic_segments.jsonl")

SIMILARITY_THRESHOLD = 0.55


model = SentenceTransformer("all-MiniLM-L6-v2")


def get_user_question(messages):

    for m in messages:
        if m["role"] == "user":
            return m["content"]

    return ""


def main():

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    segments_written = 0

    previous_embedding = None

    with open(INPUT_FILE, "r", encoding="utf-8") as infile, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:

        for line in infile:

            item = json.loads(line)

            messages = item.get("messages", [])

            question = get_user_question(messages)

            if not question:
                continue

            embedding = model.encode([question])[0]

            new_topic = False

            if previous_embedding is not None:

                sim = cosine_similarity(
                    [embedding],
                    [previous_embedding]
                )[0][0]

                if sim < SIMILARITY_THRESHOLD:
                    new_topic = True

            previous_embedding = embedding

            item["semantic_new_topic"] = new_topic

            outfile.write(json.dumps(item, ensure_ascii=False) + "\n")

            segments_written += 1

    print("\nSemantic segmentation complete")
    print("Segments processed:", segments_written)
    print("Saved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
