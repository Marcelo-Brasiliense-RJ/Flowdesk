# Testes do FlowDesk — 5 níveis

Cada teste tem o **arquivo** para subir, o **prompt** para colar no Smart Chat
(aba **Chat** cria um projeto novo, ou use o painel de chat dentro do Editor) e o
**gabarito** (resultado esperado).

---

## Teste 1 — Fácil · Soma de vendas por produto
**Arquivo:** `teste1_vendas.xlsx` (colunas: data, produto, vendedor, valor)
**Prompt:** "Tenho uma planilha de vendas com as colunas produto e valor. Quero o
total geral de vendas e o total por produto, gerando uma planilha de saída."
**Gabarito:** total geral = **1700** · por produto = {'Plano A': 400, 'Plano B': 300, 'Plano C': 1000}

## Teste 2 — Médio · Conciliação por chave comum
**Arquivos:** `teste2_sistema.xlsx` e `teste2_banco.xlsx` (colunas: id, descricao, valor)
**Prompt:** "Concilie estas duas planilhas pela coluna id. Quero três grupos:
conciliados (id em ambas), só no sistema, só no banco; e aponte divergências de
valor para o mesmo id."
**Gabarito:** conciliados (id em ambas) = 4,5,6 → **3** · só sistema = 1,2,3 →
**3** · só banco = 7,8,9 → **3** · divergência de valor = id **5** (500 x 550)

## Teste 3 — Médio-difícil · Razão: débito x crédito que se zera
**Arquivo:** `teste3_razao.xlsx` (colunas: conta, historico, D/C, valor)
**Prompt:** "Concilie este razão contábil pareando débito contra crédito de mesmo
valor que se anulam (zeram). Separe em Conciliados e Não Conciliados, mantendo
TODOS os registros, e gere um resumo com os totais."
**Gabarito:** carregados = **7** · conciliados = **4** (pares 1000 e 500) ·
não conciliados = **3** · soma fecha (4+3=7).

## Teste 4 — Difícil · Aging de contas a receber (faixas de vencimento)
**Arquivo:** `teste4_contas_receber.xlsx` (colunas: cliente, documento, vencimento, valor)
**Data-base de cálculo:** 2026-06-08
**Prompt:** "Considere a data-base 2026-06-08. Classifique cada título por faixa de
atraso (A vencer, 1-30, 31-60, 61-90, 90+) com base no vencimento e some o valor
por faixa. Gere também o total por cliente e faixa."
**Gabarito (soma por faixa):** {'1-30': 2500, '31-60': 2500, '90+': 6000, 'A vencer': 1400}

## Teste 5 — Muito difícil · Conciliação bancária por valor + data (tolerância)
**Arquivos:** `teste5_extrato.xlsx` (data, descricao, valor) e `teste5_razao.xlsx`
(data, historico, valor)
**Prompt:** "Concilie o extrato bancário com o razão casando lançamentos de mesmo
valor cuja data esteja dentro de uma tolerância de 3 dias (as descrições são
diferentes). Liste os casados, os não casados do extrato e os não casados do
razão."
**Gabarito:** casados = **2** (1000 com +2 dias; 750 no mesmo dia) ·
não casados extrato = Pagamento fornecedor (2500, data 7 dias do razão) e Deposito
(1800) · não casados razão = Fornecedor X (2500) e Outro (9999). Observação: o par
2500 NÃO casa porque a diferença de datas (15/05 x 22/05 = 7 dias) excede a
tolerância de 3 dias — é isso que torna o teste difícil.

---
Dica: no teste 2 dá para usar o app publicado **/app/conciliador** (concilia por
chave) direto. Os demais ficam melhores criando um projeto novo pela aba **Chat**.
