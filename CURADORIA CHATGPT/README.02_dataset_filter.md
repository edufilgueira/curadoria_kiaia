# Documentação: `02_dataset_filter.py`

Documentação completa do script que aplica filtros aos segmentos extraídos do ChatGPT. Remove melhore texto, código e segmentos com estrutura inválida. **Exceção:** leituras de campo/vibracional/profética/dinâmica são marcadas com `fonte: "leitura_gpt"`.

**Filtros desativados:** smalltalk e personal não são mais removidos — segmentos com cumprimentos (oi, kkkk) ou menções a terceiros (meu amigo, fala pra ela) são mantidos.

**Foi filtrado manualmente** textos que contem o padrão: *Eu não tenho como saber o que ele está sentindo ou esperando internamente. Não tenho acesso à expectativa dele em tempo real.*

1) Eu não tenho como saber com certeza absoluta o que estava passando na mente do Garibaldi
2) sobre analisar o campo energético dela e a possibilidade de “rodear” (influenciar ou proteger) essa pessoa, minha resposta precisa ser clara e direta:\n\nEu não tenho acesso direto a campos energéticos reais de pessoas.
3) Na verdade, não. Eu não tenho acesso a nenhum tipo de “campo” espiritual, energético ou fora da informação que possa ser **explicitamente fornecida ou publicamente registrada**.
4) Eu não tenho como ler o pensamento ou o “campo” de outra pessoa,
5) Antes de tudo, vale reforçar: eu não tenho como “ler” energia literal ou espiritual de alguém;
---

## 1. Objetivo

O script lê `01_chatgpt_segments.jsonl`, aplica filtros e grava em `02_chatgpt_filtered.jsonl` apenas os segmentos que passam. O objetivo é eliminar edição genérica, código, segmentos com pergunta/resposta muito parecidas (similaridade), duplicatas (exatas e aproximadas) e trechos com estrutura inválida, mantendo o que é útil para treino de LLM.

---

## 2. Arquivos envolvidos

| Constante | Valor | Descrição |
|-----------|-------|-----------|
| `INPUT_FILE` | `data/processed/01_chatgpt_segments.jsonl` | Saída do script 01 |
| `OUTPUT_FILE` | `data/processed/02_chatgpt_filtered.jsonl` | Segmentos filtrados |
| `REPORT_FILE` | `data/processed/02_chatgpt_filtered.txt` | Relatório: mantidos + removidos (para controle/verificação) |

---

## 3. Dependências

- **Python 3.x**
- Bibliotecas padrão: `json`, `pathlib`
- **scikit-learn** (filtro de similaridade): `pip install scikit-learn`

---

## 4. Constantes e listas de padrões

### 4.1 LEITURA_PATTERNS

Padrões que indicam **leitura de campo, vibracional, profética ou dinâmica**. Segmentos com esses padrões recebem `fonte: "leitura_gpt"`.

```
leitura de campo, leitura vibracional, leitura profética, leitura profetica,
leitura de dinâmica, leitura de dinamica, dinâmica de , dinamica de ,
analisa o campo, analisa a dinâmica, analisa a dinamica, faz a leitura,
faz a leitura de, pedindo a leitura, pedindo leitura, pessoa tal, pessoa fulano,
leitura dela, leitura dele
```

**Nota:** `dinâmica de ` (com espaço) evita falsos positivos como "interdisciplinar".

### 4.2 MELHORE_TEXTO_PATTERNS

Padrões de **pedidos genéricos de edição de texto**. Remove.

```
melhore o texto, melhore este texto, como fazer chantilly, melhore o ,
mude o texto, altere o texto, melhore este tesdto, melhore este testo,
logotipo do site, coxinha
```

### 4.3 CODIGO_PATTERNS

Padrões de **pedidos de código, n8n, JSON, conversões técnicas**. Remove.

```
n8n, $input.first, $input.first().json, organize esse json, organiza esse json,
organize esse objeto, organiza esse objeto, organiza 400, organize 400,
converta para inteiro, converta para float, converta para string, gere código,
gerar código, crie um hotsite, crie um site, $(', base64, pixQrCode, decodifique,
docker, ruby, rails, rspec, "role, calcule o intervalo, tenho uma data
```

**Regra:** A verificação usa **user + assistant** — padrões como `"role` aparecem na resposta (JSON com role).

### 4.4 SIMILARITY_THRESHOLD e DEDUP_THRESHOLD

