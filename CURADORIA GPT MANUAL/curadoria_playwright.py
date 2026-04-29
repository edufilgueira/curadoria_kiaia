#!/usr/bin/env python3
"""
Curadoria automática via browser (Playwright) — DeepSeek Chat.
Projeto: CURADORIA GPT MANUAL (SOURCE/CURATED definidos em curadoria_batch.py; curado típico:
data/exports/base_de_conhecimento/dataset_pergunta_resposta.jsonl).

Lê lotes do ficheiro de seleção, envia ao DeepSeek conforme prompt_curadoria.txt,
valida a resposta e anexa linhas JSONL ao dataset de exportação (removendo as linhas
processadas do início do ficheiro fonte).

Primeira execução: abre o Chromium com perfil persistente, você faz login,
pressiona Enter no terminal e o script processa lotes.

Configuração: edite curadoria_config.json (batch_size, arquivos, prompt_file, seletores CSS).

Dependências:
  pip install playwright
  playwright install chromium

Uso:
  python curadoria_playwright.py
  python curadoria_playwright.py --config outro_config.json
  python curadoria_playwright.py --batch-size 3 --batches 1
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent

# Reutiliza validação / parse do fluxo manual
from curadoria_batch import (
    CURATED,
    SOURCE,
    build_curator_prompt_block,
    commit_curated_batch_to_disk,
    extract_json_objects,
    merge_preserved_fields,
    parse_response_for_batch,
    read_jsonl_lines,
    reorder_response_lines_to_batch,
    snap_user_messages_from_original,
    validate_jsonl_line,
)


def load_json_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_chat_url(url: str) -> str:
    """Evita URLs inválidas por esquema duplicado (ex.: https://https://...) ou https// sem ':'."""
    u = (url or "").strip()
    if not u:
        return "https://chat.deepseek.com/"
    while "https://https://" in u:
        u = u.replace("https://https://", "https://", 1)
    while "http://http://" in u:
        u = u.replace("http://http://", "http://", 1)
    if u.startswith("https//") and not u.startswith("https://"):
        u = "https://" + u[len("https//") :]
    if u.startswith("http//") and not u.startswith("http://"):
        u = "http://" + u[len("http//") :]
    return u


def sleep_between_batches(cfg: dict) -> None:
    """
    Espera entre lotes. Se existir delay_between_batches_random_seconds [min, max] no JSON,
    usa tempo aleatório nesse intervalo (segundos); senão usa delay_between_batches_seconds fixo.
    """
    raw = cfg.get("delay_between_batches_random_seconds")
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        try:
            lo, hi = float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            pass
        else:
            if hi < lo:
                lo, hi = hi, lo
            delay = random.uniform(lo, hi)
            print(
                f"Pausa aleatória: {delay:.1f}s (entre {lo:g}s e {hi:g}s) antes do próximo lote."
            )
            time.sleep(delay)
            return
    delay = float(cfg.get("delay_between_batches_seconds", 2))
    print(f"Pausa: {delay:.1f}s antes do próximo lote.")
    time.sleep(delay)


def load_prompt_text(prompt_path: Path) -> str:
    if not prompt_path.is_file():
        raise SystemExit(f"Arquivo de prompt não encontrado: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def pick_locator(page, selectors: list[str]):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=8000)
            return loc, sel
        except Exception:
            continue
    return None, None


def send_message(page, input_el, cfg: dict) -> None:
    if cfg.get("use_enter_to_send", True):
        combo = cfg.get("send_key_combination", "Enter")
        input_el.press(combo)
        return
    for sel in cfg.get("send_selectors", []):
        btn = page.locator(sel).first
        if btn.count() and btn.is_visible():
            btn.click()
            return
    input_el.press("Enter")


def count_curated_json_objects(text: str) -> int:
    """Quantos objetos JSON válidos com 'messages' existem no texto (ignora prosa)."""
    n = 0
    for raw_obj in extract_json_objects(text):
        try:
            validate_jsonl_line(raw_obj)
            n += 1
        except ValueError:
            continue
    return n


def locator_text_for_capture(loc, cfg: dict) -> str:
    if cfg.get("assistant_use_inner_text", False):
        return loc.inner_text(timeout=2000)
    try:
        t = loc.text_content(timeout=2000)
        if t and t.strip():
            return t
    except Exception:
        pass
    return loc.inner_text(timeout=2000)


def collect_message_candidates(
    page,
    selectors: list[str],
    *,
    merge_all_selectors: bool = False,
    cfg: dict | None = None,
) -> list[str]:
    cfg = cfg or {}
    if merge_all_selectors:
        seen: set[str] = set()
        out_all: list[str] = []
        for sel in selectors:
            loc = page.locator(sel)
            try:
                n = loc.count()
            except Exception:
                continue
            for i in range(n):
                try:
                    txt = locator_text_for_capture(loc.nth(i), cfg)
                except Exception:
                    continue
                t = txt.strip()
                if not t or t in seen:
                    continue
                seen.add(t)
                out_all.append(t)
        return out_all

    for sel in selectors:
        loc = page.locator(sel)
        try:
            n = loc.count()
        except Exception:
            continue
        seen: set[str] = set()
        out: list[str] = []
        for i in range(n):
            try:
                txt = locator_text_for_capture(loc.nth(i), cfg)
            except Exception:
                continue
            t = txt.strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)
        if out:
            return out
    return []


def collect_best_message_candidates(
    page,
    selectors: list[str],
    cfg: dict,
    expected_json_objects: int | None,
    *,
    merge_all_selectors: bool,
) -> list[str]:
    if merge_all_selectors:
        return collect_message_candidates(
            page, selectors, merge_all_selectors=True, cfg=cfg
        )

    best_list: list[str] = []
    best_score = -1
    need = int(expected_json_objects or 0)

    for sel in selectors:
        loc = page.locator(sel)
        try:
            n = loc.count()
        except Exception:
            continue
        if n == 0:
            continue
        seen: set[str] = set()
        out: list[str] = []
        for i in range(n):
            try:
                txt = locator_text_for_capture(loc.nth(i), cfg)
            except Exception:
                continue
            t = txt.strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)
        if not out:
            continue
        pick = pick_assistant_text(out, cfg, expected_json_objects)
        score = count_curated_json_objects(pick)
        if score > best_score:
            best_score = score
            best_list = out
        if need > 0 and score >= need:
            return out

    if not best_list:
        return collect_message_candidates(
            page, selectors, merge_all_selectors=False, cfg=cfg
        )
    return best_list


