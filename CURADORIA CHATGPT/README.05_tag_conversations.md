0    | $0.87
1000 | $1.09 | 0,22
1000 |

# Documentação: `05_tag_conversations.py`

Documentação completa do script que adiciona tags (genero, funcao, tom) e classifica conversas via LLM. Alinha ao padrão da curadoria da Bíblia. **LLM não é obrigatório** — use `--no-llm` para tags padrão (pipeline sem API).

Para leituras de campo, o script também **anonimiza** pergunta e resposta: substitui nomes por "uma pessoa" + tema genérico.

---

## 1. Objetivo

O script lê `04_scored_segments.jsonl`, classifica cada segmento via LLM (ou tags padrão) e grava em `05_tagged_segments.jsonl`. Para segmentos do tipo **leitura** ou **pergunta_ao_campo**, reescreve a pergunta do user e substitui nomes na resposta do assistant, preparando o dataset para treino sem dados identificáveis.

---

## 2. Arquivos envolvidos

| Constante | Valor | Descrição |
|-----------|-------|-----------|
| `INPUT_FILE` | `data/processed/04_scored_segments.jsonl` | Saída do script 04 (segmentos com quality_score) |
| `OUTPUT_FILE` | `data/processed/05_tagged_segments.jsonl` | Segmentos taggeados e anonimizados |

**Pré-requisito:** Execute `04_quality_scoring.py` antes.

---

## 3. Dependências

- **Python 3.x**
- **openai** (pip install openai) — cliente compatível com API OpenAI e DeepSeek
- **config.py** — configurações e prompt (LLM_PROVIDERS, PROMPT_TAG_CONVERSATION, etc.)

Sem LLM (`--no-llm`): nenhuma dependência externa além das bibliotecas padrão.

---

## 4. Configuração (config.py)

O script importa de `config.py`:

| Constante | Descrição |
|-----------|-----------|
| `LLM_PROVIDERS` | gpt, deepseek (env_key, model, base_url) |
| `PROMPT_TAG_CONVERSATION` | Prompt para classificação e anonimização |
| `MIN_SCORE` | Score mínimo para processar (padrão 0.55) |
| `MAX_TEXT_LENGTH` | Caracteres máximos enviados à LLM (padrão 800) |
| `DEFAULT_TAGS` | Tags quando --no-llm |
| `PAUSE_EVERY_N_REQUESTS` | Pausa a cada N requisições (rate limit) |
| `PAUSE_BATCH_MIN/MAX` | Segundos de pausa (aleatório) |

### Variáveis de ambiente