| Constante | Valor | Uso |
|-----------|-------|-----|
| **SIMILARITY_THRESHOLD** | `0.8` | Similaridade **pergunta vs resposta** (dentro do mesmo segmento). Se ≥ 0.8, remove — pergunta e resposta muito parecidas (ex.: "organize esse json" → resposta ecoa). |
| **DEDUP_THRESHOLD** | `0.95` | Similaridade **segmento vs outros segmentos**. Se ≥ 0.95 com algum já mantido, remove — duplicata aproximada. Mantém sempre o primeiro. |

**Diferença:** `SIMILARITY_THRESHOLD` compara user e assistant do *mesmo* segmento; `DEDUP_THRESHOLD` compara segmentos *entre si* (conteúdo user+assistant concatenado).

---

## 5. Funções e regras de filtro

### 5.1 `contains_pattern(text, patterns)`

Verifica se o texto (em minúsculas) contém algum dos padrões.

```
text = text.lower()
para cada p em patterns:
  se p in text: return True
return False
```

---

### 5.2 `is_leitura(segment)`

Detecta leituras de campo/vibracional/profética/dinâmica.

| Escopo | Apenas mensagens `user` |
|--------|-------------------------|
| Verificação | `contains_pattern(text, LEITURA_PATTERNS)` |

**Uso:** Se `True`, o segmento recebe `fonte: "leitura_gpt"`.

---

### 5.3 `is_melhore_texto(segment)`

Remove pedidos genéricos de edição.

| Escopo | Apenas mensagens `user` |
|--------|-------------------------|
| Verificação | `contains_pattern(text, MELHORE_TEXTO_PATTERNS)` |

---

### 5.4 `is_codigo(segment)`

Remove pedidos de código e conversões técnicas.

| Escopo | **Todas** as mensagens (user + assistant) |
|--------|--------------------------------------------|
| Verificação | `contains_pattern(text, CODIGO_PATTERNS)` |

**Motivo:** Padrões como `"role` aparecem na resposta (JSON com role).

---

### 5.5 Similaridade (pergunta vs resposta)

Remove segmentos onde pergunta e resposta são muito parecidas (ex.: "organize esse json" → resposta com JSON organizado).

| Método | TF-IDF + cosine_similarity |
|--------|----------------------------|
| Constante | `SIMILARITY_THRESHOLD` (padrão 0.8) |
| Regra | ≥ threshold → remove |
| Escopo | Compara texto user vs texto assistant (mesmo segmento) |

**Requer:** `pip install scikit-learn`

---

### 5.6 Deduplicação (entre segmentos)

Remove segmentos com conteúdo idêntico ou muito parecido entre si. Evita repetições como "Ah, meu amor, que história gostosa..." aparecendo em várias linhas.

| Fase | Método | Descrição |
|------|--------|-----------|
| **1. Exata** | Texto normalizado (lower + strip) em set | Se o texto user+assistant já apareceu, remove |
| **2. Aproximada** | TF-IDF + cosine_similarity ≥ `DEDUP_THRESHOLD` (0.95) | Se similar a algum segmento já mantido, remove |

**Ordem:** Primeiro remove duplicatas exatas; depois aplica similaridade nos restantes. Mantém sempre o **primeiro** de cada grupo.

---

### 5.7 `valid_structure(messages)`

Valida a estrutura mínima do segmento.

| Condição | Retorno |
|----------|---------|
| `messages` vazio | `False` |
| Primeira mensagem não é `user` | `False` |
| Nenhuma mensagem com `role` = `assistant` | `False` |
| Caso contrário | `True` |

---

## 6. Ordem de aplicação dos filtros

O script aplica os filtros **na ordem abaixo**. O primeiro que der `True` remove o segmento (sem gravar).

```
1. valid_structure(messages)   → remove se inválido
2. is_melhore_texto(messages)  → remove
3. is_codigo(messages)         → remove
4. similaridade (user vs assistant) ≥ SIMILARITY_THRESHOLD (0.8) → remove
5. is_leitura(messages)        → NÃO remove; adiciona item["fonte"] = "leitura_gpt"
6. deduplicação exata         → remove se texto user+assistant já existir
7. deduplicação aproximada    → remove se similaridade ≥ DEDUP_THRESHOLD (0.95) a segmento já mantido
8. grava no arquivo + relatório 02_chatgpt_filtered.txt
```

**Filtros desativados:** `is_smalltalk` e `is_personal` não são mais aplicados.

---

## 7. Fluxo principal (`main`)