def scroll_chat_to_bottom(page) -> None:
    try:
        page.evaluate(
            """() => {
                window.scrollTo(0, document.body.scrollHeight);
                for (const e of document.querySelectorAll(
                    '[class*="scroll"], [style*="overflow"]'
                )) {
                    try { e.scrollTop = e.scrollHeight; } catch (err) {}
                }
            }"""
        )
    except Exception:
        pass


def dom_fallback_markdown_nodes(page, tail_nodes: int) -> str:
    js = """(tailN) => {
                const sel = [
                    '.ds-markdown',
                    '[class*="ds-markdown"]',
                    '[class*="markdown--block"]',
                    '[class*="Markdown"]',
                    'pre',
                ].join(',');
                const nodes = Array.from(document.querySelectorAll(sel));
                const slice = nodes.slice(-tailN);
                const out = [];
                const seen = new Set();
                for (const n of slice) {
                    const t = (n.innerText || n.textContent || '').trim();
                    if (t.length < 2 || seen.has(t)) continue;
                    seen.add(t);
                    out.push(t);
                }
                return out.join('\\n\\n');
            }"""
    best = ""
    for fr in page.frames:
        try:
            chunk = fr.evaluate(js, tail_nodes)
            if chunk and len(chunk) > len(best):
                best = chunk
        except Exception:
            continue
    return best


