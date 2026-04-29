#!/usr/bin/env python3
"""
Percorre data/exports recursivamente (todos os .jsonl, em qualquer subpasta).
Grupos editoriais (prefixos de pasta): livros/, mensagens_biblicas/,
leituras_de_campo/, base_de_conhecimento/, sinteticos/, registros/.

Por cada linha JSONL lê-se um objeto com ``messages``. Cada **par consecutivo**
``user`` + ``assistant`` conta como **uma unidade de dataset** (um turno).
Vários pares na mesma linha geram várias unidades, cada uma com tokens e
classificação (Curta/Média/Longa) pelo **assistant** daquele par.

Tokens: tiktoken cl100k_base. ``user`` e ``assistant`` somados por turno;
totais globais somam todos os turnos.

O relatório **não** atualiza sozinho: após editar datasets, volte a executar este script.
Grava data/estatistico/tokens_por_linha.jsonl (um registo por **turno**, não por linha).
``relatorio_distribuicao_token.txt`` e ``relatorio_proporcoes_grupos.txt``: cada execução
**coloca a nova leitura no topo**; o conteúdo anterior é mantido abaixo (histórico).

Uso:
  python exportacao_estatisticas_tokens.py
  python exportacao_estatisticas_tokens.py --exports data/exports --out data/estatistico
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).resolve().parent
DEFAULT_EXPORTS = DIR / "data" / "exports"
DEFAULT_OUT = DIR / "data" / "estatistico"

# Metas sugeridas (assistant)
META = {
    "curta": 35.0,
    "media": 30.0,
    "longa": 30.0,
    "muito_longa": 5.0,
}

# Proporção de ITENS (segmentos) por grupo editorial — % alvo fixo do total (soma 100%).
# Ajuste aqui se a estratégia editorial mudar.
GRUPO_META_PCT: dict[str, float] = {
    "livros": 30.0,
    "mensagens_biblicas": 14.0,
    "leituras": 10.0,
    "base_conhecimento": 22.0,
    "sinteticos": 10.0,
    "registros": 14.0,
}

GRUPO_LABEL = {
    "livros": "Livros",
    "mensagens_biblicas": "Mensagens Bíblicas",
    "leituras": "Leituras",
    "base_conhecimento": "Base de Conhecimento",
    "sinteticos": "Sintéticos",
    "registros": "Registros",
    "nao_classificado": "Não classificado",
}

GRUPO_ORDEM = [
    "livros",
    "mensagens_biblicas",
    "leituras",
    "base_conhecimento",
    "sinteticos",
    "registros",
    "nao_classificado",
]


def grupo_por_caminho(rel_name: str) -> str:
    """
    Classifica pelo primeiro nível de pasta sob data/exports.
    Ordem de teste: mais específico / novo layout antes de genéricos se necessário.
    """
    r = rel_name.replace("\\", "/")
    if r.startswith("livros/"):
        return "livros"
    if r.startswith("mensagens_biblicas/"):
        return "mensagens_biblicas"
    if r.startswith("leituras_de_campo/"):
        return "leituras"
    if r.startswith("base_de_conhecimento/"):
        return "base_conhecimento"
    if r.startswith("sinteticos/"):
        return "sinteticos"
    if r.startswith("registros/"):
        return "registros"
    return "nao_classificado"


def segunda_subpasta(rel_name: str, raiz: str) -> str | None:
    """
    Nome da primeira subpasta sob ``raiz/`` (2.º nível).
    Ex.: ``livros/cartas_de_cristo/dataset.jsonl`` → ``cartas_de_cristo``.
    Se o ``.jsonl`` estiver directamente sob ``raiz/``, devolve None.
    """
    r = rel_name.replace("\\", "/")
    pref = raiz + "/"
    if not r.startswith(pref):
        return None
    tail = r[len(pref) :].strip("/")
    if not tail:
        return None
    parts = tail.split("/")
    if len(parts) >= 2:
        return parts[0]
    only = parts[0]
    return None if "." in only else only


SEP_HISTORICO = "=" * 76


def escrever_relatorio_com_historico(path: Path, conteudo_novo: str) -> None:
    """
    Grava ``conteudo_novo`` no topo do ficheiro. Se já existir texto anterior
    não vazio, mantém-o abaixo de um separador (para comparar leituras).
    """
    conteudo_novo = conteudo_novo.rstrip() + "\n"
    if path.exists():
        anterior = path.read_text(encoding="utf-8")
        if anterior.strip():
            texto = (
                conteudo_novo
                + "\n"
                + SEP_HISTORICO
                + "\n"
                "Leitura anterior (histórico; preservada ao voltar a executar o script)\n"
                + SEP_HISTORICO
                + "\n\n"
                + anterior.lstrip()
            )
        else:
            texto = conteudo_novo
    else:
        texto = conteudo_novo
    path.write_text(texto, encoding="utf-8")


def _delta_meta(pct: float, meta: float) -> str:
    d = pct - meta
    if abs(d) < 0.05:
        return "no alvo"
    if d > 0:
        return f"+{d:.1f} pp acima da meta"
    return f"{d:.1f} pp abaixo da meta"


def _get_encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except ImportError as e:
        raise SystemExit(
            "Instale tiktoken: pip install tiktoken\n"
            "Usamos o encoding cl100k_base (compatível com análise de datasets estilo GPT-4)."
        ) from e


def json_loads_loose(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import json_repair

            return json_repair.loads(raw)
        except ImportError:
            print(
                "Aviso: JSON inválido e json_repair ausente. pip install json_repair",
                file=sys.stderr,
            )
            raise
        except Exception:
            raise


def count_tokens(text: str, enc) -> int:
    if not text or not isinstance(text, str):
        return 0
    return len(enc.encode(text))


def _message_content(m: dict) -> str:
    c = m.get("content")
    if not isinstance(c, str):
        return str(c or "")
    return c


def turn_token_pairs(messages: list, enc) -> list[tuple[int, int]]:
    """
    Percorre ``messages`` em ordem e extrai pares consecutivos user → assistant.
    Cada par é um turno: devolve lista de (tokens_user, tokens_assistant).
    Mensagens órfãs (sem par user+assistant adjacente) são ignoradas.
    """
    if not messages:
        return []
    pairs: list[tuple[int, int]] = []
    i = 0
    n = len(messages)
    while i + 1 < n:
        m0 = messages[i]
        m1 = messages[i + 1]
        if not isinstance(m0, dict) or not isinstance(m1, dict):
            i += 1
            continue
        if m0.get("role") == "user" and m1.get("role") == "assistant":
            u = count_tokens(_message_content(m0), enc)
            a = count_tokens(_message_content(m1), enc)
            pairs.append((u, a))
            i += 2
        else:
            i += 1
    return pairs


def classify_assistant(t: int) -> str:
    """Faixas da tabela (tokens do assistant num turno user+assistant)."""
    if t < 80:
        return "abaixo_80"
    if t <= 200:
        return "curta"
    if t <= 500:
        return "media"
    if t <= 800:
        return "longa"
    return "muito_longa"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--exports",
        type=Path,
        default=DEFAULT_EXPORTS,
        help="Pasta raiz: todos os .jsonl são lidos recursivamente (subpastas incluídas)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Pasta de saída (criada se não existir)",
    )
    args = ap.parse_args()

    exports_dir: Path = args.exports
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    jsonl_files = sorted(exports_dir.rglob("*.jsonl"))
    if not jsonl_files:
        raise SystemExit(
            f"Nenhum .jsonl (recursivo) em: {exports_dir.resolve()}"
        )

    enc = _get_encoder()
    per_line_path = out_dir / "tokens_por_linha.jsonl"
    report_path = out_dir / "relatorio_distribuicao_token.txt"
    proporcoes_path = out_dir / "relatorio_proporcoes_grupos.txt"

    class_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    sub_livros: Counter[str] = Counter()
    sub_registros: Counter[str] = Counter()
    total_itens = 0  # unidades = pares user+assistant (turnos)
    skipped_json = 0
    skipped_sem_turno = 0
    total_user_tokens = 0
    total_assistant_tokens = 0

    with open(per_line_path, "w", encoding="utf-8") as out_lines:
        for fp in jsonl_files:
            try:
                rel_name = fp.relative_to(exports_dir).as_posix()
            except ValueError:
                rel_name = fp.name
            with open(fp, encoding="utf-8") as f:
                for line_no, raw in enumerate(f, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        obj = json_loads_loose(raw)
                    except Exception as e:
                        print(
                            f"Aviso: ignorada {rel_name}:{line_no} ({e})",
                            file=sys.stderr,
                        )
                        skipped_json += 1
                        continue
                    if not isinstance(obj, dict):
                        continue

                    msgs = obj.get("messages")
                    if not isinstance(msgs, list):
                        msgs = []
                    pairs = turn_token_pairs(msgs, enc)
                    if not pairs:
                        skipped_sem_turno += 1
                        continue

                    grp = grupo_por_caminho(rel_name)
                    sl = (
                        segunda_subpasta(rel_name, "livros")
                        if grp == "livros"
                        else None
                    )
                    sr = (
                        segunda_subpasta(rel_name, "registros")
                        if grp == "registros"
                        else None
                    )

                    for turn_idx, (u_tok, a_tok) in enumerate(pairs, start=1):
                        total_user_tokens += u_tok
                        total_assistant_tokens += a_tok
                        total_itens += 1
                        group_counts[grp] += 1
                        if grp == "livros":
                            sub_livros[sl if sl else "(sem subpasta)"] += 1
                        elif grp == "registros":
                            sub_registros[sr if sr else "(sem subpasta)"] += 1
                        bucket = classify_assistant(a_tok)
                        class_counts[bucket] += 1

                        record = {
                            "arquivo": rel_name,
                            "linha": line_no,
                            "turno": turn_idx,
                            "user": str(u_tok),
                            "assistant": str(a_tok),
                            "grupo": grp,
                            "classificacao_assistant": bucket,
                        }
                        if "conversation_id" in obj:
                            record["conversation_id"] = obj["conversation_id"]
                        if "segment_id" in obj:
                            record["segment_id"] = obj["segment_id"]
                        out_lines.write(
                            json.dumps(record, ensure_ascii=False) + "\n"
                        )

    def pct(n: int) -> float:
        if total_itens == 0:
            return 0.0
        return 100.0 * n / total_itens

    gerado_em = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines_report = [
        "Relatório de tokens — CURADORIA GPT MANUAL",
        "=" * 60,
        f"Gerado em: {gerado_em}  (volte a executar o script após alterar qualquer .jsonl)",
        f"Pasta analisada (recursiva): {exports_dir.resolve()}",
        f"Ficheiros .jsonl: {len(jsonl_files)}",
        f"Itens (turnos user+assistant) contabilizados: {total_itens}",
        f"Linhas JSONL ignoradas (JSON inválido): {skipped_json}",
        f"Linhas JSONL sem par user+assistant: {skipped_sem_turno}",
        f"Encoding: tiktoken cl100k_base",
        "",
        "Totais acumulados (todos os turnos):",
        f"  Tokens user (soma):     {total_user_tokens}",
        f"  Tokens assistant (soma): {total_assistant_tokens}",
        "",
        "O que a tabela «Classificação» mede:",
        "  • Cada par consecutivo user → assistant em ``messages`` = 1 turno (1 unidade).",
        "  • Uma linha JSONL pode conter vários turnos; cada um é classificado à parte.",
        "  • «Curta (80–200)» etc. = faixas pelo TAMANHO da resposta assistant (tokens) naquele turno.",
        "  • N e % atual = quantos TURNOS caem em cada faixa (percentagem sobre o nº de turnos).",
        "    Não é percentagem de «tokens totais do dataset» por faixa.",
        "  • Ao apagar linhas num .jsonl, guarde o ficheiro e execute: python exportacao_estatisticas_tokens.py",
        "    — a leitura anterior deste ficheiro desce no histórico (não é apagada).",
        "",
        "Classificação por tokens do ASSISTANT (por turno):",
        "  (A tabela de metas aplica-se à distribuição do comprimento das respostas.)",
        "",
    ]

    # Ordem de apresentação
    order = [
        ("abaixo_80", "Abaixo de 80 (fora da tabela inferior)", None),
        ("curta", "Curta (80 – 200)", META["curta"]),
        ("media", "Média (201 – 500)", META["media"]),
        ("longa", "Longa (501 – 800)", META["longa"]),
        ("muito_longa", "Muito longa (801+)", META["muito_longa"]),
    ]

    lines_report.append(
        f"{'Classificação':<38} {'N':>8} {'% atual':>10} {'% meta':>10} {'Δ':>8}"
    )
    lines_report.append("-" * 76)

    for key, label, meta in order:
        n = class_counts.get(key, 0)
        p = pct(n)
        if meta is not None:
            delta = p - meta
            lines_report.append(
                f"{label:<38} {n:>8} {p:>9.1f}% {meta:>9.1f}% {delta:>+7.1f}pp"
            )
        else:
            lines_report.append(f"{label:<38} {n:>8} {p:>9.1f}% {'—':>10} {'—':>8}")

    sum_class = sum(class_counts.get(k, 0) for k, _, _ in order)
    lines_report.append("-" * 76)
    lines_report.append(
        f"{'Total':<38} {sum_class:>8} "
        f"{100.0 if sum_class else 0.0:>9.1f}% {'—':>10} {'—':>8}"
    )

    lines_report.extend(
        [
            "",
            "Função (referência):",
            "  Curta:       precisão, impacto, respostas rápidas",
            "  Média:       base principal de profundidade",
            "  Longa:       leituras mais completas",
            "  Muito longa: casos especiais (campo aberto, narrativas)",
            "",
            "Notas:",
            "  • % meta (40 / 35 / 20 / 5) refere-se apenas às quatro faixas centrais;",
            "    turnos «Abaixo de 80» não entram nessa proporção alvo.",
            "  • Para aproximar o dataset das metas, ajuste amostragem ou reescreva",
            "    respostas para concentrar mais turnos nas faixas desejadas.",
            "",
            f"Ficheiros gerados em: {out_dir.resolve()}",
            f"  - {per_line_path.name}",
            f"  - {report_path.name}",
            f"  - {proporcoes_path.name}",
        ]
    )

    def pct_itens(n: int) -> float:
        if total_itens == 0:
            return 0.0
        return 100.0 * n / total_itens

    meta_str = {k: f"{v:.0f}%" for k, v in GRUPO_META_PCT.items()}
    meta_str["nao_classificado"] = "—"

    lines_prop = [
        "Proporção de itens por grupo editorial — CURADORIA GPT MANUAL",
        "=" * 60,
        f"Gerado em: {gerado_em}",
        f"Pasta analisada: {exports_dir.resolve()}",
        f"Total de itens (turnos user+assistant): {total_itens}",
        "",
        "Métrica: número de turnos por grupo editorial, em % do total de turnos.",
        "Cada par user+assistant válido conta 1 item; uma linha JSONL pode gerar vários.",
        "",
        f"{'Grupo':<28} {'N':>7} {'% atual':>10} {'Meta':>12} {'Estado':<28}",
        "-" * 90,
    ]

    for gkey in GRUPO_ORDEM:
        n = group_counts.get(gkey, 0)
        p = pct_itens(n)
        label = GRUPO_LABEL[gkey]
        mstr = meta_str[gkey]
        if gkey in GRUPO_META_PCT:
            st = _delta_meta(p, GRUPO_META_PCT[gkey])
        else:
            st = "fora do mapeamento" if n else "—"
        lines_prop.append(
            f"{label:<28} {n:>7} {p:>9.1f}% {mstr:>12} {st:<28}"
        )

    sum_n = sum(group_counts.get(g, 0) for g in GRUPO_ORDEM)
    lines_prop.append("-" * 90)
    lines_prop.append(
        f"{'Total':<28} {sum_n:>7} "
        f"{100.0 if sum_n else 0.0:>9.1f}% {'—':>12} {'—':<28}"
    )

    livros_n = group_counts.get("livros", 0)
    registros_n = group_counts.get("registros", 0)
    lines_prop.extend(["", "Detalhe — subpastas (2.º nível):", "-" * 90])
    lines_prop.append("livros/")
    if livros_n == 0:
        lines_prop.append("  (nenhum turno neste grupo)")
    else:
        for nome in sorted(sub_livros.keys()):
            n_sub = sub_livros[nome]
            pct_gl = 100.0 * n_sub / livros_n
            label = nome if nome.startswith("(") else f"{nome}/"
            lines_prop.append(
                f"  └─ {label:<36} {n_sub:>7}  ({pct_gl:5.1f}% do grupo Livros)"
            )
    lines_prop.append("")
    lines_prop.append("registros/")
    if registros_n == 0:
        lines_prop.append("  (nenhum turno neste grupo)")
    else:
        for nome in sorted(sub_registros.keys()):
            n_sub = sub_registros[nome]
            pct_gr = 100.0 * n_sub / registros_n
            label = nome if nome.startswith("(") else f"{nome}/"
            lines_prop.append(
                f"  └─ {label:<36} {n_sub:>7}  ({pct_gr:5.1f}% do grupo Registros)"
            )

    lines_prop.extend(
        [
            "",
            "Metas fixas (referência; somam 100% com os seis grupos mapeados):",
            "  Livros — fundação teológica e mística (espinha dorsal).",
            "  Mensagens Bíblicas — tom religioso e aplicação pastoral.",
            "  Leituras — diagnóstico energético (complemento).",
            "  Base de Conhecimento — fragmentos, P&R, temas nomeados.",
            "  Sintéticos — dados gerados/derivados (ex.: mapas sintéticos, padrões de auto-cuidado).",
            "  Registros — presença dialógica, figuras transitórias, eventos únicos de campo.",
            "",
            "Mapeamento de pastas (data/exports):",
            "  livros/                  → Livros",
            "  mensagens_biblicas/      → Mensagens Bíblicas",
            "  leituras_de_campo/       → Leituras",
            "  base_de_conhecimento/    → Base de Conhecimento",
            "  sinteticos/              → Sintéticos",
            "  registros/               → Registros (subpastas ex.: core/, eventos_unicos/)",
            "",
        ]
    )
    nc = group_counts.get("nao_classificado", 0)
    if nc:
        lines_prop.append(
            f"Aviso: {nc} item(ns) em pastas fora do esquema acima — "
            "ajuste pastas ou grupo_por_caminho() no script."
        )
        lines_prop.append("")

    lines_prop.append(f"Ficheiro: {proporcoes_path.resolve()}")

    escrever_relatorio_com_historico(report_path, "\n".join(lines_report))
    escrever_relatorio_com_historico(proporcoes_path, "\n".join(lines_prop))

    print(f"Itens (turnos) escritos: {total_itens} → {per_line_path}")
    if skipped_json:
        print(
            f"Aviso: {skipped_json} linha(s) ignorada(s) por JSON inválido.",
            file=sys.stderr,
        )
    if skipped_sem_turno:
        print(
            f"Aviso: {skipped_sem_turno} linha(s) sem par user+assistant (ignoradas).",
            file=sys.stderr,
        )
    print(f"Relatório tokens: {report_path}")
    print(f"Proporções por grupo: {proporcoes_path}")


if __name__ == "__main__":
    main()