```
1. Cria OUTPUT_FILE.parent se não existir
2. Abre INPUT_FILE (leitura)
3. Para cada linha do JSONL:
   - item = json.loads(line)
   - messages = item.get("messages", [])
   - Se valid_structure falha → removed_structure++, continue
   - Se is_melhore_texto → removed_melhore_texto++, continue
   - Se is_codigo → removed_codigo++, continue
   - Se similaridade user/assistant ≥ SIMILARITY_THRESHOLD → removed_similar++, continue
   - Se is_leitura → item["fonte"] = "leitura_gpt"
   - Acumula item em items_passed
4. Deduplicação:
   - Exata: remove se texto (user+assistant) normalizado já visto
   - Aproximada: TF-IDF + cosine ≥ DEDUP_THRESHOLD com segmentos já mantidos
5. Grava itens deduplicados em 02_chatgpt_filtered.jsonl
6. Grava relatório (mantidos + removidos) em 02_chatgpt_filtered.txt
7. Imprime contadores (kept, removed_*, leituras)
```

---

## 8. Formato de saída

Cada linha mantém a estrutura do JSON de entrada, com possível adição:

| Campo | Quando aparece |
|-------|----------------|
| `fonte` | `"leitura_gpt"` — apenas se `is_leitura` for `True` |

Campos originais preservados: `conversation_id`, `segment_id`, `messages`, `turn_count`, `reasoning_hint`, `source`, `dataset_version`.

### 8.1 Relatório `02_chatgpt_filtered.txt`

O script gera também um relatório em texto para controle e verificação do que foi mantido e removido.

| Seção | Conteúdo |
|-------|----------|
| **RESUMO** | Total lido, mantidos, removidos por estrutura, melhore_texto, codigo, similaridade, dedup exata, dedup aproximada |
| **MANTIDOS** | Lista de `segment_id` dos segmentos que passaram em todos os filtros |
| **REMOVIDOS: estrutura** | `segment_id`, user (preview 150 chars), assistant |
| **REMOVIDOS: melhore_texto** | Idem |
| **REMOVIDOS: codigo** | Idem |
| **REMOVIDOS: similaridade** | Idem + score (ex.: `similarity: 0.836`) |
| **REMOVIDOS: dedup exata** | Idem (conteúdo idêntico a outro) |
| **REMOVIDOS: dedup aproximada** | Idem + `sim=X.XXX` e `duplicata de: <segment_id>` |

**Uso:** Permite auditar se as remoções fazem sentido e localizar o segmento mantido para comparação em caso de dedup aproximada.

---

## 9. Resumo das regras de filtro

| Filtro | Escopo | Condição para remover |
|--------|--------|------------------------|
| **structure** | — | Mensagens vazias, ou não começa com user, ou não tem assistant |
| **melhore texto** | Apenas user | Contém "melhore o texto", "mude o texto", etc. |
| **codigo** | User + assistant | Contém n8n, JSON, hotsite, código, etc. |
| **similaridade** | User vs assistant | Cosine ≥ SIMILARITY_THRESHOLD (0.8) — pergunta e resposta muito parecidas |
| **dedup exata** | User + assistant | Texto normalizado já existe em outro segmento |
| **dedup aproximada** | User + assistant | Cosine ≥ DEDUP_THRESHOLD (0.95) com algum segmento já mantido |

**Desativados:** smalltalk e personal — segmentos com cumprimentos ou menções a terceiros são **mantidos**.

---

## 10. Leituras

Segmentos com padrões de **leitura de campo, vibracional, profética ou dinâmica**:

- Recebem `fonte: "leitura_gpt"` para identificação
- São contados separadamente no output (`kept_leituras`)

---

## 11. Execução

```bash
cd CURADORIA CHATGPT
python 02_dataset_filter.py
```

**Pré-requisito:** `01_chatgpt_segments.jsonl` existente (gerado pelo script 01).

**Saída no terminal:**
```
=== 02 Filter (estrutura + melhore texto + codigo + similaridade + deduplicação) ===

Segments kept: XXXX
  Incl. leituras (campo/vibracional/profética/dinâmica): XX
Removed melhore texto: XX
Removed codigo: XX
Removed bad structure: XX
Removed (similaridade user/assistant >= 0.8): XX
Removed (deduplicação exata): XX
Removed (deduplicação aproximada >= 0.95): XX

Saved to: data/processed/02_chatgpt_filtered.jsonl
Report (mantidos + removidos): data/processed/02_chatgpt_filtered.txt
```

---

## 12. Próximo passo no pipeline

O arquivo `02_chatgpt_filtered.jsonl` é a entrada do `03_detect_question_boundaries.py`, que detecta fronteiras de perguntas e gera `03_chatgpt_questions.jsonl`.
