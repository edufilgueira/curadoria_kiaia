# CURADORIA CHATGPT

Pipeline de curadoria de conversas exportadas do ChatGPT para dataset de treino de LLM.  
Formato de saída alinhado ao padrão da curadoria da Bíblia.  
Inclui **leituras de campo** (vibracional, profética, dinâmica de pessoas) com anonimização.

---

## Pré-requisitos

- Python 3.x
- `pip install scikit-learn` (para 02_dataset_filter — filtro de similaridade)
- `pip install openai` (para 05_tag_conversations com LLM)
- Export do ChatGPT em `data/raw/conversations-*.json`

---

## Configuração da LLM

O **único** script que usa LLM é o `05_tag_conversations.py`. **LLM não é obrigatório** — sem API key, o script usa tags padrão (`--no-llm`).

### config.py

Configurações e prompts ficam em `config.py` (como no ORÁCULO VIVO):

| Conteúdo | Descrição |
|----------|-----------|
| `LLM_PROVIDERS` | gpt, deepseek (env_key, model, base_url) |
| `PROMPT_TAG_CONVERSATION` | Prompt para classificação de conversas |
| `MIN_SCORE`, `MAX_TEXT_LENGTH` | Filtros e limites |
| `DEFAULT_TAGS` | Tags quando --no-llm |
| `PAUSE_EVERY_N_REQUESTS`, `PAUSE_BATCH_MIN/MAX` | Pausas para rate limit |

### Arquivo que usa LLM

| Script | Função |
|--------|--------|
| `05_tag_conversations.py` | Classifica conversas (tipo, tags, tipo_consulta, anonimização) |

### Onde a chave é lida

**Arquivo:** `config.py` → `LLM_PROVIDERS`

O script lê a chave das variáveis de ambiente. Não há lugar no código para colar a chave diretamente — use variáveis de ambiente.

### Variáveis de ambiente

