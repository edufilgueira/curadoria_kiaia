"""
Filtros: estrutura, melhore texto, código, leituras (marca fonte), similaridade, deduplicação.
Lê 01_chatgpt_segments.jsonl → grava 02_chatgpt_filtered.jsonl.

- Similaridade: remove segmentos onde pergunta e resposta são muito parecidas (TF-IDF + cosine).
- Deduplicação: remove segmentos com conteúdo idêntico ou muito parecido entre si (exata + 0.95).

Requer: pip install scikit-learn
"""

import json
from pathlib import Path


INPUT_FILE = Path("data/processed/01_chatgpt_segments.jsonl")
OUTPUT_FILE = Path("data/processed/02_chatgpt_filtered.jsonl")
REPORT_FILE = Path("data/processed/02_chatgpt_filtered.txt")

# Similaridade >= threshold → remove (pergunta e resposta muito parecidas)
SIMILARITY_THRESHOLD = 0.8

# Deduplicação: remove segmentos com conteúdo muito parecido entre si (TF-IDF + cosine)
# Threshold >= valor → considera duplicata e remove (mantém o primeiro)
DEDUP_THRESHOLD = 0.95

# Leituras de campo, vibracional, profética, dinâmica
LEITURA_PATTERNS = [
    "leitura de campo",
    "leitura vibracional",
    "analisa a frequencia",
    "leitura profética",
    "leitura profetica",
    "leitura de dinâmica",
    "leitura de dinamica",
    "dinâmica de ",
    "dinamica de ",
    "analisa o campo",
    "analisa a dinâmica",
    "analisa a dinamica",
    "faz a leitura",
    "faz a leitura de",
    "pedindo a leitura",
    "pedindo leitura",
    "pessoa tal",
    "pessoa fulano",
    "leitura dela",
    "leitura dele",
]

# Perguntas genéricas de edição — excluir
MELHORE_TEXTO_PATTERNS = [
    "reescreva este texto",
    "melhore este prompt",
    "conte o numero de palavra do texto:",
    "esta dando 0% o resultado refaça o prompt",
    "melhores este pronpt",
    "melhore este texto",
    "como fazer chantilly",
    "melhore o ",
    "mude o texto",
    "altere o texto",
    "melhore este tesdto",
    "melhore este testo",
    "logotipo do site",
    "coxinha",
    "resolução nº 23.735",
    "o balanced scorecard",
    "melhora este texto"
    "resumir com outras palavras"
    "dívida pública"
]

# Pedidos de código / n8n / JSON / conversões técnicas — excluir
CODIGO_PATTERNS = [
    "n8n",
    "$input.first",
    "$input.first().json",
    "organize esse json",
    "organiza esse json",
    "organize esse objeto",
    "organiza esse objeto",
    "organiza 400",
    "organize 400",
    "converta para inteiro",
    "converta para float",
    "converta para string",
    "gere código",
    "gerar código",
    "crie um hotsite",
    "crie um site",
    "$('",
    "base64",
    "pixQrCode",
    "decodifique",
    "docker",
    "ruby",
    "rails",
    "rspec",
    '"role',
    "calcule o intervalo",
    "tenho uma data",
    "esp32",
    "https://t.me/+zEYXsdLXvfs3NmIx",
    "regex",
    "tranzar",
    "vadia",
    "果",
    "ams1117",
    "esp8266",
    "resumo do texto",
    "qual a potencia de condsumo",
    "crie um texto",
    "resuma o texto",
    "qual link",
    "dívida pública",
    "refaça o texto",
    "resumir com outras palavras"
    "tinkercad",
    "arduino",
    "hidraulico",
    "pdf",
    "que erro é esse",
    "response.",
    "nodejs",
    "apt/",
    "apt insta",
    "nodesource",
    " apt ",
    "clinica",
    " sql ",
    "routes",
    "error:",
    "hf_token",
    " token ",
    " login ",
    " pip ",
    "llama",
    ".includes",
    "substring",
    "emulsificante",
    "alginato de sódio",
    "leite condensado",
    "receita",
    "placa de vídeo",
    "10000 a 1%",
    "e de 22 mil",
    "e de 10300",
    "quanto é 65%",
    "10000",
    "okr"
]


