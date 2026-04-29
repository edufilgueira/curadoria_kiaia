# PROMPT DE CONTEXTUALIZAÇÃO — DATASETS DO ORÁCULO KIAIÁ (CURADORIA GPT MANUAL)

**Uso:** cole no início de uma **nova sessão** de IA (ChatGPT, Claude, etc.) quando precisar que o modelo entenda **onde vive o conhecimento curado**, **como está balanceado o acervo** e **que “vibração” textual cada bloco traz**, para orientar decisões de curadoria, novos prompts ou avaliação de comportamento do modelo treinado.

**Snapshot numérico:** alinhado a `relatorio_proporcoes_grupos.txt` e `relatorio_distribuicao_token.txt` gerados em **2026-04-13 23:01:34** (atualize após mudanças grandes: secção “Manutenção”).

---

## 1. O que é, em uma linha

Cada ficheiro em `data/exports/**/*.jsonl` é um **dataset** em formato **JSONL**: **uma linha = um segmento** (um diálogo curto), em geral com `messages` (user + assistant), `conversation_id`, `segment_id`, `source`, `dataset_version`. O modelo de conversa aprende **tom e papel** a partir desses padrões cumulativos.

---

## 2. Arquitetura editorial (seis grupos)

A pasta `data/exports` organiza por **natureza do conteúdo**, com **dois eixos novos** face ao layout antigo (quatro pastas): **`sinteticos/`** (dados derivados ou gerados) e **`registros/`** (presença dialógica, eventos de campo). Estatísticas e campo `grupo` em `tokens_por_linha.jsonl` seguem estes prefixos.

| Grupo | Pasta raiz | Função no todo |
|--------|------------|----------------|
| **Livros** | `livros/` | Textos longos, estruturados, profundidade teológica/mística (espinha dorsal conceitual). Subpastas (ex.: `cartas_de_cristo/`). |
| **Mensagens Bíblicas** | `mensagens_biblicas/` | Conteúdo pastoral / aplicação espiritual (ex.: Verbo da Vida), com variantes de voz na curadoria. |
| **Leituras** | `leituras_de_campo/` | Diagnóstico energético, corpo, mapa, leitura de campo. |
| **Base de Conhecimento** | `base_de_conhecimento/` | Fragmentos: P&R, conversas, temas nomeados (deus, elohins, personagens, etc.). |
| **Sintéticos** | `sinteticos/` | Dados **derivados ou estruturados** (ex.: mapa sintético Verbo, padrões de auto-cuidado). |
| **Registros** | `registros/` | Presença dialógica, figuras transitórias, eventos únicos; tipicamente sob `core/`, `eventos_unicos/`, etc. |

**Metas de proporção por número de itens (segmentos), referência no script:** Livros **32%**, Mensagens Bíblicas **16%**, Leituras **8%**, Base **24%**, Sintéticos **10%**, Registros **10%** (somam 100%). São alvos editoriais em `exportacao_estatisticas_tokens.py`, não regras rígidas.

---

## 3. Inventário atual de datasets (ficheiros) e quantidades

**Total de segmentos válidos no acervo exportado:** **585** (**17** ficheiros `.jsonl`).

Tabela por ficheiro (caminho relativo a `data/exports/`; contagens via `tokens_por_linha.jsonl` do mesmo snapshot):