| Variável | Provedor | Onde obter |
|----------|----------|------------|
| `DEEPSEEK_API_KEY` | DeepSeek (padrão) | [platform.deepseek.com](https://platform.deepseek.com) |
| `OPENAI_API_KEY` | GPT | [platform.openai.com](https://platform.openai.com) |

Defina **uma** das duas. O script usa DeepSeek por padrão (`--provider deepseek`).

### Como configurar

**Opção 1 — No terminal (sessão atual):**
```bash
export DEEPSEEK_API_KEY="sua-chave-aqui"
# ou
export OPENAI_API_KEY="sua-chave-aqui"
```

**Opção 2 — Arquivo `.env` na pasta do projeto:**
```bash
# CURADORIA CHATGPT/.env
DEEPSEEK_API_KEY=sua-chave-aqui
# ou
OPENAI_API_KEY=sua-chave-aqui
```

Se usar `.env`, carregue antes de rodar (ex.: `source .env` ou `pip install python-dotenv` e carregue no script).

**Opção 3 — Sem configurar:** o script detecta a ausência da chave e usa `--no-llm` automaticamente (tags padrão).

> **Segurança:** não commite o arquivo `.env` ou chaves no repositório. Adicione `.env` ao `.gitignore`.

### Exemplos de uso (05_tag_conversations)

```bash
# Defina a variável antes (opcional — sem ela usa --no-llm)
export DEEPSEEK_API_KEY="sua-chave"

# Gerar tudo com DeepSeek (padrão)
python 05_tag_conversations.py --provider deepseek

# Gerar com GPT
export OPENAI_API_KEY="sk-..."
python 05_tag_conversations.py --provider gpt

# Testar com apenas 10 segmentos
python 05_tag_conversations.py --provider deepseek --limit 10

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

## Pipeline

> **Documentação detalhada do `01_extract_chatgpt_dataset.py`:** [README.01_extract_chatgpt_dataset.md](README.01_extract_chatgpt_dataset.md)

```
01_extract_chatgpt_dataset  →  data/raw/conversations-*.json
02_dataset_filter          →  data/processed/02_chatgpt_filtered.jsonl
03_detect_question_boundaries → data/processed/03_chatgpt_questions.jsonl
04_quality_scoring         →  data/processed/04_scored_segments.jsonl
05_tag_conversations       →  data/processed/05_tagged_segments.jsonl
06_format_for_training     →  06_llm_training_dataset.jsonl
```

---

## Filtros (02_dataset_filter)

> **Documentação detalhada do `02_dataset_filter.py`:** [README.02_dataset_filter.md](README.02_dataset_filter.md)

| Filtro | Descrição |
|--------|-----------|
| **melhore texto** | Remove pedidos genéricos de edição (melhore o texto, melhore este texto) |
| **codigo** | Remove pedidos de código (n8n, JSON, conversões, hotsite, site) |
| **similaridade** | Remove segmentos onde pergunta e resposta são muito parecidas (TF-IDF ≥ 0.7) |
| **deduplicação** | Remove duplicatas exatas e aproximadas entre segmentos (TF-IDF ≥ 0.95) |
| **leituras** | Marcadas com `fonte: "leitura_gpt"` (campo/vibracional/profética/dinâmica) |

**Desativados:** smalltalk e personal — segmentos com cumprimentos (oi, kkkk) ou menções a terceiros (meu amigo, fala pra ela) são **mantidos**.

---

## Formato de saída (06_llm_training_dataset.jsonl)

Igual ao `data/final/dataset.jsonl` da curadoria da Bíblia (padrão para refine/treino):

```json
{
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

---

## Execução

```bash
# Pipeline completo (01 → 06). 05 usa LLM se API key estiver definida.
python run_pipeline.py

# Scripts individuais
python 01_extract_chatgpt_dataset.py
python 02_dataset_filter.py
python 03_detect_question_boundaries.py
python 04_quality_scoring.py
python 05_tag_conversations.py --provider deepseek   # classificação via LLM
python 05_tag_conversations.py --no-llm             # tags padrão (sem API, sem chave)
python 05_tag_conversations.py --resume             # continuar de onde parou
python 05_tag_conversations.py --limit 5            # testar com 5 segmentos
python 06_format_for_training.py
```

---

## Classificação via LLM (05_tag_conversations)

> **Documentação detalhada do `05_tag_conversations.py`:** [README.05_tag_conversations.md](README.05_tag_conversations.md)

O script 05 é o **único** que consulta LLM na curadoria ChatGPT. Classifica cada conversa em:

| Campo | Descrição |
|-------|-----------|
| **tipo** | "leitura" ou "conversa" |
| **genero** | narrativa, poesia, conversa, explicativo, criativo, dialogo, etc. |
| **funcao** | historica, espiritual, educacional, pratica, conselho, acolhimento, etc. |
| **tom** | reflexivo, contemplativo, poetico, pratico, formal, informal, conselheira, campo |
| **tipo_consulta** | (se leitura) ansiedade, relacionamento, propósito, trabalho, transição, saúde, espiritual |
| **contexto_anonimo** | (se leitura) frase genérica para anonimização |
| **user_anonimizado** | (se leitura) pergunta reescrita com "uma pessoa" + tema genérico na própria pergunta |
| **nome_remover** | (se leitura) nome(s) da pessoa a substituir na resposta do assistant por "a pessoa" |

**Provedores:** `--provider deepseek` (padrão) ou `gpt`. Se nenhuma API key estiver definida, usa tags padrão automaticamente.

---

## Com LLM vs Sem LLM

Os **filtros** (02, 05, 06) são aplicados **sempre**, com ou sem LLM. O que muda é apenas a **classificação** (tags), feita no script 05.

### Com LLM (API key configurada)

| O que | Descrição |
|-------|-----------|
| **Classificação** | LLM analisa cada conversa e preenche: tipo, genero, funcao, tom, tipo_consulta, contexto_anonimo, user_anonimizado |
| **Leituras** | LLM identifica tipo "leitura", classifica tipo_consulta (ansiedade, relacionamento, etc.) e reescreve a pergunta do user (anonimização) |
| **Filtros** | 02 (smalltalk, personal, melhore texto, codigo, short) → 05 (quality_score ≥ 0.55) → 06 (quality_score ≥ 0.55) |

### Sem LLM (`--no-llm` ou sem API key)

| O que | Descrição |
|-------|-----------|
| **Classificação** | Tags padrão: `genero: ["conversa"], funcao: ["educacional"], tom: ["reflexivo"]` |
| **Leituras** | Se detectadas no 02 (keywords): tags `genero: ["dialogo"], funcao: ["conselho", "acolhimento"], tom: ["conselheira"]`. **Sem** anonimização (user_anonimizado fica null) |
| **Filtros** | **Mesmos** do 02, 05 e 06. Nada é carregado por completo — smalltalk, personal, melhore texto, codigo, short e quality_score &lt; 0.55 continuam removidos |

---

## Leituras de campo

Conversas de **leitura de campo**, **vibracional**, **profética** ou **dinâmica de pessoas** são:

- **Detectadas** no 02 (keywords) e **não** removidas como "personal"
- **Com LLM**: tipo, tipo_consulta, contexto_anonimo, user_anonimizado (pergunta com "uma pessoa" + tema genérico), nome_remover (substituído na resposta por "a pessoa")
- **Sem LLM**: tags padrão de leitura (dialogo, conselho, acolhimento) — **sem** anonimização
- **Metadata**: fonte=leitura_gpt, contexto_anonimo, tipo_consulta, campos_removidos

Exemplo de saída para leitura:

```json
{
  "fonte": "leitura_gpt",
  "tipo": "leitura",
  "tipo_consulta": "transição",
  "contexto_anonimo": "pessoa em transição profissional",
  "anonimizado": true,
  "metadata": {"genero_consulta": "transição", "tom_resposta": "conselheira", "campos_removidos": ["nome", "localizacao"]},
  "tags": {"genero": ["dialogo"], "funcao": ["conselho", "acolhimento"], "tom": ["conselheira"]},
  "messages": [...]
}
```