def dom_fallback_main_tail(page, max_chars: int) -> str:
    js = """(maxChars) => {
                const pick =
                    document.querySelector('main')
                    || document.querySelector('[class*="scroll-area"]')
                    || document.querySelector('[class*="conversation"]')
                    || document.querySelector('article')
                    || document.body;
                const t = (pick && (pick.innerText || pick.textContent || '')) || '';
                const s = String(t).replace(/\\r\\n/g, '\\n');
                return s.length <= maxChars ? s : s.slice(-maxChars);
            }"""
    best = ""
    for fr in page.frames:
        try:
            chunk = fr.evaluate(js, max_chars)
            if chunk and len(chunk) > len(best):
                best = chunk
        except Exception:
            continue
    return best


def augment_capture_text(
    page, cfg: dict, primary: str, expected_json_objects: int | None
) -> str:
    if not cfg.get("assistant_dom_fallback", True):
        return (primary or "").strip()

    need = int(expected_json_objects or 0)
    cur = (primary or "").strip()
    if need > 0 and count_curated_json_objects(cur) >= need:
        return cur

    scroll_chat_to_bottom(page)
    time.sleep(float(cfg.get("assistant_dom_fallback_after_scroll_ms", 250)) / 1000.0)

    tail_nodes = int(cfg.get("assistant_dom_fallback_tail_nodes", 48))
    max_chars = int(cfg.get("assistant_dom_fallback_max_chars", 120000))
    node_blob = dom_fallback_markdown_nodes(page, tail_nodes)
    tail_blob = dom_fallback_main_tail(page, max_chars)

    candidates: list[str] = [cur, node_blob, tail_blob]
    if node_blob and tail_blob:
        candidates.append(f"{node_blob}\n\n{tail_blob}")
    if cur:
        for extra in (node_blob, tail_blob):
            if extra:
                candidates.append(f"{cur}\n\n{extra}")
        if node_blob and tail_blob:
            candidates.append(f"{cur}\n\n{node_blob}\n\n{tail_blob}")

    best = cur
    best_n = count_curated_json_objects(best)
    for c in candidates:
        s = (c or "").strip()
        if not s:
            continue
        n = count_curated_json_objects(s)
        if n > best_n:
            best_n = n
            best = s
        if need > 0 and n >= need:
            return s
    return best.strip()


def pick_assistant_text(
    candidates: list[str], cfg: dict, expected_json_objects: int | None = None
) -> str:
    """
    Por omissão usa só as últimas bolhas do assistente (evita fundir todo o histórico do chat,
    o que misturava JSON de lotes antigos com o lote atual e desalinhava pergunta/resposta).
    merge_all = comportamento antigo perigoso (junta todas as .ds-markdown).
    """
    if not candidates:
        return ""
    strategy = cfg.get("assistant_pick_strategy", "last_sufficient")
    need = expected_json_objects if expected_json_objects is not None else 0

    if strategy == "last":
        return candidates[-1]

    if strategy == "merge_all":
        merged = "\n".join(candidates)
        merged_n = count_curated_json_objects(merged)
        scored = [(count_curated_json_objects(c), len(c), c) for c in candidates]
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        best_n, _, best_text = scored[0]
        if merged_n > best_n:
            return merged
        if best_n > 0:
            return best_text
        if merged_n > 0:
            return merged
        return max(candidates, key=len)

    # last_sufficient (default): funde o sufixo das últimas k bolhas até haver JSON suficiente.
    # Com need>0, k precisa poder chegar a ~need (ou mais): o DeepSeek costuma emitir 1 linha JSON
    # por bolha; o antigo teto de 3 impedia ver 5+ objetos e o wait ficava preso até o timeout.
    if need <= 0:
        max_k = min(3, len(candidates))
    else:
        max_k = min(len(candidates), need + 12)
    for k in range(1, max_k + 1):
        tail = candidates[-k:]
        merged = "\n".join(tail)
        nobj = count_curated_json_objects(merged)
        if need <= 0:
            if nobj > 0:
                return merged
        elif nobj >= need:
            return merged
    merged_all = "\n".join(candidates)
    n_all = count_curated_json_objects(merged_all)
    if need <= 0 and n_all > 0:
        return merged_all
    if need > 0 and n_all >= need:
        return merged_all
    # Nunca devolver só a última bolha: no DeepSeek ela costuma ser texto de fecho sem JSON.
    return "\n".join(candidates[-max_k:])


