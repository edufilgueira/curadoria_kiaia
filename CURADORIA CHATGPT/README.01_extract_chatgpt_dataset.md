# Documentação: `01_extract_chatgpt_dataset.py`

Documentação completa do script que extrai e segmenta conversas dos exports do ChatGPT. É o **primeiro passo** do pipeline de curadoria.

---

## 1. Objetivo

O script lê arquivos de export do ChatGPT (`conversations-*.json`), percorre o grafo de mensagens, reconstrói as cadeias de diálogo, segmenta por turnos user/assistant e grava o resultado em JSONL. Cada linha da saída é um segmento pronto para os filtros do passo 02.

---

## 2. Arquivos envolvidos

| Constante | Valor | Descrição |
|-----------|-------|-----------|
| `INPUT_DIR` | `data/raw` | Diretório dos exports do ChatGPT |
| `OUTPUT_FILE` | `data/processed/01_chatgpt_segments.jsonl` | Saída em JSONL (uma linha por segmento) |

O script procura por `conversations*.json` em `INPUT_DIR` (ex.: `conversations-000.json`, `conversations-001.json`), ordenados por nome.

---

## 3. Dependências

- **Python 3.x**
- Bibliotecas padrão: `json`, `re`, `uuid`, `pathlib`

Sem dependências externas (pip).

---

## 4. Fluxo principal (`main`)

```
1. Cria INPUT_DIR e OUTPUT_FILE.parent se não existirem
2. Lista arquivos: sorted(INPUT_DIR.glob("conversations*.json"))
3. Se vazio → imprime aviso e retorna
4. Abre OUTPUT_FILE em modo "w" (sobrescreve)
5. Para cada arquivo:
   - Carrega JSON
   - Se for lista → conversations = data
   - Se for objeto → conversations = [data]
   - Para cada conversa: process_conversation(convo, out)
6. Imprime total de segmentos extraídos
```

---

## 5. Funções e regras de importação

### 5.1 `normalize(text)` — linhas 12–20

Normaliza o texto antes de gravar.

| Entrada | Comportamento |
|---------|---------------|
| Não é `str` | Retorna `""` |
| É `str` | `strip()` + `re.sub(r"\s+", " ", text)` (colapsa espaços múltiplos em um) |

---

### 5.2 `get_text_from_message(msg)` — linhas 23–45

Extrai o texto de uma mensagem do export.

| Condição | Retorno |
|----------|---------|
| `msg` é falsy | `""` |
| `msg.content` ausente | `""` |
| `msg.content.parts` ausente ou vazio | `""` |
| `parts[0]` é string | `normalize(parts[0])` |
| `parts[0]` é dict | `normalize(parts[0].get("text", ""))` |
| Outro tipo | `""` |

**Regra:** Usa apenas o **primeiro** elemento de `parts`. Imagens e outros tipos de part são ignorados.

---

### 5.3 `find_leaf_nodes(mapping)` — linhas 129–145

Identifica nós folha (fim de ramo) no grafo.

```
children = set()
para cada node em mapping.values():
  se node.parent existe:
    children.add(node.parent)

leaves = []
para cada node_id em mapping:
  se node_id NÃO está em children:
    leaves.append(node_id)
return leaves
```

**Regra:** Nó folha = nó que não é referenciado como `parent` por nenhum outro. Cada folha é o final de um ramo da conversa (bifurcações do ChatGPT).

---

### 5.4 `reconstruct_conversation(mapping, leaf)` — linhas 49–79

Reconstrói a cadeia de mensagens subindo do nó folha até a raiz.

```
chain = []
node = mapping[leaf]
enquanto node existe:
  msg = node.message
  role = msg.author.role
  text = get_text_from_message(msg)
  se role in ["user", "assistant"] E text não vazio:
    chain.append({role, content: text})
  parent = node.parent
  se não parent: break
  node = mapping[parent]

chain.reverse()  // ordem cronológica (raiz → folha)
return chain
```

**Regras de importação:**
- Apenas `role` = `user` ou `assistant` são incluídos
- Mensagens `system` ou com texto vazio são ignoradas
- A ordem final é cronológica (primeira mensagem primeiro)

---

### 5.5 `segment_conversation(chain)` — linhas 82–101

Divide a cadeia em segmentos a cada nova mensagem do usuário.

```
segments = []
buffer = []
para cada msg em chain:
  se msg.role == "user":
    se buffer não vazio:
      segments.append(buffer)
      buffer = []
  buffer.append(msg)
se buffer não vazio:
  segments.append(buffer)
return segments
```

**Regra:** Um segmento = bloco que termina quando aparece o próximo `user`. Exemplo:

- Cadeia: `[user1, asst1, user2, asst2]`
- Segmentos: `[[user1, asst1], [user2, asst2]]`

