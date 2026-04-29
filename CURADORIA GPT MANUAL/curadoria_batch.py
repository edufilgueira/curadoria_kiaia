#!/usr/bin/env python3
"""
Biblioteca compartilhada da curadoria em JSONL (parse, validação, commit no disco).
O fluxo automático está em curadoria_playwright.py.

CLI disponível:
  python curadoria_batch.py reset ...
     Repor fonte a partir de um .bak e/ou esvaziar o curado (ver --help).
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import unicodedata
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).resolve().parent
CONFIG_DEFAULT = DIR / "curadoria_config.json"
# Fonte (JSONL a processar) e saída (dataset curado): único sítio a editar ao mudar de ficheiro.
# curadoria_playwright.py, reset e resolve_source_curated_paths usam sempre estas constantes.
SOURCE = DIR / "data/select/pergunta_resposta.jsonl"
CURATED = DIR / "data/exports/base_de_conhecimento/dataset_pergunta_resposta.jsonl"
PROMPT_FILE = DIR / "prompt_curadoria.txt"
# Artefactos antigos do modo manual (reset remove se ainda existirem)
_STALE_MANUAL = (
    DIR / "pending_batch.jsonl",
    DIR / "resposta_deepseek.txt",
    DIR / "COLAR_NO_DEEPSEEK.txt",
)
BACKUP_SUFFIX = ".bak"


def _json_loads_loose(s: str):
    """json.loads; se falhar, tenta json_repair (modelos costumam quebrar aspas em content)."""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        try:
            import json_repair  # type: ignore[import-untyped]

            return json_repair.loads(s)
        except ImportError as e:
            raise ValueError(
                "JSON inválido e json_repair não instalado. Rode: pip install json_repair"
            ) from e
        except Exception as e:
            raise ValueError(f"JSON inválido (json_repair também falhou): {e}") from e


def _extract_braced_object_at(s: str, start: int) -> tuple[str | None, int]:
    """A partir de start em '{{', devolve o objeto JSON como substring (respeitando strings)."""
    n = len(s)
    if start >= n or s[start] != "{":
        return None, min(start + 1, n)
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < n:
        c = s[i]
        if esc:
            esc = False
            i += 1
            continue
        if in_str:
            if c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1], i + 1
        i += 1
    return None, start + 1


def resolve_source_curated_paths(config_path: Path | None) -> tuple[Path, Path]:
    """Devolve sempre SOURCE e CURATED deste módulo (config_path ignorado para caminhos)."""
    return SOURCE, CURATED


def build_curator_prompt_block(prompt: str, batch: list[str]) -> str:
    """Junta o prompt fixo, lembrete de contagem e as linhas JSON do lote."""
    n = len(batch)
    inject = (
        f"\n\n[CONTAGEM: {n} linha(s) de entrada abaixo. "
        f"Sua resposta deve ter exatamente {n} linha(s), cada uma um JSON completo. "
        "Nenhum texto antes ou depois.]\n\n"
    )
    return prompt.rstrip() + inject + "\n".join(batch) + "\n"


def load_prompt() -> str:
    if PROMPT_FILE.is_file():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return (
        "Curadoria JSONL: devolva o mesmo número de linhas, cada uma um JSON válido "
        'no formato {"messages":[...]}. Sem markdown.\n\n--- LINHAS A CURAR ---\n\n'
    )


def read_jsonl_lines(path: Path) -> list[str]:
    lines: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                lines.append(s)
    return lines


def write_jsonl_lines(path: Path, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line.strip() + "\n")


def backup_file(path: Path) -> Path | None:
    if not path.is_file():
        return None
    b = path.with_name(path.name + BACKUP_SUFFIX)
    shutil.copy2(path, b)
    return b


def strip_fences(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:jsonl|json)?\s*\n?(.*)\n?```\s*$", t, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def parse_response_lines(text: str) -> list[str]:
    body = strip_fences(text)
    out: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        out.append(s)
    return out


def _user_key_from_messages_obj(obj: dict) -> str:
    """Chave estável para emparelhar pergunta do lote com a linha devolvida pelo modelo."""
    for m in obj.get("messages") or []:
        if isinstance(m, dict) and m.get("role") == "user":
            return " ".join((m.get("content") or "").split())
    return ""


def _first_assistant_content(obj: dict) -> str:
    for m in obj.get("messages") or []:
        if isinstance(m, dict) and m.get("role") == "assistant":
            return (m.get("content") or "").strip()
    return ""


# Pergunta usa forma de dicionário; resposta curada pode usar infinitivo/outra flexão.
_TOPIC_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "peque": ("pecar", "pecado", "pecados", "peca", "pecando", "pecaram"),
}


_OVERLAP_STOPWORDS = frozenset(
    """
    mais como quem esse essa esse isso aquilo para pela pelo sobre tudo nada algo cada
    onde quando qual quais tipo isto deve pois nome vez devem foram sido suas seus suas
    pelo pela num nos nas nem sem sob seu sua somente muito muita então essa esse
    """.split()
)


def _significant_question_tokens(user_key: str) -> list[str]:
    """Palavras do enunciado úteis para checar se a resposta é do mesmo tema (exclui ruído comum)."""
    raw = [t for t in re.findall(r"\w+", user_key.lower()) if len(t) >= 4]
    return [t for t in raw if t not in _OVERLAP_STOPWORDS]


def _fold_norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower()


def _relaxed_term_in_haystack(term_folded: str, hay_folded: str) -> bool:
    if len(term_folded) < 4:
        return False
    if term_folded in hay_folded:
        return True
    if len(term_folded) >= 5 and term_folded[:5] in hay_folded:
        return True
    if len(term_folded) >= 7 and term_folded.endswith("ar"):
        stem = term_folded[:-2]
        if len(stem) >= 4 and stem in hay_folded:
            return True
    for alt in _TOPIC_TERM_ALIASES.get(term_folded, ()):
        if alt in hay_folded:
            return True
    # Palavras longas: “significado” vs “significa”, etc. (SequenceMatcher não cobre bem verbos curtos.)
    if len(term_folded) >= 8:
        for w in re.findall(r"\w+", hay_folded):
            if len(w) < 4 or abs(len(w) - len(term_folded)) > 8:
                continue
            if difflib.SequenceMatcher(None, term_folded, w).ratio() >= 0.72:
                return True
    return False


def _count_relaxed_hits(terms: list[str], assistant_text: str) -> int:
    h = _fold_norm(assistant_text)
    seen: set[str] = set()
    n = 0
    for t in terms:
        tf = _fold_norm(t)
        if tf in seen:
            continue
        seen.add(tf)
        if _relaxed_term_in_haystack(tf, h):
            n += 1
    return n


def _anchor_terms_from_original_assistant(text: str, limit: int = 24) -> list[str]:
    """Termos do assistant original do fonte — âncoras se a curadoria parafrasear sem repetir o enunciado."""
    out: list[str] = []
    seen: set[str] = set()
    for t in re.findall(r"\w+", text.lower()):
        if len(t) < 5 or t in _OVERLAP_STOPWORDS:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _assistant_topic_overlap(user_key: str, assistant_text: str) -> int:
    """Quantas palavras (≥4 letras) do enunciado aparecem no texto do assistant — filtra respostas de outro tema."""
    toks = [t for t in re.findall(r"\w+", user_key.lower()) if len(t) >= 4]
    if not toks:
        toks = [t for t in re.findall(r"\w+", user_key.lower()) if len(t) >= 3]
    low = assistant_text.lower()
    return sum(1 for t in set(toks) if t in low)


def load_ingest_topic_check_mode(config_path: Path | None = None) -> str:
    """strict | relaxed | off — ver chave ingest_topic_check no JSON."""
    p = config_path if config_path is not None else CONFIG_DEFAULT
    if not p.is_file():
        return "relaxed"
    try:
        with open(p, encoding="utf-8") as f:
            m = json.load(f).get("ingest_topic_check", "relaxed")
        return m if m in ("strict", "relaxed", "off") else "relaxed"
    except (json.JSONDecodeError, OSError):
        return "relaxed"


def assert_curated_assistants_match_questions(
    pending_lines: list[str],
    validated_lines: list[str],
    *,
    mode: str = "relaxed",
) -> None:
    """
    Falha se o assistant parecer de outro tema (resposta trocada / captura errada).
    relaxed: enunciado com flexão/acentos/prefixos + âncoras do assistant original do fonte.
    """
    if mode == "off":
        return

    if len(pending_lines) != len(validated_lines):
        raise ValueError("pending e validated devem ter o mesmo tamanho.")

    for i, (pend, val) in enumerate(zip(pending_lines, validated_lines), 1):
        po = json.loads(pend)
        vo = json.loads(val)
        uq = _user_key_from_messages_obj(po)
        asst = _first_assistant_content(vo)
        sig = _significant_question_tokens(uq)
        if not sig:
            continue

        if mode == "strict":
            low = asst.lower()
            hit = sum(1 for t in set(sig) if t in low)
            if hit == 0:
                preview = uq[:120] + ("…" if len(uq) > 120 else "")
                raise ValueError(
                    f"Linha {i}: a resposta parece deslocada do tema da pergunta "
                    f"(nenhum dos termos: {', '.join(sorted(set(sig))[:8])} aparece no assistant). "
                    f"Pergunta: {preview!r} — não removi linhas do fonte; corrija a resposta ou a captura."
                )
            continue

        qhits = _count_relaxed_hits(sig, asst)
        orig_asst = _first_assistant_content(po)
        anchors = _anchor_terms_from_original_assistant(orig_asst)
        ahits = _count_relaxed_hits(anchors, asst) if anchors else 0

        ok = qhits >= 1 or ahits >= 2 or (ahits >= 1 and len(anchors) <= 3)
        if not ok:
            preview = uq[:120] + ("…" if len(uq) > 120 else "")
            raise ValueError(
                f"Linha {i}: a resposta parece deslocada do tema (checagem relaxed: "
                f"0 termos do enunciado e <2 do texto original do fonte). "
                f"Termos tentados no enunciado: {', '.join(sorted(set(sig))[:8])}. "
                f"Pergunta: {preview!r}. "
                f"Isto costuma ser captura de bolha antiga no chat — veja assistant_pick_strategy no config."
            )


def _restore_curated_after_failed_append(
    curated: Path, backup: Path | None, n_appended: int
) -> None:
    if backup is not None and backup.is_file():
        shutil.copy2(backup, curated)
        return
    lines = read_jsonl_lines(curated) if curated.is_file() else []
    if len(lines) >= n_appended:
        write_jsonl_lines(curated, lines[:-n_appended])
    elif curated.is_file():
        curated.write_text("", encoding="utf-8")


def _verify_curated_tail_matches(
    curated: Path, expected_lines: list[str], backup: Path | None
) -> None:
    all_lines = read_jsonl_lines(curated)
    n = len(expected_lines)
    if len(all_lines) < n:
        _restore_curated_after_failed_append(curated, backup, n)
        raise ValueError(
            f"Falha ao verificar {curated.name}: arquivo ficou com menos linhas que o esperado."
        )
    tail = all_lines[-n:]
    for j, (a, b) in enumerate(zip(tail, expected_lines)):
        try:
            if json.loads(a) != json.loads(b):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            _restore_curated_after_failed_append(curated, backup, n)
            raise ValueError(
                f"Conteúdo gravado em {curated.name} não bate com o esperado (linha {j + 1} do lote). "
                "Curado revertido; fonte não foi alterado."
            ) from None


def commit_curated_batch_to_disk(
    pending_lines: list[str],
    validated_lines: list[str],
    source_path: Path,
    curated_path: Path,
    *,
    topic_check_mode: str | None = None,
    topic_check_config_path: Path | None = None,
) -> int:
    """
    1) Checa coerência pergunta↔assistant.
    2) Anexa `validated_lines` ao curado, fsync e relê o tail (byte-a-byte via JSON).
    3) Só então remove o mesmo número de linhas do início do fonte.
    Devolve quantas linhas restam no fonte. Levanta ValueError em qualquer falha (fonte intacto).
    """
    expected = len(pending_lines)
    if len(validated_lines) != expected:
        raise ValueError("Número de linhas validadas difere do lote pendente.")

    tcm = topic_check_mode
    if tcm is None:
        tcm = load_ingest_topic_check_mode(topic_check_config_path)
    assert_curated_assistants_match_questions(
        pending_lines, validated_lines, mode=tcm
    )

    if not source_path.is_file():
        raise ValueError(f"Arquivo fonte não encontrado: {source_path}")

    all_source = read_jsonl_lines(source_path)
    if len(all_source) < expected:
        raise ValueError("Arquivo fonte tem menos linhas que o lote pendente — abortando.")

    head = all_source[:expected]
    if head != pending_lines:
        raise ValueError(
            "As primeiras linhas do fonte não batem com o lote pendente. "
            "Não edite o JSONL manualmente entre preparar e ingerir."
        )

    cur_backup = backup_file(curated_path)
    n_cur_before = len(read_jsonl_lines(curated_path)) if curated_path.is_file() else 0

    try:
        with open(curated_path, "a", encoding="utf-8") as out:
            for line in validated_lines:
                out.write(line + "\n")
            out.flush()
            os.fsync(out.fileno())
    except OSError as e:
        if cur_backup is not None and cur_backup.is_file():
            shutil.copy2(cur_backup, curated_path)
        elif curated_path.is_file():
            lines_now = read_jsonl_lines(curated_path)
            if len(lines_now) > n_cur_before:
                write_jsonl_lines(curated_path, lines_now[:n_cur_before])
        raise ValueError(f"Erro ao gravar {curated_path}: {e}") from e

    _verify_curated_tail_matches(curated_path, validated_lines, cur_backup)

    backup_file(source_path)
    rest = all_source[expected:]
    write_jsonl_lines(source_path, rest)
    return len(rest)


def reorder_response_lines_to_batch(
    batch: list[str], response_lines: list[str]
) -> list[str]:
    """
    Se o modelo repetiu as mesmas perguntas (user) que no lote mas noutra ordem,
    reordena as linhas da resposta para coincidir com o lote. Caso não haja
    correspondência exata para todas as linhas, devolve a lista original.
    """
    if len(batch) != len(response_lines):
        return response_lines

    parsed: list[dict] = []
    for line in response_lines:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            return response_lines

    batch_keys: list[str] = []
    for bl in batch:
        try:
            batch_keys.append(_user_key_from_messages_obj(json.loads(bl)))
        except json.JSONDecodeError:
            return response_lines

    if any(not k for k in batch_keys):
        return response_lines

    pools: dict[str, list[int]] = defaultdict(list)
    for i, o in enumerate(parsed):
        key = _user_key_from_messages_obj(o)
        if key:
            pools[key].append(i)

    new_idx: list[int] = []
    for bk in batch_keys:
        pl = pools.get(bk)
        if not pl:
            return response_lines
        new_idx.append(pl.pop(0))

    if len(set(new_idx)) != len(new_idx):
        return response_lines

    return [response_lines[i] for i in new_idx]


def _collect_valid_message_objects(raw: str) -> list[dict]:
    """Objetos JSON válidos com messages no texto (scan + linhas), sem duplicados exatos."""
    seen: set[str] = set()
    out: list[dict] = []

    def try_add(o: dict) -> None:
        if not isinstance(o, dict):
            return
        try:
            line = json.dumps(o, ensure_ascii=False)
            validate_jsonl_line(line)
        except (TypeError, ValueError):
            return
        if line in seen:
            return
        seen.add(line)
        out.append(o)

    for s in extract_json_objects(raw):
        try:
            try_add(json.loads(s))
        except json.JSONDecodeError:
            continue
    for line in parse_response_lines(raw):
        try:
            try_add(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _pick_best_candidate_index_for_batch_line(
    batch_line: str, pool_indices: list[int], candidates: list[dict]
) -> int:
    """
    Entre vários JSON com a mesma pergunta (eco vs resposta curada vs lixo antigo), prefere:
    1) assistant diferente do original do lote (curadoria real);
    2) maior sobreposição de termos do enunciado no assistant (evita bloco de outro tema);
    3) maior comprimento; 4) índice maior (ligeira preferência por texto mais recente na captura).
    """
    try:
        orig = json.loads(batch_line)
        orig_asst = _first_assistant_content(orig)
        user_key = _user_key_from_messages_obj(orig)
    except (json.JSONDecodeError, TypeError):
        return pool_indices[-1]

    best_i = pool_indices[0]
    best_key = (-1, -1, -1, -1)

    for i in pool_indices:
        asst = _first_assistant_content(candidates[i])
        changed = 1 if asst != orig_asst else 0
        overlap = _assistant_topic_overlap(user_key, asst)
        key = (changed, overlap, len(asst), i)
        if key > best_key:
            best_key = key
            best_i = i
    return best_i


def match_batch_to_response_candidates(
    batch: list[str], candidates: list[dict]
) -> list[str] | None:
    """
    Escolhe `len(batch)` objetos entre candidatos pela pergunta (user) igual à do lote.
    Com duplicados (eco + resposta), escolhe o objeto cujo assistant **não** repete o
    original do fonte quando possível — evita ficar com trecho de outro turno só porque
    era a “última” ocorrência no HTML.
    """
    pools: dict[str, list[int]] = defaultdict(list)
    for i, o in enumerate(candidates):
        k = _user_key_from_messages_obj(o)
        if k:
            pools[k].append(i)

    result_idx: list[int] = []
    for bl in batch:
        try:
            bk = _user_key_from_messages_obj(json.loads(bl))
        except (json.JSONDecodeError, TypeError):
            return None
        if not bk:
            return None
        pl = pools.get(bk, [])
        if not pl:
            return None
        picked = _pick_best_candidate_index_for_batch_line(bl, pl, candidates)
        if picked not in pl:
            return None
        pl.remove(picked)
        result_idx.append(picked)

    if len(set(result_idx)) != len(result_idx):
        return None

    return [json.dumps(candidates[i], ensure_ascii=False) for i in result_idx]


def extract_json_objects(text: str) -> list[str]:
    """
    Extrai objetos com chave 'messages' (LoRA). Ignora sub-objetos '{"role":...}'
    que o scan ingênuo confundia com o envelope completo. Usa json_repair quando o
    modelo deixa aspas não escapadas dentro de content.
    """
    seen: set[str] = set()
    out: list[str] = []
    decoder = json.JSONDecoder()

    def add_obj(obj) -> None:
        if not isinstance(obj, dict) or "messages" not in obj:
            return
        line = json.dumps(obj, ensure_ascii=False)
        if line not in seen:
            seen.add(line)
            out.append(line)

    def scan(s: str) -> None:
        idx = 0
        n = len(s)
        while idx < n:
            while idx < n and s[idx] != "{":
                idx += 1
            if idx >= n:
                break
            try:
                obj, end = decoder.raw_decode(s, idx)
            except json.JSONDecodeError:
                # Modelo costuma quebrar JSON com aspas "curvas" ou " não escapadas em content;
                # raw_decode falha, mas _json_loads_loose (json_repair) recupera o envelope completo.
                blob, endpos = _extract_braced_object_at(s, idx)
                if blob:
                    try:
                        obj = _json_loads_loose(blob)
                    except ValueError:
                        idx += 1
                        continue
                    if isinstance(obj, dict) and "messages" in obj:
                        add_obj(obj)
                        idx = endpos
                        continue
                idx += 1
                continue
            if isinstance(obj, dict) and "messages" not in obj:
                keys = set(obj.keys())
                if keys <= {"role", "content", "name"} and "role" in obj:
                    idx = end
                    continue
            if isinstance(obj, dict) and "messages" in obj:
                add_obj(obj)
            idx = end

    scan(strip_fences(text.strip()))
    for m in re.finditer(
        r"```(?:jsonl|json)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE
    ):
        inner = (m.group(1) or "").strip()
        if inner:
            scan(inner)

    pos = 0
    token = '{"messages"'
    while True:
        j = text.find(token, pos)
        if j == -1:
            break
        blob, endpos = _extract_braced_object_at(text, j)
        pos = j + 1
        if not blob:
            continue
        try:
            obj = _json_loads_loose(blob)
        except ValueError:
            continue
        if isinstance(obj, dict) and "messages" in obj:
            add_obj(obj)
        pos = max(pos, endpos)

    return out


def _match_batch_sliding_windows(
    batch: list[str], candidates: list[dict], expected: int
) -> list[str] | None:
    """
    Se a captura trouxe JSON a mais (ex.: bolha antiga antes do lote atual), tenta
    janelas contíguas de tamanho `expected`, **do fim para o início** (prioridade ao
    bloco mais recente). Só aceita se match_batch_to_response_candidates validar —
    mesmo critério de igualdade de `user` que antes; não relaxa emparelhamento.
    """
    n = len(candidates)
    if n < expected:
        return None
    for start in range(n - expected, -1, -1):
        window = candidates[start : start + expected]
        picked = match_batch_to_response_candidates(batch, window)
        if picked is not None:
            return picked
    return None


def parse_response_for_batch(
    raw: str, expected: int, batch: list[str] | None = None
) -> list[str]:
    """
    Obtém exatamente `expected` objetos JSON da resposta do modelo.
    Prioridade: (1) JSONL, uma linha = um objeto; (2) linhas a mais → janela deslizante;
    (3) scan `{...}`; (4) candidatos com `batch` (janela deslizante se houver extra).
    """
    lines = parse_response_lines(raw)
    if len(lines) == expected:
        normalized: list[str] = []
        for line in lines:
            try:
                obj = validate_jsonl_line(line)
                normalized.append(json.dumps(obj, ensure_ascii=False))
            except ValueError:
                normalized = []
                break
        if normalized:
            return normalized

    if (
        batch is not None
        and len(batch) == expected
        and len(lines) > expected
    ):
        parsed_lines: list[dict] = []
        for line in lines:
            try:
                validate_jsonl_line(line)
                parsed_lines.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                parsed_lines = []
                break
        if len(parsed_lines) == len(lines):
            picked = _match_batch_sliding_windows(batch, parsed_lines, expected)
            if picked is not None:
                return picked

    objs = extract_json_objects(raw)
    if len(objs) >= expected:
        tail = objs[-expected:]
        try:
            for o in tail:
                validate_jsonl_line(o)
            return tail
        except ValueError:
            pass
    if len(objs) == expected:
        return objs

    if batch is not None and len(batch) == expected:
        candidates = _collect_valid_message_objects(raw)
        picked = match_batch_to_response_candidates(batch, candidates)
        if picked is not None:
            return picked
        if len(candidates) > expected:
            picked = _match_batch_sliding_windows(batch, candidates, expected)
            if picked is not None:
                return picked

    raise ValueError(
        f"Esperado {expected} objeto(s) JSON (cada um com 'messages'). "
        f"Encontrados {len(objs)} objeto(s) JSON no texto (scan) e "
        f"{len(lines)} linha(s) não vazia(s). "
        "Se aparecerem objetos a mais, a captura pode incluir mensagem antiga — "
        "o script tenta janelas contíguas e emparelhamento por `user` idêntico ao lote. "
        "Confere last_model_raw.txt; reforça no prompt que cada linha deve repetir o user do lote à letra."
    )


def validate_jsonl_line(line: str) -> dict:
    obj = _json_loads_loose(line)
    if not isinstance(obj, dict) or "messages" not in obj:
        raise ValueError("Objeto deve ter chave 'messages'")
    msgs = obj["messages"]
    if not isinstance(msgs, list) or len(msgs) < 1:
        raise ValueError("'messages' deve ser lista não vazia")
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            raise ValueError("Cada mensagem precisa de role user|assistant")
        if "content" not in m:
            raise ValueError("Cada mensagem precisa de 'content'")
    if not any(isinstance(m, dict) and m.get("role") == "user" for m in msgs):
        raise ValueError("'messages' precisa de pelo menos uma mensagem user")
    if not any(isinstance(m, dict) and m.get("role") == "assistant" for m in msgs):
        raise ValueError("'messages' precisa de pelo menos uma mensagem assistant")
    return obj


def merge_preserved_fields(
    original_line: str, curated_obj: dict, fields: list[str]
) -> dict:
    """Recoloca campos de topo do JSON original se o modelo os omitiu (ex.: conversation_id)."""
    try:
        orig = json.loads(original_line)
    except json.JSONDecodeError:
        return curated_obj
    if not isinstance(orig, dict):
        return curated_obj
    out = dict(curated_obj)
    for f in fields:
        if f not in out and f in orig:
            out[f] = orig[f]
    return out


def snap_user_messages_from_original(original_line: str, curated_obj: dict) -> dict:
    """
    Garante que os textos 'user' são os do lote enviado; só o 'assistant' vem do modelo.
    Emparelha por ordem: 1.ª pergunta do lote ↔ 1.ª resposta assistant na resposta, etc.
    """
    try:
        orig = json.loads(original_line)
    except json.JSONDecodeError:
        return curated_obj
    if not isinstance(orig, dict) or "messages" not in orig:
        return curated_obj
    omsgs = orig["messages"]
    cmsgs = curated_obj.get("messages")
    if not isinstance(omsgs, list) or not isinstance(cmsgs, list):
        return curated_obj

    users_o = [
        m
        for m in omsgs
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    asst_c = [
        m
        for m in cmsgs
        if isinstance(m, dict) and m.get("role") == "assistant"
    ]

    if len(users_o) != len(asst_c):
        raise ValueError(
            f"Perguntas (user) no lote: {len(users_o)}; respostas assistant no modelo: "
            f"{len(asst_c)} — devem ser iguais por linha. Verifique a resposta do DeepSeek."
        )

    new_msgs: list[dict] = []
    for u, cm in zip(users_o, asst_c):
        new_msgs.append({"role": "user", "content": u.get("content", "")})
        new_msgs.append({"role": "assistant", "content": cm.get("content", "")})

    out = dict(curated_obj)
    out["messages"] = new_msgs
    for k, v in orig.items():
        if k != "messages" and k not in out:
            out[k] = v
    return out


def cmd_reset(
    restore_from: Path | None,
    clear_curated: bool,
    assume_yes: bool,
    config_path: Path | None,
) -> None:
    """
    Repõe o fonte a partir de um .bak e/ou limpa o curado, com cópias de segurança com data.
    Remove ficheiros residuais do antigo modo manual, se existirem.
    """
    src, cur = resolve_source_curated_paths(config_path)

    if not restore_from and not clear_curated:
        raise SystemExit(
            "Use pelo menos uma opção:\n"
            "  --restore-source FICHEIRO.bak  → copia para o fonte (ex.: data/select/cartas_de_cristo.jsonl.bak)\n"
            "  --clear-curated                 → esvazia o curado (backup antes)\n"
            "Exemplo para recomeçar tudo:\n"
            f"  python curadoria_batch.py reset --restore-source {src.with_name(src.name + '.bak').relative_to(DIR)} --clear-curated -y"
        )

    if restore_from is not None:
        rf = restore_from if restore_from.is_absolute() else (DIR / restore_from)
        if not rf.is_file():
            raise SystemExit(f"Ficheiro para repor fonte não encontrado: {rf}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("Fonte:", src)
    print("Curado:", cur)
    if restore_from:
        print("Repor fonte desde:", rf)
    if clear_curated:
        print("Curado será esvaziado (com backup .reset_" + ts + ").")

    if not assume_yes:
        confirm = input("Escreva RESET para confirmar: ").strip()
        if confirm != "RESET":
            raise SystemExit("Cancelado.")

    if restore_from:
        if src.is_file():
            snap = src.with_name(f"{src.name}.before_reset_{ts}.bak")
            shutil.copy2(src, snap)
            print(f"Backup do fonte atual: {snap.name}")
        shutil.copy2(rf, src)
        print(f"OK: fonte reposto desde {rf.name}")

    if clear_curated:
        if cur.is_file():
            snap = cur.with_name(f"{cur.stem}_before_reset_{ts}{cur.suffix}")
            shutil.copy2(cur, snap)
            print(f"Backup do curado: {snap.name}")
            cur.write_text("", encoding="utf-8")
        else:
            cur.write_text("", encoding="utf-8")
        print(f"OK: curado esvaziado ({cur.name})")

    for stale in _STALE_MANUAL:
        if stale.is_file():
            stale.unlink()
            print(f"Removido: {stale.name}")

    print("\nPróximo passo: python curadoria_playwright.py")


def main() -> None:
    p = argparse.ArgumentParser(
        description="Utilitários da curadoria JSONL. Fluxo principal: curadoria_playwright.py"
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_rst = sub.add_parser(
        "reset",
        help="Repor fonte (.bak) e/ou limpar curado para recomeçar a curadoria do zero",
    )
    p_rst.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            f"JSON com opções (ingest_topic_check, etc.); fonte/curado vêm de SOURCE/CURATED "
            f"em curadoria_batch.py (default config: {CONFIG_DEFAULT.name})"
        ),
    )
    p_rst.add_argument(
        "--restore-source",
        type=Path,
        default=None,
        metavar="FICHEIRO",
        help="Copia para o ficheiro SOURCE em curadoria_batch.py (ex.: …/cartas_de_cristo.jsonl.bak)",
    )
    p_rst.add_argument(
        "--clear-curated",
        action="store_true",
        help="Esvazia o ficheiro curado (guarda backup com timestamp)",
    )
    p_rst.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Confirmar sem prompt (RESET)",
    )

    args = p.parse_args()
    if args.command == "reset":
        cmd_reset(
            args.restore_source,
            args.clear_curated,
            args.yes,
            args.config,
        )


if __name__ == "__main__":
    main()
