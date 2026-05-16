#!/usr/bin/env python3
"""
Por omissão só percorre `data/exports` (subpastas de exportação); pastas chamadas `select`
são sempre ignoradas, mesmo que --root inclua esse ramo.

Por omissão, **antes de validar**, ajusta e grava ``turn_count`` = ``len(messages)//2`` em todas as
linhas com lista ``messages`` (valores errados, ausentes ou tipo inválido). Use ``--sem-fix-turn-count``
para apenas inspecionar sem alterar ficheiros.

A partir de --root válido, valida ficheiros *.jsonl encontrados por varredura recursiva:
cada linha não vazia tem de ser um único objeto JSON válido (padrão JSONL).

Além disso valida o esquema de conversação esperado por muitos pipelines LoRA:
  - objeto raiz com chave obrigatória "messages" (lista);
  - turnos estritamente alternados começando em "user": user, assistant, user, assistant, …
  - cada entrada em "messages" é um objeto com pelo menos "role" (user|assistant) e "content"
    (tipicamente string; outras chaves no mesmo objeto são permitidas);
  - número par de mensagens (cada turno = par user + assistant);
  - chave obrigatória ``turn_count`` (inteiro) igual a ``len(messages) // 2`` — o número de turnos
    completos (pares user+assistant) coerente com o array;
  - turnos incompletos ou ordem invertida (ex.: assistant antes do user esperado) são erros.

Cada erro inclui linha no ficheiro e, sempre que derivável da linha de texto já guardada em disco,
a coluna inicial (base 1) do `{` de ``messages[k]`` ou o apontador de sintaxe do ``json.loads`` —
formato típico: ``ficheiro:linha`` ou ``ficheiro:linha:coluna`` (saltar direto para o carácter no Cursor/VS Code).

Uso:
  python validar_jsonl_recursivo.py
  python validar_jsonl_recursivo.py --root /caminho/para/data/exports
  python validar_jsonl_recursivo.py --quiet
  python validar_jsonl_recursivo.py --sem-turn-count   # ignorar coerência de turn_count na validação
  python validar_jsonl_recursivo.py --sem-fix-turn-count # só valida, não regrava turn_count nos ficheiros
  python validar_jsonl_recursivo.py --somente-json       # só sintaxe JSON (não altera turn_count)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = (DIR / "data" / "exports").resolve()

# Segmentos de caminho ignorados (ex.: não validar dados em preparação sob data/select/).
DIRETORIOS_IGNORADOS_NOS_CAMINHOS = frozenset({"select"})

ROLES_VALIDAS = frozenset({"user", "assistant"})


def indice_trimmed_na_linha_ficheiro(linha_ficheiro: str, texto_trimmed: str) -> int:
    """Desvio (offset 0-base) até ao início de texto_trimmed dentro da linha física."""
    if not texto_trimmed:
        return len(linha_ficheiro) - len(linha_ficheiro.lstrip(" \t\n\r\f\v"))
    try:
        return linha_ficheiro.index(texto_trimmed)
    except ValueError:
        n = len(linha_ficheiro)
        i = 0
        while i < n and linha_ficheiro[i] in " \t\n\r\f\v":
            i += 1
        return i


def coluna_physical_json_decode(
    linha_ficheiro: str, texto_trimmed: str, erro: json.JSONDecodeError
) -> int | None:
    """Coluna 1-based na linha do ficheiro, alinhada com json.loads sobre texto_trimmed."""
    if erro.lineno != 1:
        return None
    lead = indice_trimmed_na_linha_ficheiro(linha_ficheiro, texto_trimmed)
    # colno conta a partir da 1ª coluna da "linha lógica" passada ao descodificador
    return lead + erro.colno


def encontrar_matching_chave(payload: str, abertura: int) -> int | None:
    """Índice 0-base do fecho `}` correspondente ao `{` em abertura; None se incompleto."""
    if abertura >= len(payload) or payload[abertura] != "{":
        return None
    prof = 0
    dentro_string = False
    escape = False
    i = abertura
    while i < len(payload):
        ch = payload[i]
        if dentro_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                dentro_string = False
            i += 1
            continue
        if ch == '"':
            dentro_string = True
            i += 1
            continue
        if ch == "{":
            prof += 1
        elif ch == "}":
            prof -= 1
            if prof == 0:
                return i
        i += 1
    return None


def avancar_espacos(payload: str, i: int) -> int:
    while i < len(payload) and payload[i] in " \t\n\r\f\v":
        i += 1
    return i


def offsets_aberturas_objetos_em_messages(payload: str) -> list[int] | None:
    """
    Lista de índices 0-base de cada `{` que abre um objeto dentro do array `messages`,
    segundo o texto JSON (ordenado pela ordem física das mensagens).

    Ajuda localizar falhas estruturais na linha física quando o objeto JSON já é válido.
    """
    m = re.search(r'"messages"\s*:', payload)
    if not m:
        return None
    i = avancar_espacos(payload, m.end())
    if i >= len(payload) or payload[i] != "[":
        return None
    i += 1
    posicoes: list[int] = []
    while True:
        i = avancar_espacos(payload, i)
        if i >= len(payload):
            return None
        if payload[i] == "]":
            break
        if payload[i] == "{":
            posicoes.append(i)
            fim_obj = encontrar_matching_chave(payload, i)
            if fim_obj is None:
                return None
            i = avancar_espacos(payload, fim_obj + 1)
            if i < len(payload) and payload[i] == ",":
                i += 1
                continue
            i = avancar_espacos(payload, i)
            if i < len(payload) and payload[i] == "]":
                break
            return None
        return None
    return posicoes


def coluna_objecto_message(
    linha_ficheiro: str, texto_trimmed: str, indice_msg: int | None, offsets_objs: list[int] | None
) -> int | None:
    """
    Coluna 1-based onde começa `{` da mensagens[k] dentro da linha do ficheiro;
    usa offsets pré-calculados sobre texto_trimmed.
    """
    if indice_msg is None:
        return None
    if not offsets_objs or indice_msg < 0 or indice_msg >= len(offsets_objs):
        return None
    lead = indice_trimmed_na_linha_ficheiro(linha_ficheiro, texto_trimmed)
    # colunas em editores são 1-based no código UTF-8 (code points igual a Python len char)
    return lead + offsets_objs[indice_msg] + 1


def _validar_turn_count_vs_messages(
    obj: dict[str, Any],
    msgs: list[Any],
    erros: list[tuple[int | None, str]],
) -> None:
    """
    ``turn_count`` deve existir, ser inteiro e igual a len(msgs)//2
    (número de pares user+assistant no array ``messages``).
    """
    esperado = len(msgs) // 2
    if "turn_count" not in obj:
        erros.append(
            (
                None,
                "falta a chave obrigatória 'turn_count' (inteiro = número de turnos: len(messages)//2; "
                f"neste registo o valor esperado seria {esperado}).",
            )
        )
        return
    tc = obj["turn_count"]
    if isinstance(tc, bool):
        erros.append(
            (None, "'turn_count' não pode ser booleano; use um inteiro (ex.: 2)."),
        )
        return
    if not isinstance(tc, int):
        erros.append(
            (
                None,
                f"'turn_count' tem de ser um inteiro; encontrado tipo {type(tc).__name__!r}.",
            ),
        )
        return
    if tc != esperado:
        erros.append(
            (
                None,
                f"'turn_count' ({tc}) não coincide com messages: há {len(msgs)} mensagem(ns) → "
                f"{esperado} turno(s) segundo len(messages)//2. Use turn_count: {esperado}.",
            ),
        )


def coluna_turn_count(payload: str, linha_ficheiro: str) -> int | None:
    """Coluna 1-based do início da chave ``turn_count`` na linha física."""
    m = re.search(r'"turn_count"\s*:', payload)
    if not m:
        return None
    lead = indice_trimmed_na_linha_ficheiro(linha_ficheiro, payload)
    return lead + m.start() + 1


def validar_estrutura_messages(
    obj: Any,
    *,
    validar_turn_count: bool = True,
) -> list[tuple[int | None, str]]:
    """
    Valida objeto já descodificado pelo json.loads.
    Outras chaves no objeto raiz ou dentro de cada mensagem são aceites;
    apenas o bloco messages tem regras rígidas para o formato de turnos LoRA.
    """
    erros: list[tuple[int | None, str]] = []
    if not isinstance(obj, dict):
        return [(None, "a raiz tem de ser um objeto JSON ({...}); tipos não mapeados no JSON não são válidos aqui.")]
    if "messages" not in obj:
        return [(None, "falta a chave obrigatória 'messages'.")]

    msgs = obj["messages"]
    if not isinstance(msgs, list):
        erros.append((None, "'messages' tem de ser uma lista ([])."))
        return erros
    if len(msgs) == 0:
        erros.append((None, "'messages' está vazio; é necessário pelo menos um turno (user + assistant)."))
        if validar_turn_count:
            _validar_turn_count_vs_messages(obj, msgs, erros)
        return erros

    for i, m in enumerate(msgs):
        esperado = "user" if i % 2 == 0 else "assistant"
        pref = f"messages[{i}]"

        if not isinstance(m, dict):
            erros.append((i, f"{pref}: cada mensagem tem de ser um objeto; encontrado {type(m).__name__}."))
            continue

        if "role" not in m:
            erros.append((i, f"{pref}: falta a chave obrigatória 'role'."))
            role_norm: str | None = None
        else:
            role = m["role"]
            if not isinstance(role, str):
                erros.append((i, f"{pref}.role tem de ser string (ex.: \"user\")."))
                role_norm = None
            else:
                role_norm = role.strip()
                if role_norm != role:
                    erros.append(
                        (
                            i,
                            f"{pref}.role não deve ter espaços em branco nas extremidades ({role!r}).",
                        )
                    )
                if role_norm not in ROLES_VALIDAS:
                    erros.append(
                        (
                            i,
                            f"{pref}.role tem valor não suportado para este formato: {role_norm!r} "
                            f'(use apenas "user" ou "assistant" em alternância).',
                        )
                    )
                elif role_norm != esperado:
                    if role_norm == "assistant" and esperado == "user":
                        erros.append(
                            (
                                i,
                                f'{pref}: ordem de turnos invertida ou em falta — esperava primeiro '
                                f'"user" nesta posição, veio "assistant". Cada turno é user → assistant.',
                            )
                        )
                    elif role_norm == "user" and esperado == "assistant":
                        erros.append(
                            (
                                i,
                                f"{pref}: turno incompleto ou ordem errada — o turno anterior deveria terminar "
                                f'com "assistant"; não pode aparecer novo "user" sem o "assistant" '
                                f"entre turnos. Confirme também se falta mensagem antes desta.",
                            )
                        )

        if "content" not in m:
            erros.append((i, f"{pref}: falta a chave obrigatória 'content'."))
        else:
            c = m["content"]
            if c is None:
                erros.append((i, f"{pref}.content não pode ser null."))
            elif not isinstance(c, str):
                erros.append(
                    (
                        i,
                        f"{pref}.content tem de ser string (texto) para este conjunto LoRA estável; "
                        f"tipo encontrado: {type(c).__name__}.",
                    )
                )

    if len(msgs) % 2 != 0:
        ultimo = len(msgs) - 1
        erros.append(
            (
                ultimo,
                "número ímpar de mensagens — turno incompleto na cauda (último par user/assistant incompleto). "
                "Cada turno = exatamente 2 objetos: user e seguidamente assistant.",
            )
        )

    if validar_turn_count:
        _validar_turn_count_vs_messages(obj, msgs, erros)
    return erros


def validar_ficheiro(
    caminho: Path,
    *,
    somente_json: bool = False,
    validar_turn_count: bool = True,
) -> tuple[list[tuple[int, int | None, str]], int]:
    """
    Uma passagem pelo ficheiro.
    Devolve (lista de erros (linha, coluna_opcional_1_based, msg), número de linhas não vazias).
    lineno -1 = erro de abertura/leitura.
    """
    erros: list[tuple[int, int | None, str]] = []
    linhas_json = 0
    try:
        with caminho.open("r", encoding="utf-8") as f:
            for num_linha, linha in enumerate(f, start=1):
                if not linha.strip():
                    continue
                linhas_json += 1
                payload = linha.strip()
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError as e:
                    col = coluna_physical_json_decode(linha, payload, e)
                    erros.append((num_linha, col, str(e)))
                else:
                    if not somente_json:
                        offsets_msgs = offsets_aberturas_objetos_em_messages(payload)
                        for idx_msg, msg_est in validar_estrutura_messages(
                            obj,
                            validar_turn_count=validar_turn_count,
                        ):
                            col = coluna_objecto_message(linha, payload, idx_msg, offsets_msgs)
                            if col is None and "'turn_count'" in msg_est:
                                col = coluna_turn_count(payload, linha)
                            erros.append((num_linha, col, msg_est))
    except UnicodeDecodeError as e:
        erros.append((-1, None, f"UTF-8 inválido: {e}"))
    except OSError as e:
        erros.append((-1, None, str(e)))
    return erros, linhas_json


def caminho_tem_segmento_ignorado(caminho: Path) -> bool:
    """True se algum elemento do caminho corresponde a um diretório ignorado."""
    return any(p.lower() in DIRETORIOS_IGNORADOS_NOS_CAMINHOS for p in caminho.parts)


def rel_path(caminho: Path, root: Path) -> Path:
    try:
        return caminho.relative_to(root)
    except ValueError:
        return caminho


_SENTINEL_FALTA = object()


def corrigir_turn_count_em_obj(obj: Any) -> bool:
    """
    Define ``turn_count`` = len(messages)//2 quando ``messages`` é lista.
    Corrige tipo inválido (ex.: booleano) ou valor errado. Altera ``obj`` no lugar.
    Devolve True se alterou o dicionário.
    """
    if not isinstance(obj, dict):
        return False
    msgs = obj.get("messages")
    if not isinstance(msgs, list):
        return False
    esperado = len(msgs) // 2
    tc = obj.get("turn_count", _SENTINEL_FALTA)
    if tc is _SENTINEL_FALTA:
        obj["turn_count"] = esperado
        return True
    if isinstance(tc, bool):
        obj["turn_count"] = esperado
        return True
    if not isinstance(tc, int):
        obj["turn_count"] = esperado
        return True
    if tc != esperado:
        obj["turn_count"] = esperado
        return True
    return False


def escrever_ficheiro_atomicamente(caminho: Path, conteudo: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        prefix=".tmp_validar_jsonl_",
        suffix=".jsonl",
        dir=str(caminho.parent),
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as wf:
            wf.write(conteudo)
        os.replace(tmp_path, caminho)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def corrigir_turn_count_num_ficheiro(
    caminho: Path,
    *,
    quiet: bool,
    root: Path | None = None,
) -> tuple[int, int]:
    """
    Lê o JSONL, ajusta ``turn_count`` por linha e regrava o ficheiro se houver mudanças.
    Devolve (número de linhas JSON alteradas, número de linhas JSON processadas).
    """
    rel = rel_path(caminho, root) if root is not None else caminho
    alteradas = 0
    processadas = 0
    try:
        texto = caminho.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        if not quiet:
            print(f"{rel}: falha ao ler para correção: {e}", file=sys.stderr)
        return 0, 0

    linhas_saida: list[str] = []
    linhas_brutas = texto.splitlines(keepends=True)
    for num_fis, linha in enumerate(linhas_brutas, start=1):
        if linha.endswith("\r\n"):
            corpo = linha[:-2]
            suf = "\r\n"
        elif linha.endswith("\n"):
            corpo = linha[:-1]
            suf = "\n"
        else:
            corpo = linha
            suf = ""

        if not corpo.strip():
            linhas_saida.append(linha)
            continue

        payload = corpo.strip()
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError as e:
            if not quiet:
                print(f"{rel}:{num_fis}: JSON inválido, linha ignorada na correção: {e}", file=sys.stderr)
            linhas_saida.append(linha)
            continue

        processadas += 1
        if corrigir_turn_count_em_obj(obj):
            alteradas += 1
            novo = json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))
            linhas_saida.append(novo + suf)
        else:
            linhas_saida.append(linha)

    if alteradas > 0:
        escrever_ficheiro_atomicamente(caminho, "".join(linhas_saida))

    return alteradas, processadas


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(description="Valida JSONL em todas as subpastas.")
    ap.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=(
            "Diretório raiz para pesquisa. Por omissão: data/exports junto ao script. "
            f"(default atual: {DEFAULT_ROOT}). Segmentos de caminho 'select' são ignorados."
        ),
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Só imprime erros e resumo final.",
    )
    ap.add_argument(
        "--somente-json",
        action="store_true",
        help="Valida apenas sintaxe JSON por linha (ignora messages e turn_count).",
    )
    ap.add_argument(
        "--sem-turn-count",
        action="store_true",
        help="Não exige nem valida a chave turn_count (só messages e papéis alternados).",
    )
    ap.add_argument(
        "--sem-fix-turn-count",
        action="store_true",
        help="Não grava correções em turn_count (apenas valida; por omissão o script ajusta e regrava).",
    )
    args = ap.parse_args()
    root: Path = args.root.resolve()

    if not root.is_dir():
        print(f"Erro: não é um diretório: {root}", file=sys.stderr)
        return 1

    jsonls = sorted(
        p for p in root.rglob("*.jsonl") if not caminho_tem_segmento_ignorado(p)
    )

    if not jsonls:
        print(f"Nenhum ficheiro .jsonl encontrado em {root}", flush=True)
        return 0

    aplicar_fix = not args.sem_fix_turn_count and not args.somente_json
    if aplicar_fix:
        total_linhas_corrigidas = 0
        ficheiros_tocados = 0
        for caminho in jsonls:
            alt, _proc = corrigir_turn_count_num_ficheiro(caminho, quiet=args.quiet, root=root)
            if alt > 0:
                ficheiros_tocados += 1
                total_linhas_corrigidas += alt
                if not args.quiet:
                    print(
                        f"{rel_path(caminho, root)}: {alt} linha(s) com turn_count ajustado.",
                        flush=True,
                    )
        if not args.quiet:
            print(
                f"\nCorreção turn_count: {total_linhas_corrigidas} linha(s) "
                f"em {ficheiros_tocados} ficheiro(s).\n",
                flush=True,
            )

    if not args.quiet:
        print(
            f"A validar {len(jsonls)} ficheiro(s) sob {root}\n",
            flush=True,
        )

    total_linhas = 0
    total_erros = 0
    ficheiros_com_erro = 0

    for caminho in jsonls:
        erros, n_linhas = validar_ficheiro(
            caminho,
            somente_json=args.somente_json,
            validar_turn_count=not args.sem_turn_count,
        )
        total_linhas += n_linhas
        rel = rel_path(caminho, root)
        if erros:
            ficheiros_com_erro += 1
            total_erros += len(erros)
            for num, col, msg in erros:
                if num < 0:
                    print(f"{rel}: {msg}", file=sys.stderr)
                elif col is not None:
                    print(f"{rel}:{num}:{col}: {msg}", file=sys.stderr)
                else:
                    print(f"{rel}:{num}: {msg}", file=sys.stderr)

    if total_erros:
        print(
            f"\nResumo: {len(jsonls)} ficheiro(s), {total_linhas} linha(s) JSON, "
            f"{total_erros} erro(s) em {ficheiros_com_erro} ficheiro(s).",
            file=sys.stderr,
        )
        return 1

    msg_final = (
        f"OK: {len(jsonls)} ficheiro(s), {total_linhas} linha(s) JSON válida(s), 0 erros."
    )
    if args.quiet:
        print(msg_final, flush=True)
    else:
        print(f"\n{msg_final}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