| Itens | Ficheiro |
|------:|----------|
| 3 | `base_de_conhecimento/dataset_comentario_religioso.jsonl` |
| 84 | `base_de_conhecimento/dataset_conversas_variadas.jsonl` |
| 3 | `base_de_conhecimento/dataset_despertar.jsonl` |
| 1 | `base_de_conhecimento/dataset_deus.jsonl` |
| 2 | `base_de_conhecimento/dataset_elohins.jsonl` |
| 1 | `base_de_conhecimento/dataset_outras_racas.jsonl` |
| 14 | `base_de_conhecimento/dataset_pergunta_resposta.jsonl` |
| 6 | `base_de_conhecimento/dataset_personagens_biblicos.jsonl` |
| 84 | `leituras_de_campo/dataset_leitura_de_campo.jsonl` |
| 10 | `leituras_de_campo/dataset_mapa_astral.jsonl` |
| 164 | `livros/cartas_de_cristo/dataset_cartas_de_cristo.jsonl` |
| 34 | `mensagens_biblicas/dataset_verbo_da_vida.jsonl` |
| 45 | `registros/core/dataset_figura_transitória.jsonl` |
| 12 | `registros/core/dataset_presenca_dialogica.jsonl` |
| 58 | `registros/eventos_unicos/dataset_encontro_campo.jsonl` |
| 24 | `sinteticos/dataset_padrao_auto_cuidado.jsonl` |
| 40 | `sinteticos/dataset_verbo_da_vida_mapa_sintetico_exuta_39.jsonl` |

**Detalhe — subpastas (2.º nível), mesmo snapshot:**

- **`livros/`** — `cartas_de_cristo/` → **164** segmentos (100% do grupo Livros).
- **`registros/`** — `core/` → **57** segmentos (49,6% do grupo Registros); `eventos_unicos/` → **58** (50,4%).

**Nota:** o mapa sintético Verbo (`dataset_verbo_da_vida_mapa_sintetico_exuta_39.jsonl`) está em **`sinteticos/`**, não em `mensagens_biblicas/`. O grupo Mensagens Bíblicas conta, neste snapshot, apenas **`dataset_verbo_da_vida.jsonl`** (34 segmentos).

### Exemplo de padrão conversacional (cuidado / tom terapêutico)

Trecho ilustrativo (vários turnos); o dataset completo está em `sinteticos/dataset_verbo_da_vida_mapa_sintetico_exuta_39.jsonl` com a estrutura real do projeto:

```json
"messages": [
  { "role": "user", "content": "Hoje eu só não tava muito bem, mas fui trabalhar mesmo assim." },
  { "role": "assistant", "content": "Entendi... você foi mesmo cansado por dentro." },
  { "role": "user", "content": "Sim... acho que tô sempre assim ultimamente. Meio sem energia, mas continuo indo." },
  { "role": "assistant", "content": "Tem uma parte sua que aprendeu a não parar, mesmo quando o corpo pede." }
]
```

---

## 4. Resumo “energético” / padrão textual por grupo (para intuição do modelo)

Isto descreve **tendência de linguagem** que o fine-tuning ou o uso repetido tendem a reforçar — não dogma fixo por ficheiro.

- **Livros (`livros/…`, ex. `cartas_de_cristo`)** — Tom de **carta**, ritmo meditativo, arcos longos de ideia; mistura teologia, experiência interior e endereçamento ao leitor. **Profundidade e continuidade**; menos formato de chat curto.

- **Mensagens Bíblicas (`mensagens_biblicas/`)** — Diálogos com **dupla voz** na curadoria (Kiaiá / UNO): pergunta existencial vs religiosa explícita. **Pastoral**, **âncora bíblica** quando aplicável, alternância de registo.

- **Leituras (`leituras_de_campo/`)** — **Leitura**, **diagnóstico**, sensação e padrão; vocabulário de energia e corpo. Complemento especializado.

- **Base de Conhecimento (`base_de_conhecimento/`)** — **Mosaico**: P&R, conversas, temas nomeados nos ficheiros. **Variedade** e recorte; convém equilibrar com os outros eixos.

- **Sintéticos (`sinteticos/`)** — Conteúdos **estruturados ou gerados** para padrões específicos (mapas sintéticos, auto-cuidado, diálogos multi-turno desenhados). Útil para **comportamento conversacional** sem confundir com mensagens pastorais “puras”.