def wait_stable_response_text(
    page, cfg: dict, expected_json_objects: int | None = None
) -> str:
    selectors = cfg.get("assistant_message_selectors") or [".ds-markdown"]
    stable = float(cfg.get("stable_seconds", 3))
    timeout = float(cfg.get("max_response_wait_seconds", 180))
    deadline = time.time() + timeout
    started = time.time()
    progress_every = float(cfg.get("wait_progress_log_seconds", 15))

    last = None
    stable_since = None
    last_progress_log = started

    merge_sel = cfg.get("assistant_pick_strategy") == "merge_all" or cfg.get(
        "assistant_collect_all_selectors", False
    )
    use_best = cfg.get("assistant_pick_best_selector", True)

    while time.time() < deadline:
        if use_best and not merge_sel:
            candidates = collect_best_message_candidates(
                page,
                selectors,
                cfg,
                expected_json_objects,
                merge_all_selectors=False,
            )
        else:
            candidates = collect_message_candidates(
                page, selectors, merge_all_selectors=bool(merge_sel), cfg=cfg
            )
        text = pick_assistant_text(candidates, cfg, expected_json_objects)
        text = augment_capture_text(page, cfg, text, expected_json_objects)

        if progress_every > 0 and (time.time() - last_progress_log) >= progress_every:
            last_progress_log = time.time()
            need = expected_json_objects if expected_json_objects is not None else 0
            ok = count_curated_json_objects(text) if text else 0
            raw_objs = len(extract_json_objects(text)) if text else 0
            elapsed = int(time.time() - started)
            print(
                f"  … ainda aguardando resposta ({elapsed}s / {int(timeout)}s) — "
                f"JSON válidos na captura: {ok}"
                + (f" / mínimo esperado: {need}" if need else "")
                + f"; envelopes messages no texto: {raw_objs}"
                + f"; bolhas seletor: {len(candidates)}",
                flush=True,
            )
            if need > 0 and ok == 0 and text:
                try:
                    (DIR / "last_capture_probe.txt").write_text(
                        f"valid={ok} raw_objs={raw_objs} chars={len(text)}\n\n{text[:20000]}",
                        encoding="utf-8",
                    )
                except OSError:
                    pass

        if text != last:
            last = text
            stable_since = time.time()
        elif text.strip() and stable_since and (time.time() - stable_since) >= stable:
            need = expected_json_objects if expected_json_objects is not None else 0
            ok = count_curated_json_objects(text)
            if need <= 0 or ok >= need:
                return text.strip()
            # Texto estável mas ainda sem JSON suficiente (ex.: só "regras" no início) — espera mais.

        time.sleep(0.35)

    need = expected_json_objects if expected_json_objects is not None else 0
    final = (last or "").strip()
    final = augment_capture_text(page, cfg, final, expected_json_objects)
    if need <= 0 or count_curated_json_objects(final) >= need:
        return final.strip()

    if need > 0 and count_curated_json_objects(final) < need:
        dbg = DIR / "last_capture_debug.txt"
        try:
            dbg.write_text(
                f"(última captura, {len(final)} caracteres)\n\n{final}",
                encoding="utf-8",
            )
        except OSError:
            pass
        raise RuntimeError(
            f"Tempo esgotado ({int(timeout)}s) com só "
            f"{count_curated_json_objects(final)} objeto(s) JSON válido(s) (precisa {need}). "
            "Veja last_capture_debug.txt e last_capture_probe.txt. "
            "Instale json_repair: pip install json_repair (corrige aspas no JSON do modelo)."
        )