def contains_pattern(text, patterns):
    text = text.lower()
    for p in patterns:
        if p in text:
            return True
    return False


def is_leitura(segment):
    """Detecta leituras de campo/vibracional/profética/dinâmica — permitir no dataset."""
    user_texts = [m["content"] for m in segment if m.get("role") == "user"]
    text = " ".join(user_texts).lower() if user_texts else ""
    return contains_pattern(text, LEITURA_PATTERNS)


def is_melhore_texto(segment):
    """Exclui pedidos genéricos de edição."""
    user_texts = [m["content"] for m in segment if m.get("role") == "user"]
    text = " ".join(user_texts).lower() if user_texts else ""
    return contains_pattern(text, MELHORE_TEXTO_PATTERNS)


def is_codigo(segment):
    """Exclui pedidos de código (n8n, JSON, conversões, etc.). Verifica user + assistant."""
    all_texts = [m.get("content", "") for m in segment]
    text = " ".join(all_texts).lower() if all_texts else ""
    return contains_pattern(text, CODIGO_PATTERNS)


def valid_structure(messages):
    if not messages:
        return False
    if messages[0]["role"] != "user":
        return False
    if "assistant" not in [m["role"] for m in messages]:
        return False
    return True


def get_user_text(messages):
    return " ".join(m.get("content", "") or "" for m in messages if m.get("role") == "user").strip()


def get_assistant_text(messages):
    return " ".join(m.get("content", "") or "" for m in messages if m.get("role") == "assistant").strip()


def get_segment_text(messages):
    """Concatena user + assistant para comparação entre segmentos (deduplicação)."""
    user = get_user_text(messages)
    assistant = get_assistant_text(messages)
    return f"{user} {assistant}".strip()


def compute_similarity(text1: str, text2: str) -> float:
    """Retorna similaridade cosine (0 a 1) entre dois textos usando TF-IDF."""
    if not text1.strip() or not text2.strip():
        return 0.0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer()
        matrix = vec.fit_transform([text1, text2])
        sim = cosine_similarity(matrix[0], matrix[1])[0][0]
        return float(sim)
    except ImportError:
        print("ERRO: scikit-learn não instalado. Execute: pip install scikit-learn")
        raise


