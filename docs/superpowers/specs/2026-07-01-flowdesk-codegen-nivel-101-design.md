# FlowDesk: codegen nível 101 nas automações novas

Data: 2026-07-01
Origem: falhas dos projetos 101 (corrigido) e 102 (regressão). O 101 ficou bom
porque teve correção manual do script; o 102, gerado pela IA, regrediu. Objetivo:
que as automações NOVAS atinjam o nível do 101 de forma confiável, sem correção
manual.

## Problema (causa-raiz)

O código das automações é escrito pelo agente `construtor`
(`orchestrator.run_construtor` → `call_agent("construtor", ..., json_mode=True)`).
Hoje o construtor roda `gpt-4o-mini` e recebe só a guidance em PROSA. As partes
difíceis do fluxo `extrato-dominio` (parser posicional de PDF via pdfplumber,
revisão em 2 passes, classificação correta) são ~250 linhas de código de domínio
que um modelo fraco não reproduz a partir de uma descrição textual. Resultado no
102: 21 de 564 lançamentos, 21/21 não classificados, sem tela de revisão,
contrapartida "1.1.1" inventada.

Confirmado: `chat.py` nunca injeta o código real da galeria (`_EXTRATO_DOMINIO`
em `templates.py`); só o menciona em texto. Prosa não substitui código de
referência.

## Objetivo

Automações novas que batem com um padrão conhecido (ex.: extrato bancário →
Domínio) saem no nível do 101 sem intervenção manual; as demais saem
significativamente melhores. Efeito colateral: com as novas usando o fluxo
`extrato-dominio`, a tela de revisão (`_classificacao_review`) reaparece e o botão
"Deixar IA classificar" volta a funcionar nelas.

## Escopo (travado com o usuário)

1. Migração para a Responses API acontece SÓ no `construtor` (modelo codex). Todo
   o resto continua no `chat.completions` como está hoje.
2. `reparador` e `treinador` ganham só um bump de modelo para um modelo forte
   compatível com chat (`gpt-4.1`), sem migração.
3. `assistente`/roteador, `planejador`, `nomeador`, `classificador` ficam
   inalterados (modelo compartilhado atual).

## Componentes

### 1. Migração codex do construtor (Responses API isolada em `call_agent`)

- **SDK:** subir `openai` (hoje 1.59.6, sem Responses API) para versão com
  `client.responses`. Verificar que os call-sites existentes de `chat.completions`
  continuam funcionando (a suíte de testes cobre o import da app).
- **`orchestrator.call_agent` (orchestrator.py:34-56):** adicionar um ramo que
  ativa APENAS para modelos de raciocínio/codex (regex de família:
  `gpt-5`, `o3`, `o4`, `codex`). Nesse ramo:
  - usa `client.responses.create(model=..., input=[system + messages])`;
  - NÃO envia `temperature` (o codex rejeita);
  - JSON: usa o parâmetro de saída estruturada da Responses API; se indisponível
    na versão do SDK, reforça JSON no prompt e valida com `json.loads`;
  - retorna `resp.output_text`.
  - Em falha da chamada, propaga como hoje (o call-site do construtor já trata).
  - Modelos de chat (tudo que não casar a regex) seguem no ramo
    `chat.completions` ATUAL, sem alteração.
- **Modelo do construtor:** `gpt-5.3-codex`.

### 2. Bump de modelo (sem migração): reparador e treinador

- **treinador:** já passa por `call_agent("treinador", ...)`. Bump = só
  configurar o modelo do agente. Zero código.
- **reparador:** hoje chama `client.chat.completions.create(model=ai_config.get_model())`
  direto (repair.py:145). Trocar para `ai_config.get_agent_model("reparador")`
  (1 linha; passa a respeitar o modelo do próprio agente). Continua em
  `chat.completions`.
- **Modelo de ambos:** `gpt-4.1` (forte em chat, compatível, sem Responses API).

### 3. Configuração de modelo por agente