def process_batch(
    batch: list[str],
    prompt: str,
    page,
    cfg: dict,
) -> str:
    block = build_curator_prompt_block(prompt, batch)

    inp, used_sel = pick_locator(page, cfg.get("input_selectors") or ["textarea"])
    if inp is None:
        raise RuntimeError(
            "Não achei campo de texto. Ajuste input_selectors em curadoria_config.json "
            "(Inspecionar elemento no DeepSeek → copiar seletor)."
        )

    print(
        f"  Campo: {used_sel!r} — enviando lote e aguardando resposta do modelo…",
        flush=True,
    )
    inp.click()
    inp.fill("")
    inp.fill(block)
    time.sleep(0.2)
    send_message(page, inp, cfg)

    raw = wait_stable_response_text(page, cfg, expected_json_objects=len(batch))
    if not raw or len(raw) < 20:
        raise RuntimeError(
            "Resposta vazia ou muito curta. Ajuste assistant_message_selectors ou "
            "stable_seconds / max_response_wait_seconds."
        )
    njson = count_curated_json_objects(raw)
    if njson < len(batch):
        (DIR / "last_model_raw.txt").write_text(raw, encoding="utf-8")
        raise RuntimeError(
            f"Resposta sem JSON suficiente para o lote ({njson} válido(s), precisa {len(batch)}). "
            "Captura gravada em last_model_raw.txt."
        )
    return raw


