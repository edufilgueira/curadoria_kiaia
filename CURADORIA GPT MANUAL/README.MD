# CURADORIA GPT MANUAL

Curadoria de datasets em JSONL via **DeepSeek Chat** automatizada com **Playwright** (browser real ou Chrome com CDP).

## Instalação

```bash
cd "CURADORIA GPT MANUAL"
pip install -r requirements.txt
playwright install chromium
```

Recomenda-se também `json_repair` (já no `requirements.txt`) para quando o modelo devolver JSON com aspas quebradas.

## Onde definir ficheiro fonte e saída

Os caminhos **não** vêm do `curadoria_config.json`. Edita **só** em `curadoria_batch.py`:

```python
SOURCE = DIR / "data/select/pergunta_resposta.jsonl"   # JSONL a processar (lotes retirados daqui)
CURATED = DIR / "data/exports/base_de_conhecimento/dataset_pergunta_resposta.jsonl"  # curado (append)
```

Os datasets finais organizam-se em subpastas de `data/exports/` (ex.: `livros/cartas_de_cristo/`, `mensagens_biblicas/`, `leituras_de_campo/`, `base_de_conhecimento/`); o relatório de tokens percorre tudo recursivamente.

Ao mudar de dataset, altera estas duas linhas. O `curadoria_playwright.py` e o comando `python curadoria_batch.py reset` usam sempre os mesmos valores.

## Como usar `curadoria_playwright.py`

1. Garante que `SOURCE` aponta para um ficheiro `.jsonl` existente (uma linha = um objeto JSON com `messages`, etc.).
2. Opcional: ajusta `prompt_curadoria.txt` e/ou `curadoria_config.json` (lote, URL, seletores).
3. Executa:

```bash
python3 curadoria_playwright.py
```

4. Na primeira vez (ou com perfil novo), abre-se o Chromium com o perfil em `user_data_dir`; faz login no DeepSeek (e-mail/senha costuma ser mais fiável que Google no Chromium do Playwright).
5. Volta ao terminal e pressiona **Enter** para começar (a menos que uses `--skip-login-wait`).
6. O script lê **lotes** do início de `SOURCE`, envia o prompt + linhas ao modelo, valida a resposta e **anexa** linhas válidas a `CURATED`, **removendo** do `SOURCE` o mesmo número de linhas processadas (com backup `.bak` do fonte).

### Argumentos de linha de comando

| Argumento | Descrição |
|-----------|-----------|
| `--config CAMINHO` | Ficheiro JSON de opções (default: `curadoria_config.json` na pasta do projeto). **Não** define `source`/`curated`. |
| `--batch-size N` | Sobrescreve `batch_size` do JSON (quantas linhas JSONL por pedido ao modelo). |
| `--batches N` | Máximo de lotes nesta execução; omitir usa `max_batches` do JSON ou processa até o fonte esvaziar. |
| `--skip-login-wait` | Não pausa à espera do Enter (útil se já estás logado no perfil). |
| `--cdp-url URL` | Liga a um Chrome já aberto, ex.: `http://127.0.0.1:9222` (útil para login com Google). Sobrescreve `connect_cdp_url` do JSON. |

Exemplos:

```bash
python3 curadoria_playwright.py --batch-size 1 --batches 1
python3 curadoria_playwright.py --config curadoria_config.json --skip-login-wait
python3 curadoria_playwright.py --cdp-url http://127.0.0.1:9222
```

## Variáveis em `curadoria_config.json`

Valores relativos à pasta do projeto (onde está o `curadoria_playwright.py`).

### Lote e fluxo

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `batch_size` | int | Linhas JSONL por lote (pedido ao DeepSeek). |
| `max_batches` | int ou `null` | Máximo de lotes por execução; `null` = até acabar o fonte. |
| `prompt_file` | string | Nome do ficheiro de prompt (ex.: `prompt_curadoria.txt`). |
| `preserve_fields` | lista de strings | Campos do JSON original a recolocar se o modelo omitir (ex.: `conversation_id`, `segment_id`). |

### Browser e chat

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `chat_url` | string | URL aberta ao iniciar (ex.: página do chat DeepSeek). |
| `connect_cdp_url` | string ou `null` | URL CDP do Chrome; `null` usa Chromium do Playwright com `user_data_dir`. |
| `user_data_dir` | string | Pasta do perfil persistente (cookies/sessão), ex.: `.playwright_gpt_manual_profile`. |
| `chromium_args` | lista (opcional) | Argumentos extra ao lançar o Chromium. |

### Envio da mensagem

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `input_selectors` | lista | Seletores CSS a tentar para o campo de texto (textarea / contenteditable). |
| `send_selectors` | lista | Botões de envio, se não usares Enter. |
| `use_enter_to_send` | bool | Se `true`, envia com tecla (ver `send_key_combination`). |
| `send_key_combination` | string | Ex.: `Enter`. |

### Captura da resposta do assistant

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `assistant_message_selectors` | lista | Onde ler o texto da resposta (markdown do DeepSeek). |
| `assistant_pick_best_selector` | bool | Escolher o bloco que melhor contém JSON válido. |
| `assistant_pick_strategy` | string | Ex.: `last_sufficient`, `merge_all` (ver código). |
| `assistant_collect_all_selectors` | bool | Juntar texto de vários seletores. |
| `assistant_use_inner_text` | bool | Usar `inner_text` em vez de `text_content` na captura. |
| `assistant_dom_fallback` | bool | Se ativo, tenta ler JSON do DOM se os seletores falharem. |
| `assistant_dom_fallback_max_chars` | int | Limite de caracteres no fallback DOM. |
| `assistant_dom_fallback_tail_nodes` | int | Quantos nós no fim do documento analisar. |
| `assistant_dom_fallback_after_scroll_ms` | int | Espera após scroll (ms) antes do fallback. |
| `stable_seconds` | float | Quanto tempo o texto da resposta deve ficar estável antes de aceitar. |
| `max_response_wait_seconds` | float | Timeout máximo à espera da resposta. |
| `wait_progress_log_seconds` | float | Intervalo entre mensagens de progresso no terminal (0 = desligar). |

### Pausa entre lotes

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `delay_between_batches_seconds` | float | Pausa fixa em segundos (se não usares intervalo aleatório). |
| `delay_between_batches_random_seconds` | `[min, max]` | Se definido, pausa aleatória entre `min` e `max` segundos (tem prioridade sobre o delay fixo). |

### Validação ao ingerir

| Chave | Tipo | Descrição |
|-------|------|-----------|
| `ingest_topic_check` | string | `strict`, `relaxed` ou `off` — coerência pergunta/resposta ao gravar (ver `curadoria_batch.py`). |

## Reset do fonte / curado

```bash
python3 curadoria_batch.py reset --help
```

Os caminhos usados são sempre `SOURCE` e `CURATED` em `curadoria_batch.py`.

## Ficheiros de diagnóstico (se algo falhar)

Podem ser criados na pasta do projeto: `last_model_raw.txt`, `last_capture_debug.txt`, `last_capture_probe.txt`, `last_error.png`, etc.