| Variável | Provedor | Onde obter |
|----------|----------|------------|
| `DEEPSEEK_API_KEY` | DeepSeek (padrão) | [platform.deepseek.com](https://platform.deepseek.com) |
| `OPENAI_API_KEY` | GPT | [platform.openai.com](https://platform.openai.com) |

Defina **uma** das duas. Se nenhuma estiver definida, o script usa `--no-llm` automaticamente.

---

## 5. Tipos e tags

### 5.1 TIPO (classificação)

| Tipo | Descrição |
|------|-----------|
| **leitura** | Pedidos de leitura específica — "faz a leitura de X", "analisa o campo de Y", "dinâmica de fulano" |
| **pergunta_ao_campo** | Usuário pede para o campo responder perguntas de outras pessoas — "responde pra ela", "o campo responde pra Débora" |
| **conversa** | Perguntas gerais, explicações, pedidos de texto, etc. |

### 5.2 TAGS (genero, funcao, tom)

Mesmos nomes da curadoria bíblica:

- **genero:** narrativa, poesia, conversa, explicativo, criativo, dialogo, etc.
- **funcao:** historica, espiritual, educacional, pratica, conselho, acolhimento, etc.
- **tom:** reflexivo, contemplativo, poetico, pratico, formal, informal, conselheira, campo, etc.

### 5.3 Campos adicionais (leitura / pergunta_ao_campo)

| Campo | Descrição |
|-------|-----------|
| **tipo_consulta** | ansiedade, relacionamento, propósito, trabalho, transição, saúde, espiritual |
| **contexto_anonimo** | Frase genérica, ex. "pessoa em transição profissional" |
| **user_anonimizado** | Pergunta reescrita com "uma pessoa" + tema genérico na própria pergunta |
| **nome_remover** | Nome(s) da pessoa a substituir na resposta do assistant por "a pessoa" |

---

## 6. Anonimização (leituras de campo)

Quando o tipo é **leitura** ou **pergunta_ao_campo**, o script modifica as mensagens:

### 6.1 Pergunta (user)

Substitui o conteúdo da primeira mensagem do user por `user_anonimizado` (gerado pela LLM).

**Exemplo:**
- Original: *"Analisa o campo da Débora e vê o que eu posso fazer por ela"*
- user_anonimizado: *"Analisa o campo de uma pessoa em dúvida sobre mensagem espiritual e orienta o que fazer por ela"*

### 6.2 Resposta (assistant)

A função `anonymize_content()` substitui os nomes em `nome_remover` por "a pessoa":

| Padrão | Substituição |
|--------|--------------|
| "da Nome", "do Nome", "de Nome" | "da pessoa" |
| "Nome" (restante) | "a pessoa" |

**Exemplo:** Se `nome_remover` = "Débora", a resposta "Fiz a leitura da Débora..." vira "Fiz a leitura da pessoa...".

---

## 7. Argumentos da CLI

| Argumento | Atalho | Padrão | Descrição |
|-----------|--------|--------|-----------|
| `--provider` | `-p` | deepseek | Provedor LLM (deepseek ou gpt) |
| `--resume` | `-r` | — | Continuar de onde parou (append, não sobrescreve) |
| `--no-llm` | — | — | Sem LLM: usa tags padrão (permite pipeline sem API) |
| `--limit` | `-l` | 0 | Limita número de segmentos (0 = todos). Útil para teste. |
| `--delay` | `-d` | 0.2 | Segundos fixos entre chamadas |
| `--delay-min` | — | — | Mínimo segundos para intervalo aleatório (use com --delay-max) |
| `--delay-max` | — | — | Máximo segundos para intervalo aleatório |

**Auto-fallback:** Se `--no-llm` não foi passado e não há API key, o script usa tags padrão automaticamente.

---

## 8. Exemplos de uso

```bash
# Defina a variável antes (obrigatório para usar LLM)
export DEEPSEEK_API_KEY="sua-chave"

# Gerar tudo com DeepSeek (padrão)
python 05_tag_conversations.py --provider deepseek

# Gerar com GPT
export OPENAI_API_KEY="sk-..."
python 05_tag_conversations.py --provider gpt

# Testar com apenas 5 segmentos
python 05_tag_conversations.py --provider deepseek --limit 5

# Continuar de onde parou (resume)
python 05_tag_conversations.py --provider deepseek --resume

# Delay fixo (evitar rate limit)
python 05_tag_conversations.py --provider deepseek --delay 2

# Intervalo aleatório 1–3 s (requisições mais dinâmicas)
python 05_tag_conversations.py --provider deepseek --delay-min 1 --delay-max 3

# Sem LLM (tags padrão, pipeline sem API)
python 05_tag_conversations.py --no-llm
```

---

## 9. Fluxo principal (`main`)

```
1. Verifica API key; se ausente, usa --no-llm
2. Carrega segmentos de 04_scored_segments.jsonl
3. Filtra por quality_score >= MIN_SCORE e len(messages) >= 2
4. Se --resume: carrega IDs já gravados em 05_tagged_segments.jsonl
5. Para cada segmento não processado:
   - Se --no-llm: usa _default_result(is_leitura_hint)
   - Senão: chama tag_conversation_llm(messages, provider)
   - Se leitura/pergunta_ao_campo: substitui user por user_anonimizado, assistant por anonymize_content(assistant, nome_remover)
   - Grava segmento em 05_tagged_segments.jsonl
6. A cada PAUSE_EVERY_N_REQUESTS: pausa aleatória (rate limit)
7. Imprime total processado
```

---

## 10. Com LLM vs Sem LLM

### Com LLM (API key configurada)

| O que | Descrição |
|-------|-----------|
| **Classificação** | LLM analisa cada conversa e retorna tipo, genero, funcao, tom, tipo_consulta, contexto_anonimo, user_anonimizado, nome_remover |
| **Leituras** | Pergunta substituída por user_anonimizado; nomes na resposta substituídos por "a pessoa" |
| **Pausas** | A cada 10 requisições, pausa aleatória 2–5 s (configurável) |

### Sem LLM (`--no-llm` ou sem API key)

| O que | Descrição |
|-------|-----------|
| **Classificação** | Tags padrão: genero=["conversa"], funcao=["educacional"], tom=["reflexivo"] |
| **Leituras** | Se fonte=leitura_gpt (detectado no 02): tags de leitura (dialogo, conselho, acolhimento). **Sem** anonimização (user_anonimizado e nome_remover ficam null) |
| **Pausas** | Nenhuma (não há chamadas à API) |

---

## 11. Funções principais (referência rápida)

| Função | O que faz |
|--------|-----------|
| `has_llm_key(provider)` | Verifica se há API key configurada |
| `get_llm_client(provider)` | Retorna (OpenAI client, model). Valida API key. |
| `extract_text_for_prompt(messages)` | Extrai user + assistant até MAX_TEXT_LENGTH caracteres |
| `tag_conversation_llm(messages, provider, is_leitura_hint)` | Chama LLM, parseia JSON, retorna tags + tipo + anonimização |
| `anonymize_content(content, nome_remover)` | Substitui nomes na resposta por "a pessoa" |
| `_default_result(is_leitura)` | Retorna tags padrão (com ou sem leitura) |
| `_ensure_list(x)` | Garante que genero/funcao/tom sejam listas |

---

## 12. Formato de saída

Cada linha de `05_tagged_segments.jsonl` mantém a estrutura do 04, com adições:

| Campo | Quando aparece |
|-------|----------------|
| `tags` | Sempre (genero, funcao, tom) |
| `tipo` | Sempre (leitura, pergunta_ao_campo ou conversa) |
| `fonte` | Sempre (leitura_gpt ou chatgpt_export) |
| `tipo_consulta` | Se leitura ou pergunta_ao_campo |
| `contexto_anonimo` | Se leitura ou pergunta_ao_campo |
| `anonimizado` | Se leitura ou pergunta_ao_campo |
| `metadata` | Se leitura ou pergunta_ao_campo |
| `messages` | **Modificado** se leitura: user → user_anonimizado, assistant → nomes substituídos |

---

## 13. Execução

```bash
cd CURADORIA CHATGPT
python 05_tag_conversations.py --provider deepseek
```

**Pré-requisito:** `04_scored_segments.jsonl` existente (gerado pelo script 04).

**Saída no terminal:**
```
Segmentos lidos: XXXX
Novos taggeados: XXXX
Já existentes (skip): XX   # se --resume
Salvo em: data/processed/05_tagged_segments.jsonl
```

---

## 14. Próximo passo no pipeline

O arquivo `05_tagged_segments.jsonl` é a entrada do `06_format_for_training.py`, que formata para o dataset final de treino (`06_llm_training_dataset.jsonl`).
