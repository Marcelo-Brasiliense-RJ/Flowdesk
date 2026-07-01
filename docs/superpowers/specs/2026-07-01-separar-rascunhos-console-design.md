# Separar Rascunhos de "Sem pasta" na Console

Data: 2026-07-01
Status: aprovado

## Problema

Na tela de Automações ([front/src/pages/Console.tsx](../../../front/src/pages/Console.tsx)), o grupo "Sem pasta" lista todos os projetos sem `folder_id`, misturando os que estão No ar (`status === "live"`) com os que ainda são Rascunho (`status === "draft"`). O usuário quer que "Sem pasta" mostre somente as automações No ar e que os rascunhos fiquem em uma seção própria de Rascunhos.

## Escopo

Apenas rascunhos sem pasta. Um rascunho que já esteja dentro de uma pasta real (ex: Fiscal) permanece nessa pasta. A mudança altera somente como o conjunto "sem `folder_id`" é apresentado, dividindo-o em dois grupos por `status`.

Fora de escopo: criar pasta real de rascunhos no backend, migração de dados, mudança de API. O agrupamento é derivado no front a partir de campos que já existem (`status`, `folder_id`).

## Solução

Arquivo afetado: [front/src/pages/Console.tsx](../../../front/src/pages/Console.tsx), somente.

### Derivação dos grupos

Hoje ([Console.tsx:201](../../../front/src/pages/Console.tsx#L201)):

```
ungrouped = projects.filter((p) => !p.folder_id)
```

Passa a ser dois grupos derivados por status:

```
ungroupedLive = projects.filter((p) => !p.folder_id && p.status === "live")
drafts        = projects.filter((p) => !p.folder_id && p.status === "draft")
```

Favoritos e pastas reais ficam inalterados.

### Render

Em [Console.tsx:309-321](../../../front/src/pages/Console.tsx#L309-L321):

1. A seção "Sem pasta" passa a receber `ungroupedLive` no lugar de `ungrouped`.
2. Logo depois dela, uma nova seção "Rascunhos" com `drafts`.

A nova seção reaproveita o componente `Section` já existente, como seção virtual (sem `folderId`). Para consistência visual com "⭐ Favoritos", o título usa o prefixo de emoji "📝 Rascunhos".

### Reaproveitamento do componente Section

As duas seções são virtuais (não têm `folderId`). A regra atual de esconder grupo virtual vazio ([Console.tsx:368](../../../front/src/pages/Console.tsx#L368), `if (projects.length === 0 && !folderId && !pinned) return null;`) já cobre ambas sem código adicional: "Sem pasta" some quando não há projetos No ar sem pasta, e "Rascunhos" some quando não há rascunhos sem pasta.

### Drag & drop

- O card continua arrastável para dentro de pastas reais (comportamento inalterado do `ProjectCard`).
- A seção "Sem pasta" mantém `onDropProject={(id) => moveProject(id, null)}`, que limpa a pasta do projeto.
- A seção "Rascunhos" não recebe `onDropProject`. Soltar um card ali não teria como nem por que alterar o `status`; um projeto só passa a `live` pelo fluxo de publicação existente.

### Comportamento derivado

- Publicar um rascunho o move de "Rascunhos" para "Sem pasta" automaticamente, porque o agrupamento é derivado de `status`.
- Arrastar um rascunho para "Sem pasta" apenas limpa o `folder_id`; como ele continua `draft`, reaparece em "Rascunhos", não em "Sem pasta". Coerente com a regra.

## Critérios de sucesso

- Com projetos sem pasta em ambos os status, "Sem pasta" lista somente os `live` e "Rascunhos" lista somente os `draft`.
- Contagens de cada seção batem com o número de cards exibidos.
- Rascunhos dentro de pastas reais continuam aparecendo em suas pastas.
- Quando não há rascunhos sem pasta, a seção "Rascunhos" não aparece.
- Quando não há projetos No ar sem pasta, a seção "Sem pasta" não aparece.
- Publicar um rascunho o transfere de "Rascunhos" para "Sem pasta" sem reload manual (após o `load()` já disparado pelo fluxo de publicação).

## Testes

O projeto tem testes de front em `front/src/**/*.test.tsx`. Adicionar teste do agrupamento cobrindo: separação live/draft sem pasta, rascunho dentro de pasta permanecendo na pasta, e ocultação das seções virtuais vazias. Se a Console ainda não tiver arquivo de teste, extrair a lógica de derivação dos grupos para uma função pura testável é preferível a testar via render completo.
