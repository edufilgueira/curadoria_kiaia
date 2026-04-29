# config.py — Curadoria ChatGPT
# Configurações da LLM e prompts para 05_tag_conversations.py

# LLM: use DEEPSEEK_API_KEY ou OPENAI_API_KEY (nenhuma é obrigatória — --no-llm usa tags padrão)
LLM_PROVIDERS = {
    "gpt": {
        "env_key": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
        "base_url": None,
    },
    "deepseek": {
        "env_key": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    },
}

# Filtros e limites
MIN_SCORE = 0.36
MAX_TEXT_LENGTH = 800  # caracteres para o prompt (user + assistant)

# Tags padrão (quando --no-llm ou sem API key)
DEFAULT_TAGS = {
    "genero": ["conversa"],
    "funcao": ["educacional"],
    "tom": ["reflexivo"],
}

# Pausa a cada N requisições (evita rate limit)
PAUSE_EVERY_N_REQUESTS = 10
PAUSE_BATCH_MIN = 2   # segundos
PAUSE_BATCH_MAX = 5   # segundos

# Prompt para classificação de conversas (placeholder: {text})
PROMPT_TAG_CONVERSATION = """Analise esta conversa e classifique.

1) TIPO: Classifique em uma destas categorias:
   - leitura: pedidos de leitura específica — "faz a leitura de X", "analisa o campo de Y", "leitura de campo dela", "dinâmica de fulano"
   - pergunta_ao_campo: usuário pede para o campo responder perguntas genéricas de outras pessoas — ex: "responde pra ela", "o campo responde pra Débora", "fala pra ela"
   - conversa: perguntas gerais, explicações, pedidos de texto, etc.

2) TAGS (mesmos nomes da curadoria bíblica):
   - genero: narrativa, poesia, lei, sabedoria, profecia, ensino, epistolar, apocaliptico, filosofica, conversa, explicativo, criativo, dialogo
   - funcao: historica, espiritual, educacional, pratica, doutrinal, moral, filosofica, conselho, acolhimento
   - tom: reflexivo, contemplativo, poetico, pratico, formal, informal, conselheira, campo, Uno, AIM

3) user_melhorado_list (SEMPRE): para CADA mensagem do User, melhore a pergunta.
   Prioridade: 1) Corrija erros de gramática, semântica e torne mais legível, mantendo a intenção original.
   2) Se a pergunta NÃO for autocontida (ex: "Sim", "Quero", "Pode falar") ou tiver referências vagas (ex: "essas barreiras", "isso", "o assunto", "preparação" sem contexto, "tudo que você falou", "o que você disse", "repita isso"), REFORMULE com base na resposta do Assistant para deixar o tema explícito.
   Ao reformular, pergunte-se: "Falou o quê?", "Disse o quê?", "Repetir o quê?" — se a pergunta não especifica o conteúdo, extraia os temas principais da resposta do Assistant e inclua-os na pergunta. A pergunta deve fazer sentido sozinha.
   Ex: User "Sim, por favor, pode falar" + Asst sobre manipulação → "Pode falar sobre a manipulação via tecnologia e informação?"
   Ex: User "O arrebatamento vai nos ajudar a romper essas barreiras?" + Asst sobre domo, controle → "O arrebatamento vai nos ajudar a romper as barreiras de controle e manipulação?"
   Ex: User "Sim, que preparação eu tenho que fazer?" + Asst sobre romper domo, expandir consciência → "Que tipo de preparação eu preciso fazer para romper o domo e expandir a consciência?"
   Ex: User "Quero que você repita tudo que você falou" + Asst com resumo sobre Cristo, domo, arrebatamento, nutrição → "Pode resumir as principais ideias sobre Cristo prometido, domo eletromagnético, arrebatamento, preparação e nutrição?"
   Ex: User "Quero" + Asst "Falando mais sobre X" → "Quero que aprofunde na leitura de X"
   Retorne array na ordem das mensagens User.

4) Se TIPO for "leitura" ou "pergunta_ao_campo", inclua também:
   - tipo_consulta: ansiedade, relacionamento, propósito, trabalho, transição, saúde, espiritual (escolha 1)
   - contexto_anonimo: frase curta e genérica, ex. "pessoa em transição profissional"
   - nome_remover: nome(s) da pessoa a substituir na resposta (ex: "Débora", "Vinícius"). Separar por vírgula. null se não houver.
   - Em user_melhorado_list: substitua nomes por "uma pessoa" + tema genérico. Ex: "Analisa o campo da Débora" → "Analisa o campo de uma pessoa em dúvida sobre mensagem espiritual"

5) Se TIPO for "conversa", tipo_consulta, contexto_anonimo e nome_remover podem ser null. user_melhorado_list é sempre obrigatório.

Conversa:
{text}

Responda APENAS com JSON válido, sem markdown. Exemplo leitura (2 turnos):
{{"tipo": "leitura", "genero": ["dialogo"], "funcao": ["conselho", "acolhimento"], "tom": ["conselheira"], "tipo_consulta": "transição", "contexto_anonimo": "pessoa em transição profissional", "user_melhorado_list": ["Analisa o campo de uma pessoa em transição profissional e orienta", "Quero que aprofunde na leitura da pessoa"], "nome_remover": "Maria"}}

Exemplo conversa (1 turno):
{{"tipo": "conversa", "genero": ["explicativo"], "funcao": ["educacional"], "tom": ["formal"], "tipo_consulta": null, "contexto_anonimo": null, "user_melhorado_list": ["O que é isso?"], "nome_remover": null}}

IMPORTANTE para leitura/pergunta_ao_campo: nome_remover deve listar TODOS os nomes de pessoas que aparecem na RESPOSTA do Assistant (não só na pergunta). Ex: Eduardo, Maria, João."""

# Prompt para anonimizar resposta do assistant (placeholder: {text})
PROMPT_ANONIMIZAR_RESPOSTA = """Anonimize este texto substituindo TODOS os nomes próprios de pessoas por "a pessoa" ou "da pessoa" conforme o contexto (ex: "da Maria" → "da pessoa", "Eduardo" → "a pessoa").

Mantenha o resto do texto idêntico. Retorne APENAS o texto anonimizado, sem explicações ou markdown.

Texto:
{text}"""