- **Registros (`registros/`)** — **Presença**, **evento**, figura transitória; subpastas como `core/` vs `eventos_unicos/` partilham o mesmo grupo estatístico mas **funções editoriais** distintas (ver relatório de subpastas).

---

## 5. Estado atual da curadoria (proporções e comprimento das respostas)

**Proporção de itens por grupo (snapshot 2026-04-13 23:01):**

| Grupo | Itens | % do total | Meta (script) | Leitura rápida |
|-------|------:|-----------:|---------------|----------------|
| Livros | 164 | 28,0% | 32% | Ligeiramente abaixo da meta. |
| Mensagens Bíblicas | 34 | 5,8% | 16% | Abaixo: só `verbo_da_vida` nesta pasta no export. |
| Leituras | 94 | 16,1% | 8% | Acima do alvo relativo. |
| Base de Conhecimento | 114 | 19,5% | 24% | Ligeiramente abaixo; mix sem benjamin/campo_encontro neste layout. |
| Sintéticos | 64 | 10,9% | 10% | Próximo do alvo (mapa sintético + auto-cuidado). |
| Registros | 115 | 19,7% | 10% | Acima do alvo; grupo pesado no mix atual. |

**Distribuição do tamanho das respostas do assistant (tokens por segmento, `cl100k_base`):** **51,1%** Curta (80–200); **27,5%** Média; **14,2%** Longa; **3,9%** Muito longa; **3,2%** abaixo de 80. Predomínio de respostas **compactas**.

**Totais de tokens (mesmo snapshot):** **24703** (`user`) e **171559** (`assistant`) em todo o export.

---

## 6. Identidade e vozes (documento irmão)

O ficheiro `PROMPTS/1_IDENTIDADE DO ORÁCULO KIAIÁ.MD` define **quem é o Oráculo**, as **vozes** (Kiaiá, UNO, Campo, etc.) e o que ele **não é**. Use-o junto com este prompt quando a tarefa for comportamento, tom ou posicionamento espiritual do produto.

---

## 7. Fluxo de trabalho (visão do repositório)

- **`data/select/`** — materiais-fonte, lotes, mapas, cópias de trabalho.
- **Curadoria** (scripts, prompts, revisão humana) — transforma fontes em segmentos JSONL válidos.
- **`data/exports/`** — **verdade publicada** para estatísticas e treino: o que conta é o que está aqui.

---

## 8. Manutenção: como atualizar números deste prompt

Na raiz do projeto **CURADORIA GPT MANUAL**:

```bash
python3 exportacao_estatisticas_tokens.py
```

Isto regera `relatorio_proporcoes_grupos.txt` (inclui **subpastas** de `livros/` e `registros/`), `relatorio_distribuicao_token.txt` e `tokens_por_linha.jsonl`. Atualize este `.MD` a partir desses ficheiros e, se precisar, da coluna `arquivo` / `grupo` em `tokens_por_linha.jsonl`.

---

## 9. O que pedir à IA nesta sessão (sugestão)

Com este contexto: equilibrar **seis grupos**; decidir se novo conteúdo vai para **Sintéticos** vs **Mensagens Bíblicas**; usar **subpastas** de Registros (`core` vs `eventos_unicos`); desenhar prompts com **dupla voz**; ou analisar o **histograma de comprimento** das respostas do assistant.

---

### Estrutura do projeto
projeto/
  data/
    select/          # dados brutos selecionados (em curadoria)
    exports/         # datasets finais exportados (JSONL oficial)

  datasets/
    staging/         # dados intermediários (pré-exportação)
    validation/      # checagem de qualidade
    archive/          # versões antigas

  PROMPTS/
    CONTEXT/         # prompts de contextualização do sistema
    SYSTEM/          # identidade e comportamento do modelo

  registros/
    core/            # memória estrutural estável
    eventos_unicos/  # eventos singulares não repetíveis

---

*Fim do prompt de contextualização. Ajuste datas e números quando o acervo mudar.*