Segmentos com múltiplos turnos (vários user/assistant) são permitidos.

---

### 5.6 `detect_reasoning(segment)` — linhas 104–126

Classifica o segmento como explicativo ou não.

Concatena todo o texto do segmento (user + assistant), converte para minúsculas e verifica se contém alguma destas palavras:

| Português | Inglês |
|-----------|--------|
| por que, explique, como funciona, demonstre, passo a passo, raciocínio | why, explain, how does, step by step |

| Retorno | Condição |
|---------|----------|
| `"explanation"` | Alguma palavra encontrada |
| `"none"` | Nenhuma encontrada |

---

### 5.7 `process_conversation(convo, output_file)` — linhas 148–187

Processa uma conversa e grava os segmentos no arquivo de saída.

```
mapping = convo.mapping
conversation_id = convo.id ou uuid4()
se não mapping: return 0

leaves = find_leaf_nodes(mapping)
seg_index = 0
count = 0

para cada leaf em leaves:
  chain = reconstruct_conversation(mapping, leaf)
  segments = segment_conversation(chain)
  para cada seg em segments:
    se seg vazio: continue
    seg_index += 1
    dataset_item = {
      conversation_id, segment_id, messages, turn_count,
      reasoning_hint, source, dataset_version
    }
    out.write(json.dumps(dataset_item, ensure_ascii=False) + "\n")
    count += 1

return count
```

**`segment_id`:** `{conversation_id}_{seg_index}`. O `seg_index` é global para a conversa (todas as folhas).

---

## 6. Formato de entrada (export do ChatGPT)

### Estrutura esperada

Cada arquivo em `data/raw/` pode ser:

- **Lista:** `[{conversa1}, {conversa2}, ...]`
- **Objeto único:** `{conversa}`

Cada conversa:

```json
{
  "id": "uuid",
  "mapping": {
    "node-id": {
      "id": "node-id",
      "parent": "id-do-pai",
      "children": ["id-filho"],
      "message": {
        "author": {"role": "user" | "assistant" | "system"},
        "content": {
          "content_type": "text",
          "parts": ["texto"]  // ou [{"text": "..."}]
        }
      }
    }
  }
}
```

### Campos usados pelo script

| Caminho | Uso |
|---------|-----|
| `convo.id` | `conversation_id` (fallback: `uuid4()`) |
| `convo.mapping` | Grafo de nós |
| `node.parent` | Navegação para a raiz |
| `node.message.author.role` | Filtro: só `user` e `assistant` |
| `node.message.content.parts[0]` | Texto (string ou `dict["text"]`) |

---

## 7. Formato de saída (cada linha do JSONL)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `conversation_id` | string | UUID da conversa |
| `segment_id` | string | `{conversation_id}_{índice}` |
| `messages` | array | `[{role, content}, ...]` |
| `turn_count` | int | `len(messages)` |
| `reasoning_hint` | string | `"explanation"` ou `"none"` |
| `source` | string | `"chatgpt_export"` |
| `dataset_version` | string | `"v1"` |

---

## 8. Resumo das regras de importação

| Regra | Descrição |
|-------|-----------|
| **Arquivos** | `data/raw/conversations*.json` (ordenados por nome) |
| **Formato** | Lista ou objeto único de conversas |
| **Folhas** | Apenas nós que não são `parent` de ninguém |
| **Cadeia** | Reconstruída subindo por `parent` até a raiz |
| **Roles** | Apenas `user` e `assistant` |
| **Texto** | Primeiro `part`; string ou `part["text"]` |
| **Normalização** | `strip` + colapso de espaços |
| **Segmentação** | Corte a cada nova mensagem `user` |
| **Segmentos vazios** | Ignorados (não gravados) |
| **reasoning_hint** | Palavras-chave no texto concatenado |

---

## 9. O que é incluído e excluído

### Incluído

- Mensagens `user` e `assistant` com texto não vazio
- Primeiro `part` de cada mensagem
- Todos os ramos (cada folha gera seus segmentos)
- Segmentos com múltiplos turnos

### Excluído

- Mensagens `system`
- Mensagens com texto vazio após normalização
- Nós sem `message` ou sem `content.parts` válido
- Partes além da primeira (imagens, etc.)
- Segmentos vazios após segmentação

---

## 10. Execução

```bash
cd CURADORIA CHATGPT
python 01_extract_chatgpt_dataset.py
```

**Saída no terminal:**
```
Found N conversation files

Processing: conversations-000.json
Processing: conversations-001.json
...

Extraction complete
Segments extracted: XXXX
Saved to: data/processed/01_chatgpt_segments.jsonl
```

---

## 11. Próximo passo no pipeline

O arquivo `01_chatgpt_segments.jsonl` é a entrada do `02_dataset_filter.py`, que aplica filtros (smalltalk, personal, melhore texto, código, tamanho mínimo).
