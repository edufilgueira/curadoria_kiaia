# 05_tag_conversations.py
"""
Adiciona tags (genero, funcao, tom) a cada segmento via LLM.
Alinha ao padrão da curadoria da Bíblia para compatibilidade futura.
Entrada: 04_scored_segments.jsonl
Saída: 05_tagged_segments.jsonl (mesma estrutura + tags)

LLM não é obrigatório: use --no-llm para tags padrão (pipeline sem API).
"""

import argparse
import json
import os
import random
import re
import time
from pathlib import Path


def anonymize_content(content: str, nome_remover) -> str:
    """Substitui nomes na resposta por 'a pessoa' (fallback quando LLM não anonimiza)."""
    if not content:
        return content
    if nome_remover is None:
        return content
    if isinstance(nome_remover, list):
        nome_remover = ",".join(str(n) for n in nome_remover if n)
    names = [n.strip() for n in str(nome_remover).split(",") if n.strip()]
    result = content
    for name in names:
        if not name:
            continue
        esc = re.escape(name)
        result = re.sub(rf"\b(da|do|de)\s+{esc}\b", "da pessoa", result, flags=re.IGNORECASE)
        result = re.sub(rf"\b{esc}\b", "a pessoa", result, flags=re.IGNORECASE)
    return result


MAX_ANONIMIZAR_LENGTH = 6000  # chars máx para envio à LLM (respostas maiores usam fallback regex)


def anonymize_with_llm(content: str, provider: str) -> str | None:
    """Chama a LLM para anonimizar o texto (remover nomes de pessoas). Retorna None em erro."""
    if not content or len(content.strip()) < 10:
        return content
    if len(content) > MAX_ANONIMIZAR_LENGTH:
        return None  # texto muito longo: usar fallback anonymize_content
    try:
        client, model = get_llm_client(provider)
        prompt = PROMPT_ANONIMIZAR_RESPOSTA.format(text=content)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=min(4096, len(content) + 500),
            temperature=0.1,
        )
        result = (response.choices[0].message.content or "").strip()
        result = re.sub(r"^```\w*\n?", "", result)
        result = re.sub(r"\n?```\s*$", "", result)
        if result and len(result) >= len(content) * 0.8:
            return result
    except Exception as e:
        print(f"  [LLM anonimizar erro: {e}]")
    return None

from config import (
    DEFAULT_TAGS,
    LLM_PROVIDERS,
    MAX_TEXT_LENGTH,
    MIN_SCORE,
    PAUSE_BATCH_MAX,
    PAUSE_BATCH_MIN,
    PAUSE_EVERY_N_REQUESTS,
    PROMPT_ANONIMIZAR_RESPOSTA,
    PROMPT_TAG_CONVERSATION,
)

INPUT_FILE = Path("data/processed/04_scored_segments.jsonl")
OUTPUT_FILE = Path("data/processed/05_tagged_segments.jsonl")


def has_llm_key(provider: str = "deepseek") -> bool:
    """Verifica se há API key configurada."""
    cfg = LLM_PROVIDERS.get(provider)
    return bool(cfg and os.environ.get(cfg["env_key"]))


def get_llm_client(provider: str):
    from openai import OpenAI
    cfg = LLM_PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Provedor '{provider}' inválido.")
    api_key = os.environ.get(cfg["env_key"])
    if not api_key:
        raise ValueError(f"Defina {cfg['env_key']} para usar {provider}")
    kwargs = {"api_key": api_key}
    if cfg.get("base_url"):
        kwargs["base_url"] = cfg["base_url"]
    return OpenAI(**kwargs), cfg["model"]


def extract_text_for_prompt(messages: list) -> str:
    """Extrai texto resumido para o prompt (user + assistant)."""
    parts = []
    total = 0
    for m in messages:
        role = m.get("role", "")
        content = (m.get("content", "") or "").strip()
        if not content:
            continue
        prefix = "User:" if role == "user" else "Assistant:"
        if total + len(content) > MAX_TEXT_LENGTH:
            remain = MAX_TEXT_LENGTH - total - 20
            content = content[:remain] + "..." if len(content) > remain else content
            parts.append(f"{prefix} {content}")
            break
        parts.append(f"{prefix} {content}")
        total += len(content)
    return "\n\n".join(parts) if parts else ""