def main():
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        print("ERRO: scikit-learn não instalado. Execute: pip install scikit-learn")
        return

    script_dir = Path(__file__).parent
    input_path = script_dir / INPUT_FILE
    output_path = script_dir / OUTPUT_FILE

    if not input_path.exists():
        print(f"ERRO: {input_path} não encontrado. Execute 01_extract_chatgpt_dataset.py primeiro.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    kept_leituras = 0
    removed_melhore_texto = 0
    removed_codigo = 0
    removed_structure = 0
    removed_similar = 0
    similar_examples = []
    items_passed = []  # Acumula itens que passaram nos filtros (antes da deduplicação)

    # Para relatório: guardar todos os removidos (segment_id, motivo, preview)
    removed_structure_items = []
    removed_melhore_items = []
    removed_codigo_items = []
    removed_similar_items = []
    total_read = 0

    with open(input_path, "r", encoding="utf-8") as infile:
        for line in infile:
            line = line.strip()
            if not line:
                continue

            total_read += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            messages = item.get("messages", [])
            user_text = get_user_text(messages)
            assistant_text = get_assistant_text(messages)
            preview = lambda u, a: {"segment_id": item.get("segment_id"), "user": (u[:150] + "..." if len(u) > 150 else u) if u else "", "assistant": (a[:150] + "..." if len(a) > 150 else a) if a else ""}

            if not valid_structure(messages):
                removed_structure += 1
                removed_structure_items.append(preview(user_text, assistant_text))
                continue

            if is_melhore_texto(messages):
                removed_melhore_texto += 1
                removed_melhore_items.append(preview(user_text, assistant_text))
                continue

            if is_codigo(messages):
                removed_codigo += 1
                removed_codigo_items.append(preview(user_text, assistant_text))
                continue

            # Filtro de similaridade (pergunta vs resposta)
            if len(messages) >= 2:
                if user_text and assistant_text:
                    similarity = compute_similarity(user_text, assistant_text)
                    if similarity >= SIMILARITY_THRESHOLD:
                        removed_similar += 1
                        p = preview(user_text, assistant_text)
                        p["similarity"] = round(similarity, 3)
                        removed_similar_items.append(p)
                        if len(similar_examples) < 5:
                            similar_examples.append({
                                "segment_id": item.get("segment_id"),
                                "similarity": round(similarity, 3),
                                "user_preview": user_text[:80] + "..." if len(user_text) > 80 else user_text,
                                "assistant_preview": assistant_text[:80] + "..." if len(assistant_text) > 80 else assistant_text,
                            })
                        continue

            if is_leitura(messages):
                item["fonte"] = "leitura_gpt"
                kept_leituras += 1

            items_passed.append(item)

    # Deduplicação: 1) exatos (hash) 2) aproximados (TF-IDF + cosine)
    texts = [get_segment_text(item.get("messages", [])) for item in items_passed]
    text_normalized = [t.lower().strip() for t in texts]

    # 1. Duplicatas exatas (rápido)
    seen_exact = set()
    exact_kept = []
    removed_exact = 0
    removed_exact_items = []
    for i, t in enumerate(text_normalized):
        if not t:
            exact_kept.append(i)
            continue
        if t in seen_exact:
            removed_exact += 1
            it = items_passed[i]
            u, a = get_user_text(it.get("messages", [])), get_assistant_text(it.get("messages", []))
            removed_exact_items.append({
                "segment_id": it.get("segment_id"),
                "user": (u[:150] + "...") if len(u) > 150 else u,
                "assistant": (a[:150] + "...") if len(a) > 150 else a,
            })
            continue
        seen_exact.add(t)
        exact_kept.append(i)

    # 2. Duplicatas aproximadas (TF-IDF)
    vec = TfidfVectorizer()
    matrix = vec.fit_transform([texts[i] for i in exact_kept])

    kept_indices = []
    removed_dedup = 0
    dedup_examples = []
    removed_dedup_items = []
    exact_items = [items_passed[i] for i in exact_kept]
    exact_texts = [texts[i] for i in exact_kept]

    for i in range(len(exact_items)):
        if not kept_indices:
            kept_indices.append(i)
            continue
        sims = cosine_similarity(matrix[i], matrix[kept_indices])
        max_sim = float(sims.max())
        if max_sim >= DEDUP_THRESHOLD:
            removed_dedup += 1
            j = int(sims.argmax())
            dup_of_id = exact_items[kept_indices[j]].get("segment_id")
            msgs = exact_items[i].get("messages", [])
            u, a = get_user_text(msgs), get_assistant_text(msgs)
            removed_dedup_items.append({
                "segment_id": exact_items[i].get("segment_id"),
                "similarity": round(max_sim, 3),
                "duplicate_of": dup_of_id,
                "user": (u[:150] + "...") if len(u) > 150 else u,
                "assistant": (a[:150] + "...") if len(a) > 150 else a,
            })
            if len(dedup_examples) < 5:
                dedup_examples.append({
                    "segment_id": exact_items[i].get("segment_id"),
                    "similarity": round(max_sim, 3),
                    "preview": (exact_texts[i][:100] + "...") if len(exact_texts[i]) > 100 else exact_texts[i],
                })
        else:
            kept_indices.append(i)

    kept_items = [exact_items[i] for i in kept_indices]

    with open(output_path, "w", encoding="utf-8") as outfile:
        for item in kept_items:
            outfile.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Relatório: o que ficou e o que saiu (para controle/verificação)
    report_path = script_dir / REPORT_FILE
    with open(report_path, "w", encoding="utf-8") as rep:
        rep.write("=== RELATÓRIO 02_chatgpt_filtered ===\n")
        rep.write(f"Arquivo gerado junto com {OUTPUT_FILE.name}\n\n")

        rep.write("--- RESUMO ---\n")
        rep.write(f"Total lido: {total_read}\n")
        rep.write(f"Mantidos: {len(kept_items)}\n")
        rep.write(f"Removidos estrutura: {removed_structure}\n")
        rep.write(f"Removidos melhore_texto: {removed_melhore_texto}\n")
        rep.write(f"Removidos codigo: {removed_codigo}\n")
        rep.write(f"Removidos similaridade (user/assistant >= {SIMILARITY_THRESHOLD}): {removed_similar}\n")
        rep.write(f"Removidos dedup exata: {removed_exact}\n")
        rep.write(f"Removidos dedup aproximada (>= {DEDUP_THRESHOLD}): {removed_dedup}\n\n")

        rep.write("--- MANTIDOS (segment_id) ---\n")
        for item in kept_items:
            rep.write(f"{item.get('segment_id', '')}\n")
        rep.write("\n")

        def write_removed(rep, title, items, extra_key=None):
            rep.write(f"--- REMOVIDOS: {title} ---\n")
            for r in items:
                rep.write(f"segment_id: {r.get('segment_id', '')}\n")
                if extra_key and extra_key in r:
                    rep.write(f"  {extra_key}: {r[extra_key]}\n")
                rep.write(f"  user: {r.get('user', '')}\n")
                rep.write(f"  assistant: {r.get('assistant', '')}\n")
                rep.write("\n")
            rep.write("\n")

        write_removed(rep, "estrutura", removed_structure_items)
        write_removed(rep, "melhore_texto", removed_melhore_items)
        write_removed(rep, "codigo", removed_codigo_items)
        write_removed(rep, f"similaridade user/assistant (>= {SIMILARITY_THRESHOLD})", removed_similar_items, "similarity")
        write_removed(rep, "dedup exata", removed_exact_items)
        rep.write(f"--- REMOVIDOS: dedup aproximada (>= {DEDUP_THRESHOLD}) ---\n")
        for r in removed_dedup_items:
            rep.write(f"segment_id: {r.get('segment_id', '')} (sim={r.get('similarity')}, duplicata de: {r.get('duplicate_of', '')})\n")
            rep.write(f"  user: {r.get('user', '')}\n")
            rep.write(f"  assistant: {r.get('assistant', '')}\n")
            rep.write("\n")

    print("\n=== 02 Filter (estrutura + melhore texto + codigo + similaridade + deduplicação) ===\n")
    print("Segments kept:", len(kept_items))
    if kept_leituras:
        print("  Incl. leituras (campo/vibracional/profética/dinâmica):", kept_leituras)
    print("Removed melhore texto:", removed_melhore_texto)
    print("Removed codigo:", removed_codigo)
    print("Removed bad structure:", removed_structure)
    print(f"Removed (similaridade user/assistant >= {SIMILARITY_THRESHOLD}):", removed_similar)
    print(f"Removed (deduplicação exata):", removed_exact)
    print(f"Removed (deduplicação aproximada >= {DEDUP_THRESHOLD}):", removed_dedup)
    print("\nSaved to:", output_path)
    print("Report (mantidos + removidos):", report_path)

    if similar_examples:
        print("\nExemplos removidos por similaridade user/assistant (primeiros 5):")
        for ex in similar_examples:
            print(f"  - {ex['segment_id']} (sim={ex['similarity']})")
            print(f"    User: {ex['user_preview']}")
            print(f"    Asst: {ex['assistant_preview']}")

    if dedup_examples:
        print("\nExemplos removidos por deduplicação (primeiros 5):")
        for ex in dedup_examples:
            print(f"  - {ex['segment_id']} (sim={ex['similarity']})")
            print(f"    Preview: {ex['preview']}")


if __name__ == "__main__":
    main()