- Defaults por agente em `ai_config` (fallback antes do modelo compartilhado),
  overrideável pelo grafo/UI de Agentes:
  - `construtor` → `gpt-5.3-codex`
  - `reparador` → `gpt-4.1`
  - `treinador` → `gpt-4.1`
  - demais → modelo compartilhado (inalterado)
- Novos settings em `config.py`: `openai_model_codegen` (default `gpt-5.3-codex`),
  `openai_model_strong` (default `gpt-4.1`). Assim dá para trocar por env sem mexer
  em código.

### 4. Injeção de código de referência + semente determinística (qualidade do construtor)

- **`reference_for_task(plan, project_context) -> {template_key, code, score}`**
  (novo helper): pontua os `TEMPLATES` da galeria (nome + descrição + palavras-chave
  de intenção) contra o texto da tarefa (plan). Reaproveita a ideia de sobreposição
  de tokens já usada no `treinador._score`.
- **Few-shot (score ≥ limiar baixo):** `run_construtor` injeta o código do melhor
  template como bloco de referência no prompt: "IMPLEMENTAÇÃO DE REFERÊNCIA PROVADA
  (adapte, não reescreva do zero)". Levanta a qualidade de todas as automações.
- **Semente determinística (score ≥ limiar alto = casamento claro):** em vez de
  confiar no modelo, `run_construtor` emite o `create_file` do script principal com
  o CÓDIGO DO TEMPLATE (adaptado só no que for objetivo: `get_file(0/1/2)` para
  formulários multi-arquivo como o do 102), garantindo paridade com o 101. O
  construtor ainda cuida de stages/nome/`require_env`.
- O template `_EXTRATO_DOMINIO` deve usar `get_file(0/1/2)` posicional (como a
  reescrita do 101) para casar formulários com mais de um arquivo.

## Confidencialidade

Sem mudança de superfície: o código dos templates é local; o construtor recebe o
mesmo contexto de tarefa de hoje. Nada novo do cliente sai da máquina. A
classificação (`classify.py`) segue mandando só padrão de histórico + código/nome
de conta, sem valores/saldos/CNPJ.

## Custo

- `construtor` (codex) e `reparador`/`treinador` (gpt-4.1) encarecem por chamada,
  mas rodam pouco (uma vez por build/reparo/colheita), não a cada turno de chat. O
  chat conversacional segue no modelo barato.

## Tratamento de erro / degradação

- Sem `OPENAI_API_KEY`: caminhos de IA já caem em mock/heurística (inalterado).
- Falha da Responses API no construtor: propaga como as falhas de `call_agent`
  atuais (o build reporta erro; o usuário tenta de novo).
- Sem template com score suficiente: geração normal (guidance + modelo), sem
  semente nem few-shot.

## Testes

- Unit: `reference_for_task` escolhe `extrato-dominio` para tarefa de extrato e
  respeita os limiares.
- Unit: `call_agent` roteia modelo codex → ramo Responses (mock do client) e
  modelo de chat → `chat.completions` (sem regressão).
- Unit: `reparador` passa a ler `get_agent_model("reparador")`.
- Integração/manual: regenerar um projeto 102-like e conferir que o script gerado
  bate com o template e, rodado contra os arquivos reais, extrai 564 lançamentos e
  produz a tela de revisão (paridade com o 101).

## Fora de escopo

- Migrar qualquer agente além do construtor para a Responses API.
- Confirmar em lote na revisão; redesenho das telas finais variáveis por automação.
- Harvest/destilação do Treinador (Tasks 6-12 do plano de auto-evolução) além do
  bump de modelo.

## Riscos e validação

- **Spike primeiro (Task 0 do plano):** com o SDK atualizado, validar em
  isolamento que `gpt-5.3-codex` responde via `responses.create` com saída JSON
  utilizável, ANTES de tocar no `call_agent`. Se a forma de JSON estruturado
  diferir da esperada, ajustar a estratégia (prompt-enforced + validação).
- **Upgrade do SDK** pode mudar comportamento de call-sites existentes: rodar a
  suíte de testes do backend após o upgrade.
- **Semente determinística**: risco de descasar campos de entrada
  (arquivo1/2/3 vs "arquivo"); mitigado usando `get_file` posicional no template.