def tag_conversation_llm(messages: list, provider: str, is_leitura_hint: bool = False) -> dict:
    """
    LLM classifica a conversa: tags (genero, funcao, tom) + tipo + intent.
    Se for leitura: tipo_consulta, contexto_anonimo, mensagem_user_anonimizada.
    """
    text = extract_text_for_prompt(messages)
    if not text:
        return _default_result(is_leitura_hint)

    prompt = PROMPT_TAG_CONVERSATION.format(text=text)

    try:
        client, model = get_llm_client(provider)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        parsed = json.loads(raw)

        tags = {
            "genero": _ensure_list(parsed.get("genero", DEFAULT_TAGS["genero"])),
            "funcao": _ensure_list(parsed.get("funcao", DEFAULT_TAGS["funcao"])),
            "tom": _ensure_list(parsed.get("tom", DEFAULT_TAGS["tom"])),
        }

        result = {"tags": tags}

        tipo_raw = str(parsed.get("tipo", "")).lower()
        result["user_melhorado_list"] = parsed.get("user_melhorado_list") or []
        if not isinstance(result["user_melhorado_list"], list):
            result["user_melhorado_list"] = [result["user_melhorado_list"]] if result["user_melhorado_list"] else []
        if tipo_raw in ("leitura", "pergunta_ao_campo"):
            result["tipo"] = tipo_raw
            result["fonte"] = "leitura_gpt"
            result["tipo_consulta"] = parsed.get("tipo_consulta") or "espiritual"
            result["contexto_anonimo"] = parsed.get("contexto_anonimo") or "consulta pessoal"
            result["anonimizado"] = True
            result["nome_remover"] = parsed.get("nome_remover")
            if not result["user_melhorado_list"] and parsed.get("user_anonimizado"):
                result["user_melhorado_list"] = [parsed.get("user_anonimizado")]
            result["metadata"] = {
                "genero_consulta": result["tipo_consulta"],
                "tom_resposta": tags.get("tom", ["conselheira"])[0] if tags.get("tom") else "conselheira",
                "campos_removidos": ["nome", "localizacao", "detalhes_identificaveis"],
            }
        else:
            result["tipo"] = "conversa"
            result["fonte"] = "chatgpt_export"

        return result
    except Exception as e:
        print(f"  [LLM erro: {e}] usando padrão")
        return _default_result(is_leitura_hint)


def _default_result(is_leitura: bool) -> dict:
    if is_leitura:
        return {
            "tags": {"genero": ["dialogo"], "funcao": ["conselho", "acolhimento"], "tom": ["conselheira"]},
            "tipo": "leitura",
            "fonte": "leitura_gpt",
            "tipo_consulta": "espiritual",
            "contexto_anonimo": "consulta pessoal",
            "anonimizado": False,
            "user_melhorado_list": [],
            "nome_remover": None,
            "metadata": {"genero_consulta": "espiritual", "tom_resposta": "conselheira", "campos_removidos": []},
        }
    return {
        "tags": DEFAULT_TAGS.copy(),
        "tipo": "conversa",
        "fonte": "chatgpt_export",
        "user_melhorado_list": [],
    }


def _ensure_list(x):
    if isinstance(x, list):
        return [str(v) for v in x if v][:3] or DEFAULT_TAGS["genero"]
    return [str(x)] if x else DEFAULT_TAGS["genero"]


