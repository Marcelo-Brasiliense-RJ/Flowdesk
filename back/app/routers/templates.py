"""Galeria de modelos prontos: automações típicas da IRKO instanciáveis em 1 clique.

Cada modelo define o fluxo completo (Form de entrada -> Script -> Form de resultado)
com código testável. Instanciar cria um projeto normal, que abre no Assistente já
pronto para testar.
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Edge, Project, SourceFile, Stage, User
from ..services import storage
from .projects import slugify

router = APIRouter(prefix="/api", tags=["templates"])


_TOTAIS_VENDAS = '''"""Totais de uma planilha: total geral e total por categoria."""
import pandas as pd
from flowdesk_sdk import get_file, set_output, output_path

df = pd.read_excel(get_file())
col_num = df.select_dtypes("number").columns
if len(col_num) == 0:
    set_output({"erro": "A planilha não tem coluna numérica para somar."})
else:
    valor = col_num[-1]
    col_txt = [c for c in df.columns if c != valor]
    grupo = col_txt[0] if col_txt else None
    total = float(df[valor].sum())
    out = output_path("totais.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame({grupo or "grupo": ["Total Geral"], valor: [total]}).to_excel(
            w, sheet_name="Resumo", index=False)
        if grupo:
            df.groupby(grupo)[valor].sum().reset_index().to_excel(
                w, sheet_name="Por grupo", index=False)
    resumo = {"total_geral": total, "linhas": len(df)}
    if grupo:
        resumo["grupos"] = int(df[grupo].nunique())
    set_output({"arquivo_resultado": str(out), "resumo": resumo})
'''

_CONCILIACAO = '''"""Concilia duas planilhas por uma chave comum e aponta divergências."""
import pandas as pd
from flowdesk_sdk import get_file, set_output, output_path

df_a = pd.read_excel(get_file(0))
df_b = pd.read_excel(get_file(1))
comuns = [c for c in df_a.columns if c in df_b.columns]
chave = comuns[0] if comuns else df_a.columns[0]
a_keys = set(df_a[chave].astype(str))
b_keys = set(df_b[chave].astype(str))
out = output_path("conciliacao.xlsx")
with pd.ExcelWriter(out, engine="openpyxl") as w:
    df_a[df_a[chave].astype(str).isin(a_keys & b_keys)].to_excel(w, sheet_name="Conciliados", index=False)
    df_a[df_a[chave].astype(str).isin(a_keys - b_keys)].to_excel(w, sheet_name="So_na_A", index=False)
    df_b[df_b[chave].astype(str).isin(b_keys - a_keys)].to_excel(w, sheet_name="So_na_B", index=False)
set_output({
    "arquivo_resultado": str(out),
    "resumo": {"chave": str(chave), "conciliados": len(a_keys & b_keys),
               "so_na_a": len(a_keys - b_keys), "so_na_b": len(b_keys - a_keys)},
})
'''

_PDF_PARA_PLANILHA = '''"""Extrai o texto de um PDF (editável ou escaneado) para uma planilha."""
import pandas as pd
from flowdesk_sdk import get_file, set_output, output_path, extract_document

doc = extract_document(get_file())
linhas = [l["text"] for l in doc["lines"]]
out = output_path("texto_extraido.xlsx")
pd.DataFrame({"linha": range(1, len(linhas) + 1), "texto": linhas}).to_excel(out, index=False)
set_output({
    "arquivo_resultado": str(out),
    "resumo": {"linhas_extraidas": len(linhas), "fonte": doc["source"],
               "confianca_media": doc["mean_confidence"]},
    "_ocr_review": {"text": doc["text"], "mean_confidence": doc["mean_confidence"],
                    "needs_review": doc["needs_review"],
                    "low_confidence": [l["text"] for l in doc["low_confidence"]]},
})
'''

_EXTRATO_DOMINIO = '''"""Extrato bancário (PDF Bradesco) -> planilha de lançamentos do Domínio.