def apply_curated_to_files(
    batch: list[str],
    response_text: str,
    source_path: Path,
    curated_path: Path,
    preserve_fields: list[str],
    topic_check_config_path: Path | None = None,
) -> None:
    try:
        lines = parse_response_for_batch(response_text, len(batch), batch)
        lines = reorder_response_lines_to_batch(batch, lines)
    except ValueError as e:
        raise ValueError(str(e)) from e

    validated: list[str] = []
    for i, line in enumerate(lines, 1):
        try:
            validate_jsonl_line(line)
            obj = json.loads(line)
            obj = snap_user_messages_from_original(batch[i - 1], obj)
            obj = merge_preserved_fields(batch[i - 1], obj, preserve_fields)
            validated.append(json.dumps(obj, ensure_ascii=False))
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Linha {i} inválida: {e}") from e

    commit_curated_batch_to_disk(
        batch,
        validated,
        source_path,
        curated_path,
        topic_check_config_path=topic_check_config_path,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Curadoria DeepSeek via Playwright.")
    ap.add_argument(
        "--config",
        type=Path,
        default=DIR / "curadoria_config.json",
        help="JSON de configuração",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Sobrescreve batch_size do config",
    )
    ap.add_argument(
        "--batches",
        type=int,
        default=None,
        help="Máximo de lotes (sobrescreve max_batches do config). Omitir = usar config ou até esvaziar o fonte",
    )
    ap.add_argument(
        "--skip-login-wait",
        action="store_true",
        help="Não pausar para login (útil se já estiver logado no perfil)",
    )
    ap.add_argument(
        "--cdp-url",
        type=str,
        default=None,
        help="Ex.: http://127.0.0.1:9222 — conecta ao Chrome já aberto (login com Google funciona). Sobrescreve connect_cdp_url do JSON.",
    )
    args = ap.parse_args()

    cfg_path = args.config
    if not cfg_path.is_file():
        raise SystemExit(f"Config não encontrado: {cfg_path}")

    cfg = load_json_config(cfg_path)
    batch_size = args.batch_size if args.batch_size is not None else int(cfg.get("batch_size", 5))

    source_path = SOURCE
    curated_path = CURATED
    curated_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path = DIR / cfg["prompt_file"]
    user_data = DIR / cfg.get("user_data_dir", ".playwright_padrao_sintetica_profile")
    chat_url = normalize_chat_url(str(cfg.get("chat_url", "https://chat.deepseek.com/")))

    if not source_path.is_file():
        jsonl_here = sorted(DIR.glob("*.jsonl")) + sorted(DIR.glob("data/**/*.jsonl"))
        hint = ""
        if jsonl_here:
            hint = "\n  Arquivos .jsonl encontrados:\n    " + "\n    ".join(
                str(p.relative_to(DIR)) for p in jsonl_here
            )
            hint += (
                "\n  Ajuste SOURCE em curadoria_batch.py (linhas SOURCE / CURATED)."
            )
        raise SystemExit(f"Fonte não encontrada: {source_path}{hint}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Instale: pip install playwright && playwright install chromium"
        ) from None

    prompt = load_prompt_text(prompt_path)
    preserve = list(cfg.get("preserve_fields", []))

    cdp_url = args.cdp_url or cfg.get("connect_cdp_url")
    if isinstance(cdp_url, str) and not cdp_url.strip():
        cdp_url = None

    if not cdp_url:
        user_data.mkdir(parents=True, exist_ok=True)

    # Limite de lotes: CLI --batches tem prioridade; senão usa max_batches do JSON (null = sem limite).
    max_batches = args.batches
    if max_batches is None:
        mb = cfg.get("max_batches")
        if mb is not None:
            max_batches = int(mb)
    batches_done = 0

    with sync_playwright() as p:
        browser_cdp = None
        if cdp_url:
            # Usa o Chrome/Chromium que você abriu com --remote-debugging-port (login Google funciona).
            print(f"Conectando via CDP em {cdp_url} ...")
            browser_cdp = p.chromium.connect_over_cdp(cdp_url)
            if not browser_cdp.contexts:
                raise SystemExit("Nenhum contexto no browser CDP — abra uma janela no Chrome.")
            context = browser_cdp.contexts[0]
            if context.pages:
                page = context.pages[0]
                page.bring_to_front()
            else:
                page = context.new_page()
        else:
            # Chromium empacotado pelo Playwright (playwright install chromium), não o Chrome do SO.
            extra_args = list(cfg.get("chromium_args") or [])
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data),
                headless=False,
                locale="pt-BR",
                args=extra_args,
            )
            page = context.pages[0] if context.pages else context.new_page()

        page.goto(chat_url, wait_until="domcontentloaded")

        if not args.skip_login_wait:
            if cdp_url:
                print(
                    "\n>>> No Chrome conectado: abra o DeepSeek, faça login (Google ok) e deixe o chat pronto.\n"
                    ">>> Depois volte aqui e pressione ENTER para começar os lotes.\n"
                )
            else:
                print(
                    "\n>>> Dica: login com Google costuma FALHAR neste Chromium automático.\n"
                    ">>> Use e-mail/senha no DeepSeek ou rode o Chrome com CDP (veja README).\n"
                    "\n>>> Faça login no DeepSeek (se precisar) e deixe o chat aberto.\n"
                    ">>> Depois volte aqui e pressione ENTER para começar os lotes.\n"
                )
            try:
                input()
            except EOFError:
                pass

        while True:
            all_lines = read_jsonl_lines(source_path)
            if not all_lines:
                print("Fonte vazio — nada a processar.")
                break

            batch = all_lines[:batch_size]
            print(f"\n--- Lote: {len(batch)} linha(s) | restantes no fonte: {len(all_lines)} ---")

            try:
                raw = process_batch(batch, prompt, page, cfg)
            except Exception as e:
                print(f"ERRO no envio/leitura: {e}", file=sys.stderr)
                Path(DIR / "last_error_response.txt").write_text(
                    str(e), encoding="utf-8"
                )
                try:
                    page.screenshot(path=str(DIR / "last_error.png"), full_page=True)
                except Exception:
                    pass
                raise

            try:
                apply_curated_to_files(
                    batch,
                    raw,
                    source_path,
                    curated_path,
                    preserve,
                    topic_check_config_path=cfg_path,
                )
            except ValueError as e:
                print(f"ERRO na validação JSON: {e}", file=sys.stderr)
                Path(DIR / "last_model_raw.txt").write_text(raw, encoding="utf-8")
                print(
                    f"Resposta bruta salva em last_model_raw.txt — ajuste o prompt ou corrija manualmente."
                )
                raise SystemExit(1) from e

            batches_done += 1
            print(f"OK → anexado em {curated_path.name}; {len(batch)} linhas removidas do fonte.")

            if max_batches is not None and batches_done >= max_batches:
                print(f"Limite de lotes ({max_batches}) atingido (--batches ou max_batches no config).")
                break

            if not read_jsonl_lines(source_path):
                break
            sleep_between_batches(cfg)

        if browser_cdp is not None:
            browser_cdp.close()
        else:
            context.close()

    print(f"\nConcluído. Lotes nesta execução: {batches_done}")


if __name__ == "__main__":
    main()