def main():
    parser = argparse.ArgumentParser(description="Tag conversations via LLM (genero, funcao, tom)")
    parser.add_argument("--provider", "-p", default="deepseek", choices=list(LLM_PROVIDERS),
                        help="Provedor LLM (deepseek ou gpt)")
    parser.add_argument("--resume", "-r", action="store_true",
                        help="Continuar de onde parou (append)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Sem LLM: usa tags padrão (permite pipeline sem API)")
    parser.add_argument("--limit", "-l", type=int, default=0,
                        help="Limita número de segmentos a processar (0 = todos). Útil para teste.")
    parser.add_argument("--delay", "-d", type=float, default=0.2,
                        help="Segundos fixos entre chamadas (usado se --delay-min/--delay-max não forem passados)")
    parser.add_argument("--delay-min", type=float, default=None,
                        help="Mínimo segundos para intervalo aleatório (use com --delay-max)")
    parser.add_argument("--delay-max", type=float, default=None,
                        help="Máximo segundos para intervalo aleatório (use com --delay-min)")
    args = parser.parse_args()

    # Auto-fallback: se --no-llm não foi passado e não há API key, usa tags padrão
    if not args.no_llm and not has_llm_key(args.provider):
        print("Aviso: Nenhuma API key (DEEPSEEK_API_KEY/OPENAI_API_KEY). Usando tags padrão (--no-llm).")
        args.no_llm = True

    script_dir = Path(__file__).parent
    input_path = script_dir / INPUT_FILE
    output_path = script_dir / OUTPUT_FILE

    if not input_path.exists():
        print(f"ERRO: {input_path} não encontrado. Execute 04_quality_scoring.py primeiro.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Carregar segmentos
    segments = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                segments.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Filtrar por score
    segments = [s for s in segments if s.get("quality_score", 0) >= MIN_SCORE]
    segments = [s for s in segments if len(s.get("messages", [])) >= 2]

    # IDs já processados (para resume)
    done_ids = set()
    if args.resume and output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        obj = json.loads(line)
                        done_ids.add(obj.get("segment_id", ""))
                    except json.JSONDecodeError:
                        pass

    mode = "a" if args.resume else "w"
    total = len(segments)
    skipped = len(done_ids)
    written = 0

    with open(output_path, mode, encoding="utf-8") as out:
        for i, seg in enumerate(segments):
            seg_id = seg.get("segment_id", "")
            if seg_id in done_ids:
                continue

            if args.limit and written >= args.limit:
                print(f"Limite {args.limit} atingido.")
                break

            is_leitura_hint = seg.get("fonte") == "leitura_gpt"

            if args.no_llm:
                result = _default_result(is_leitura_hint)
            else:
                result = tag_conversation_llm(seg.get("messages", []), args.provider, is_leitura_hint)

            seg["tags"] = result["tags"]
            seg["tipo"] = result.get("tipo", "conversa")
            seg["fonte"] = result.get("fonte", seg.get("fonte", "chatgpt_export"))

            if result.get("tipo") in ("leitura", "pergunta_ao_campo"):
                seg["tipo_consulta"] = result.get("tipo_consulta", "espiritual")
                seg["contexto_anonimo"] = result.get("contexto_anonimo", "consulta pessoal")
                seg["anonimizado"] = result.get("anonimizado", False)
                seg["metadata"] = result.get("metadata", {})

            if seg.get("messages") and not args.no_llm:
                msgs = list(seg["messages"])
                seg["user_original_list"] = [m.get("content", "") or "" for m in msgs if m.get("role") == "user"]
                user_melhorado_list = result.get("user_melhorado_list") or []
                nome_remover = result.get("nome_remover") if result.get("tipo") in ("leitura", "pergunta_ao_campo") else None
                user_idx = 0
                for j, m in enumerate(msgs):
                    if m.get("role") == "user":
                        if user_idx < len(user_melhorado_list) and user_melhorado_list[user_idx]:
                            msgs[j] = {**m, "content": user_melhorado_list[user_idx]}
                        user_idx += 1
                    elif m.get("role") == "assistant" and result.get("tipo") in ("leitura", "pergunta_ao_campo"):
                        content = m.get("content", "") or ""
                        anon = anonymize_with_llm(content, args.provider)
                        msgs[j] = {**m, "content": anon if anon is not None else anonymize_content(content, nome_remover)}
                seg["messages"] = msgs

            out.write(json.dumps(seg, ensure_ascii=False) + "\n")
            out.flush()
            written += 1

            tags = seg.get("tags", {})
            tipo = seg.get("tipo", "-")
            tom = (tags.get("tom") or ["-"])[0] if isinstance(tags.get("tom"), list) else tags.get("tom", "-")
            funcao = (tags.get("funcao") or ["-"])[0] if isinstance(tags.get("funcao"), list) else tags.get("funcao", "-")
            print(f"\r  Processados: {written}/{total} | tipo: {tipo} | tom: {tom} | funcao: {funcao}", end="", flush=True)

            if not args.no_llm:
                if args.delay_min is not None and args.delay_max is not None:
                    time.sleep(random.uniform(args.delay_min, args.delay_max))
                else:
                    time.sleep(args.delay)
                if written > 0 and written % PAUSE_EVERY_N_REQUESTS == 0:
                    pausa = random.uniform(PAUSE_BATCH_MIN, PAUSE_BATCH_MAX)
                    print(f"\n  [pausa {pausa:.1f}s após {written} requisições]")
                    time.sleep(pausa)

    print()
    print(f"Segmentos lidos: {total}")
    print(f"Novos taggeados: {written}")
    if args.resume:
        print(f"Já existentes (skip): {skipped}")
    print(f"Salvo em: {output_path}")


if __name__ == "__main__":
    main()