Fluxo em 2 passes:
  pass 1 (sem _classificacao_confirmada): lê extrato + plano de contas, aplica
    regras De/Para do projeto e devolve _classificacao_review para a tela de revisão.
  pass 2 (com _classificacao_confirmada): aplica o mapa confirmado, filtra o
    período e gera o xlsx no contrato do Domínio.
"""
import datetime as dt
import re
from flowdesk_sdk import (get_input, get_file, set_output, output_path, log,
                          progress, get_table, read_table)

NUM = re.compile(r"^-?\\d{1,3}(\\.\\d{3})*,\\d{2}$")
DATE = re.compile(r"^\\d{2}/\\d{2}/\\d{4}$")
COLUNAS = ["Data", "Cód. Conta Debito", "Cód. Conta Credito", "Valor",
           "Cód. Histórico", "Complemento Histórico", "Inicia Lote",
           "Código Matriz/Filial", "Centro de Custo Débito", "Centro de Custo Crédito"]


def brl(s):
    return float(s.replace(".", "").replace(",", "."))


def padrao_de(historico):
    """Padrão de agrupamento: histórico sem números/datas (estável entre meses)."""
    toks = [t for t in str(historico).split()
            if not t.replace("/", "").replace("-", "").replace(".", "").isdigit()]
    return " ".join(toks).strip().upper()


def parse_extrato(pdf_path):
    """Parser posicional do extrato Bradesco. Crédito x1<400, débito 400<=x1<490,
    saldo x1>=490 (valores alinhados à direita). Valida pela aritmética do saldo."""
    import pdfplumber
    lanc, saldo_ant, saldo_fim = [], None, None
    data_atual, desc_acum = None, []
    periodo = None
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            linhas = {}
            for w in words:
                linhas.setdefault(round(w["top"]), []).append(w)
            for top in sorted(linhas):
                ws = sorted(linhas[top], key=lambda x: x["x0"])
                texto_linha = " ".join(w["text"] for w in ws)
                m = re.search(r"Entre (\\d{2}/\\d{2}/\\d{4}) e (\\d{2}/\\d{2}/\\d{4})", texto_linha)
                if m and periodo is None:
                    periodo = (m.group(1), m.group(2))
                nums = [w for w in ws if NUM.match(w["text"])]
                saldo_tok = [w for w in nums if w["x1"] >= 490]
                textos = [w["text"] for w in ws
                          if not NUM.match(w["text"]) and not DATE.match(w["text"])]
                dtok = next((w["text"] for w in ws if DATE.match(w["text"])), None)
                if dtok:
                    data_atual = dt.datetime.strptime(dtok, "%d/%m/%Y").date()
                if saldo_tok:
                    saldo = brl(saldo_tok[-1]["text"])
                    inline = [t for t in textos if t.upper() not in ("SALDO", "ANTERIOR", "TOTAL")]
                    desc = " ".join(desc_acum + inline).strip()
                    desc_acum = []
                    cred = next((brl(w["text"]) for w in nums if w["x1"] < 400), None)
                    deb = next((brl(w["text"]) for w in nums if 400 <= w["x1"] < 490), None)
                    eh_rodape = "TOTAL" in " ".join(textos).upper()
                    if cred is None and deb is None:
                        if saldo_ant is None:
                            saldo_ant = saldo
                        saldo_fim = saldo
                        continue
                    if eh_rodape:
                        continue
                    lanc.append({"data": data_atual, "historico": desc,
                                 "credito": round(cred, 2) if cred is not None else None,
                                 "debito": round(abs(deb), 2) if deb is not None else None,
                                 "saldo": saldo})
                    saldo_fim = saldo
                elif textos:
                    desc_acum.append(" ".join(textos))
    # validação aritmética linha a linha (saldo anterior + delta = saldo da linha)
    prev, erros = saldo_ant or 0, 0
    for l in lanc:
        impresso = (l["credito"] or 0) - (l["debito"] or 0)
        if abs(impresso - round(l["saldo"] - prev, 2)) > 0.01:
            erros += 1
        prev = l["saldo"]
    return {"lancamentos": lanc, "saldo_anterior": saldo_ant, "saldo_final": saldo_fim,
            "periodo": periodo, "linhas_inconsistentes": erros}


def carregar_plano(caminho):
    """Plano de contas Domínio: devolve contas analíticas [{codigo, nome, classificacao}].
    Sintéticas têm 'S' na coluna T; o nome fica na coluna do grau correspondente."""
    df = read_table(caminho, header=None)
    contas = []
    for _, row in df.iterrows():
        vals = ["" if v != v else str(v).strip() for v in row.tolist()]  # NaN -> ""
        codigo = vals[0]
        if not codigo or not codigo.replace(".", "").isdigit():
            continue
        if "S" in (vals[3] if len(vals) > 3 else ""):
            continue  # sintética não recebe lançamento
        classif = next((v for v in vals if re.match(r"^\\d+(\\.\\d+)+$", v)), "")
        nome = next((v for v in vals[10:] if v and not v.isdigit()), "")
        if nome:
            contas.append({"codigo": codigo.split(".")[0], "nome": nome,
                           "classificacao": classif})
    return contas


def agrupar(lancamentos, regras):
    """Agrupa por padrão de histórico e aplica regras De/Para (match exato)."""
    grupos = {}
    for i, l in enumerate(lancamentos):
        p = padrao_de(l["historico"])
        g = grupos.setdefault(p, {"padrao": p, "exemplo": l["historico"], "qtd": 0,
                                  "total": 0.0, "tipo": "", "linhas": [],
                                  "conta": None, "conta_nome": "", "origem": None})
        g["qtd"] += 1
        g["total"] = round(g["total"] + (l["credito"] or l["debito"] or 0), 2)
        g["tipo"] = "credito" if l["credito"] else "debito"
        g["linhas"].append(i)
    for g in grupos.values():
        if g["padrao"] in regras:
            g["conta"] = regras[g["padrao"]]
            g["origem"] = "regra"
    return sorted(grupos.values(), key=lambda g: -g["total"])


def gerar_xlsx(lancamentos, mapa, conta_banco, caminho):
    """Contrato Domínio: lançamento simples; Inicia Lote = 1 na primeira linha de
    cada dia; Cód. Histórico vazio; Complemento = histórico do extrato."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilha1"
    ws.append(COLUNAS)
    dia_anterior = None
    for l in sorted(lancamentos, key=lambda x: x["data"]):
        conta = mapa.get(padrao_de(l["historico"]))
        if conta in (None, "", "IGNORAR"):
            continue
        inicia = 1 if l["data"] != dia_anterior else None
        dia_anterior = l["data"]
        if l["credito"]:  # entrada: débito banco / crédito contrapartida
            deb, cred, valor = conta_banco, conta, l["credito"]
        else:             # saída: débito contrapartida / crédito banco
            deb, cred, valor = conta, conta_banco, l["debito"]
        ws.append([l["data"], deb, cred, valor, None, l["historico"], inicia,
                   None, None, None])
    for cell in ws["A"]:
        if cell.row > 1:
            cell.number_format = "DD/MM/YYYY"
    wb.save(str(caminho))


def localizar_plano():
    """Plano de contas é ativo do projeto: uploads/plano_contas.* ou similar."""
    import glob
    for pat in ("uploads/plano*conta*.*", "uploads/*contas*.*", "uploads/*.xls"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def main():
    entrada = get_input()
    progress("Lendo o extrato", "")
    pdf = get_file(0)
    if not pdf:
        set_output({"erro": "Envie o PDF do extrato bancário."})
        return
    ext = parse_extrato(pdf)
    lanc = ext["lancamentos"]
    progress("Extrato lido", f"{len(lanc)} lançamentos, período "
             f"{ext['periodo'][0] if ext['periodo'] else '?'} a "
             f"{ext['periodo'][1] if ext['periodo'] else '?'}")
    if ext["linhas_inconsistentes"]:
        log(f"Atenção: {ext['linhas_inconsistentes']} linhas não batem com o saldo.")

    plano_path = get_file(1) or localizar_plano()
    if not plano_path:
        set_output({"erro": "Plano de contas não encontrado. Anexe o arquivo do "
                            "plano (xls/xlsx/csv) em uploads/ com 'contas' no nome."})
        return
    progress("Lendo o plano de contas", "")
    contas = carregar_plano(plano_path)
    progress("Plano de contas lido", f"{len(contas)} contas analíticas")

    regras_rows = get_table("regras_classificacao")
    regras = {r["padrao"]: r["conta_codigo"] for r in regras_rows}
    conta_banco = regras.get("_CONTA_BANCO")

    confirmado = entrada.get("_classificacao_confirmada")
    if not confirmado:
        # PASS 1: montar a revisão
        progress("Aplicando suas regras", f"{len(regras)} regras conhecidas")
        grupos = agrupar(lanc, regras)
        com_regra = sum(1 for g in grupos if g["origem"] == "regra")
        progress("Aguardando sua revisão",
                 f"{com_regra} de {len(grupos)} grupos classificados por regra")
        datas = [l["data"] for l in lanc if l["data"]]
        set_output({
            "_classificacao_review": {
                "periodo_detectado": {"inicio": ext["periodo"][0], "fim": ext["periodo"][1]}
                                     if ext["periodo"] else
                                     {"inicio": min(datas).strftime("%d/%m/%Y"),
                                      "fim": max(datas).strftime("%d/%m/%Y")},
                "conta_banco": conta_banco,
                "grupos": [{k: g[k] for k in
                            ("padrao", "exemplo", "qtd", "total", "tipo",
                             "conta", "conta_nome", "origem")} for g in grupos],
                "contas": contas,
                "total_lancamentos": len(lanc),
            },
            "resumo": {"lancamentos_no_extrato": len(lanc),
                       "grupos": len(grupos), "classificados_por_regra": com_regra},
        })
        return

    # PASS 2: gerar a planilha com o mapa confirmado
    mapa = {str(k).upper(): str(v) for k, v in confirmado.items()}
    conta_banco = entrada.get("_conta_banco") or conta_banco
    if not conta_banco:
        set_output({"erro": "Conta do banco não informada na revisão."})
        return
    periodo = entrada.get("_periodo") or {}
    ini = dt.datetime.strptime(periodo["inicio"], "%d/%m/%Y").date() if periodo.get("inicio") else None
    fim = dt.datetime.strptime(periodo["fim"], "%d/%m/%Y").date() if periodo.get("fim") else None
    progress("Filtrando pela competência",
             f"{periodo.get('inicio', '')} a {periodo.get('fim', '')}")
    no_periodo = [l for l in lanc if l["data"] and
                  (ini is None or l["data"] >= ini) and (fim is None or l["data"] <= fim)]
    fora = len(lanc) - len(no_periodo)
    ignorados = sum(1 for l in no_periodo
                    if mapa.get(padrao_de(l["historico"])) in (None, "", "IGNORAR"))
    progress("Gerando a planilha do Domínio", f"{len(no_periodo) - ignorados} lançamentos")
    out = output_path("lancamentos_dominio.xlsx")
    gerar_xlsx(no_periodo, mapa, conta_banco, out)
    tot_cred = round(sum(l["credito"] or 0 for l in no_periodo
                         if mapa.get(padrao_de(l["historico"])) not in (None, "", "IGNORAR")), 2)
    tot_deb = round(sum(l["debito"] or 0 for l in no_periodo
                        if mapa.get(padrao_de(l["historico"])) not in (None, "", "IGNORAR")), 2)
    progress("Pronto", f"créditos R$ {tot_cred:,.2f} | débitos R$ {tot_deb:,.2f}")
    set_output({
        "arquivo_resultado": str(out),
        "resumo": {"lancamentos_importados": len(no_periodo) - ignorados,
                   "fora_da_competencia": fora, "ignorados_na_revisao": ignorados,
                   "total_creditos": tot_cred, "total_debitos": tot_deb},
    })


if not get_input().get("_somente_definicoes"):
    main()
'''

# A1: conhecimento contábil que ANTES vivia hardcoded nos prompts centrais. Agora
# mora aqui, junto do template que o implementa, e é injetado no contexto da IA só
# quando a tarefa casa com este template (via reference_for_task). Prompts genéricos.
_EXTRATO_DOMINIO_REFERENCE = """\
Regras do domínio contábil (extrato bancário -> importação do Domínio). Aplique só a esta classe de tarefa.

CONTRATO DA SAÍDA (layout de importação do Domínio): colunas EXATAS, nesta ordem: Data, Cód. Conta Debito, Cód. Conta Credito, Valor, Cód. Histórico, Complemento Histórico, Inicia Lote, Código Matriz/Filial, Centro de Custo Débito, Centro de Custo Crédito. "Cód. Histórico" fica vazio. "Inicia Lote" = 1 na PRIMEIRA linha de cada dia e reinicia a cada troca de data. Convenção débito/crédito: o banco vai no débito da entrada e a contrapartida classificada no crédito; inverte na tarifa.

PARSE DO EXTRATO EM PDF: NÃO escreva um classificador do zero; parta do modelo "extrato-dominio" da galeria. Faça parse POSICIONAL do PDF via pdfplumber (import pdfplumber; pdf = pdfplumber.open(get_file(0))), separando colunas pelas POSIÇÕES x das palavras (page.extract_words(), campos x0/x1), NUNCA fatiando doc["text"] por espaços: no texto linear, data/histórico/crédito/débito/saldo perdem o alinhamento.

PLANO DE CONTAS (get_file(1)): não é tabela De/Para. Tem cabeçalho DESLOCADO (leia com header=None e localize a linha de cabeçalho) e colunas Código/T/Classificação/Nome/Grau, NUNCA uma coluna "Descrição". Jamais classifique por substring do nome da conta no histórico.

REGRAS DE/PARA: get_table("regras_classificacao") traz as regras aprendidas do projeto (lista de {padrao, conta_codigo}); a regra especial "_CONTA_BANCO" guarda a conta do banco.

REVISÃO HUMANA EM 2 PASSES: no pass 1 devolva set_output({"_classificacao_review": {periodo_detectado, conta_banco, grupos, contas, total_lancamentos}}) SEM gerar arquivo (a interface mostra a tela de revisão com semáforo). O pass 2 chega com "_classificacao_confirmada" (mapa padrao->conta; "IGNORAR" pula o grupo), "_conta_banco" e "_periodo" ({inicio, fim} dd/mm/aaaa) no get_input(); então filtre o período e gere o arquivo_resultado.

VALIDAÇÃO: antes de declarar sucesso, confira que as somas por categoria fecham com o total carregado.
"""


_AGING_REFERENCE = """\
Regras para AGING / dias de atraso de títulos (contas a receber ou a pagar).

Adapte os NOMES das colunas (vencimento, valor, cliente) aos do arquivo real; pergunte a data-base se não vier (default: hoje).
dias = (data_base - vencimento).days. dias <= 0 é "A vencer".
Faixas com limite superior INCLUSIVO e SEM sobreposição: "1-30" (1<=dias<=30), "31-60" (31<=dias<=60), "61-90" (61<=dias<=90), "90+" (dias>90).
Para "por cliente E faixa", use pivot_table(index=cliente, columns=faixa, values=valor, aggfunc="sum").
"""


_CONCILIACAO_CONTABIL_REFERENCE = """\
Regras para CONCILIAÇÃO de lançamentos (débito x crédito, ou por valor + data).

Adapte os nomes das colunas ao arquivo real.
DÉBITO x CRÉDITO que zera: pareie por VALOR ABSOLUTO (abs(valor)), tratando crédito negativo. Pareamento 1:1, marcando cada lançamento usado; com valores repetidos, ordene de forma estável. Mantenha TODOS os registros (Conciliados + Não Conciliados = carregados) e gere resumo com as contagens que fecham.
POR VALOR + DATA com tolerância: case mesmo valor com diferença de datas <= tolerância (em dias); > tolerância NÃO casa. Casamento 1:1 (não reutilize a mesma linha). Inclua na saída a coluna "dif_dias". Remova não casados por ÍNDICE da linha, nunca por valor de data.
Antes de declarar sucesso: Conciliados + Não Conciliados = total carregado.
"""


# Exemplos ILUSTRATIVOS: como o formato de entrada varia por projeto, os nomes de
# coluna são um ponto de partida a adaptar (o valor real está no reference acima).
_AGING_CODE = '''"""Aging: dias de atraso por faixa. ADAPTE os nomes das colunas ao seu arquivo."""
from flowdesk_sdk import get_file, read_table, set_output, output_path

import datetime as dt

import pandas as pd

COL_VENCIMENTO = "vencimento"  # ajuste ao nome real da coluna
COL_VALOR = "valor"
COL_CLIENTE = "cliente"


def faixa(d):
    if pd.isna(d) or d <= 0:
        return "A vencer"
    if d <= 30:
        return "1-30"
    if d <= 60:
        return "31-60"
    if d <= 90:
        return "61-90"
    return "90+"


df = read_table(get_file())
base = pd.Timestamp(dt.date.today())
venc = pd.to_datetime(df[COL_VENCIMENTO], dayfirst=True, errors="coerce")
df["faixa"] = [faixa(d) for d in (base - venc).dt.days]
piv = pd.pivot_table(df, index=COL_CLIENTE, columns="faixa", values=COL_VALOR,
                     aggfunc="sum", fill_value=0)
out = output_path("aging.xlsx")
piv.to_excel(out)
set_output({"arquivo_resultado": str(out), "resumo": {"titulos": int(len(df))}})
'''


_CONCILIACAO_CONTABIL_CODE = '''"""Concilia lançamentos que se anulam por valor absoluto (1:1). ADAPTE a coluna de valor."""
from collections import defaultdict

from flowdesk_sdk import get_file, read_table, set_output, output_path

COL_VALOR = "valor"  # ajuste ao nome real da coluna

df = read_table(get_file()).reset_index(drop=True)
vals = [float(v) for v in df[COL_VALOR]]
usados = set()
status = ["Nao Conciliado"] * len(df)
por_abs = defaultdict(list)
for i, v in enumerate(vals):
    por_abs[round(abs(v), 2)].append(i)
for i, v in enumerate(vals):
    if i in usados:
        continue
    for j in por_abs[round(abs(v), 2)]:
        if j == i or j in usados:
            continue
        if round(vals[j] + v, 2) == 0.0:  # um positivo, outro negativo, mesmo módulo
            usados.update((i, j))
            status[i] = status[j] = "Conciliado"
            break
df["conciliacao"] = status
out = output_path("conciliacao.xlsx")
df.to_excel(out, index=False)
n_ok = status.count("Conciliado")
set_output({"arquivo_resultado": str(out),
            "resumo": {"conciliados": n_ok, "nao_conciliados": len(df) - n_ok,
                       "total": len(df)}})
'''


TEMPLATES: dict[str, dict] = {
    "totais-planilha": {
        "name": "Totais de uma planilha",
        "description": "Soma o total geral e o total por grupo (ex: vendas por produto) e gera um Excel.",
        "input_fields": [{"name": "arquivo", "label": "Planilha (.xlsx)", "type": "file"}],
        "code": _TOTAIS_VENDAS,
    },
    "conciliacao-planilhas": {
        "name": "Conciliação de duas planilhas",
        "description": "Compara duas planilhas por uma chave comum e separa conciliados e divergências.",
        "input_fields": [
            {"name": "planilha_a", "label": "Planilha A", "type": "file"},
            {"name": "planilha_b", "label": "Planilha B", "type": "file"},
        ],
        "code": _CONCILIACAO,
    },
    "pdf-para-planilha": {
        "name": "PDF para planilha (com OCR)",
        "description": "Lê um PDF (mesmo escaneado) com OCR local e entrega o texto estruturado em Excel, com revisão de confiança.",
        "input_fields": [{"name": "arquivo", "label": "PDF ou imagem", "type": "file"}],
        "code": _PDF_PARA_PLANILHA,
    },
    "extrato-dominio": {
        "name": "Extrato bancário para lançamentos (Domínio)",
        "description": "Lê o extrato em PDF, classifica cada lançamento com suas "
                       "regras e revisão assistida por IA, e gera a planilha de "
                       "importação de lançamentos contábeis do Domínio.",
        "input_fields": [{"name": "arquivo", "label": "Extrato bancário (PDF)", "type": "file"}],
        "code": _EXTRATO_DOMINIO,
        "reference": _EXTRATO_DOMINIO_REFERENCE,
    },
    "aging": {
        "name": "Aging de títulos (dias de atraso)",
        "description": "Calcula os dias de atraso de títulos por faixa "
                       "(1-30, 31-60, 61-90, 90+) e o total por cliente.",
        "input_fields": [{"name": "arquivo", "label": "Planilha de títulos", "type": "file"}],
        "code": _AGING_CODE,
        "reference": _AGING_REFERENCE,
    },
    "conciliacao-contabil": {
        "name": "Conciliação contábil (débito x crédito)",
        "description": "Pareia lançamentos de débito e crédito que se anulam por "
                       "valor e separa conciliados de não conciliados.",
        "input_fields": [{"name": "arquivo", "label": "Planilha de lançamentos", "type": "file"}],
        "code": _CONCILIACAO_CONTABIL_CODE,
        "reference": _CONCILIACAO_CONTABIL_REFERENCE,
    },
}


@router.get("/templates")
def list_templates(user: User = Depends(get_current_user)):
    return [
        {"key": k, "name": t["name"], "description": t["description"]}
        for k, t in TEMPLATES.items()
    ]


@router.post("/templates/{key}/instantiate")
def instantiate_template(
    key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tpl = TEMPLATES.get(key)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")

    base = slugify(tpl["name"])
    sub = base
    while db.query(Project).filter(Project.subdomain == sub).first():
        sub = f"{base}-{_uuid.uuid4().hex[:4]}"
    project = Project(
        org_id=user.org_id, name=tpl["name"], subdomain=sub,
        description=tpl["description"], status="draft",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    storage.ensure_project_dirs(project)

    form_in = Stage(
        project_id=project.id, type="form", name="Entrada", key="entrada",
        config={"title": tpl["name"], "mode": "input", "submit_label": "Executar",
                "fields": tpl["input_fields"]},
        pos_x=40, pos_y=120,
    )
    script = Stage(
        project_id=project.id, type="script", name="Processamento", key="processamento",
        entry_file="processar.py", config={}, pos_x=360, pos_y=120,
    )
    form_out = Stage(
        project_id=project.id, type="form", name="Resultado", key="resultado",
        config={"title": "Resultado", "mode": "result",
                "summary_key": "resumo", "result_file_key": "arquivo_resultado"},
        pos_x=680, pos_y=120,
    )
    db.add_all([form_in, script, form_out])
    db.flush()
    db.add_all([
        Edge(project_id=project.id, source_stage_id=form_in.id,
             target_stage_id=script.id, variable_label="entrada"),
        Edge(project_id=project.id, source_stage_id=script.id,
             target_stage_id=form_out.id, variable_label="resultado"),
    ])
    db.add_all([
        SourceFile(project_id=project.id, path="processar.py", content=tpl["code"]),
        SourceFile(project_id=project.id, path="requirements.txt", content="pandas\nopenpyxl\n"),
        SourceFile(project_id=project.id, path="README.md",
                   content=f"# {tpl['name']}\n\n{tpl['description']}\n"),
    ])
    # marca o rascunho do assistente como montado para abrir direto na revisão
    project.wizard_state = {
        "_built": True,
        "trigger": {"kind": "manual"},
        "input": {"kind": "file"},
        "process": {"description": tpl["description"]},
        "output": {"kind": "download"},
    }
    db.commit()
    return {"project_id": project.id, "name": project.name}
