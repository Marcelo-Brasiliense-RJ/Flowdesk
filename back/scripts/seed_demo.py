"""Popula o banco com 8 automações de demonstração (form -> script -> form),
cada uma com código Python real, pastas e histórico de execuções.

Uso (a partir de back/):  .venv\\Scripts\\python.exe -m scripts.seed_demo
Idempotente: pula os subdomínios que já existem.
"""
from __future__ import annotations

import datetime as dt
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.config import settings  # noqa: E402
from app.models import (  # noqa: E402
    Build,
    ChatMessage,
    Edge,
    Execution,
    Organization,
    Project,
    ProjectFolder,
    Role,
    SourceFile,
    Stage,
    utcnow,
)
from app.services import storage  # noqa: E402

CONCILIACAO_CARTOES = '''"""Concilia vendas do sistema com o extrato da operadora de cartão."""
import pandas as pd
from flowdesk_sdk import get_input, set_output, output_path, log


def main():
    data = get_input()
    df_vendas = pd.read_excel(data["vendas"])
    df_operadora = pd.read_excel(data["extrato_operadora"])
    log(f"{len(df_vendas)} vendas x {len(df_operadora)} lançamentos da operadora")

    df_vendas["_chave"] = df_vendas["NSU"].astype(str).str.strip()
    df_operadora["_chave"] = df_operadora["NSU"].astype(str).str.strip()

    m = df_vendas.merge(df_operadora, on="_chave", how="outer", indicator=True,
                        suffixes=("_venda", "_operadora"))
    nao_recebidas = m[m["_merge"] == "left_only"]
    sem_venda = m[m["_merge"] == "right_only"]
    ok = m[m["_merge"] == "both"].copy()
    ok["_dif"] = (ok["Valor_venda"] - ok["Valor_operadora"]).round(2)
    divergentes = ok[ok["_dif"] != 0]

    out = output_path("conciliacao_cartoes.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        nao_recebidas.to_excel(w, sheet_name="Nao_recebidas", index=False)
        sem_venda.to_excel(w, sheet_name="Sem_venda", index=False)
        divergentes.to_excel(w, sheet_name="Valor_divergente", index=False)

    resumo = {
        "conciliadas": int(len(ok) - len(divergentes)),
        "nao_recebidas": int(len(nao_recebidas)),
        "sem_venda": int(len(sem_venda)),
        "valor_divergente": int(len(divergentes)),
        "taxa_media": float(round(ok["_dif"].abs().mean() or 0, 2)),
    }
    log("Resumo:", resumo)
    set_output({"arquivo_resultado": str(out), "resumo": resumo})


if __name__ == "__main__":
    main()
'''

VALIDA_NFE = '''"""Lê um lote de XMLs de NF-e e valida chave de acesso, CNPJ e totais."""
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
from flowdesk_sdk import get_input, set_output, output_path, log

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}
PESOS = [2, 3, 4, 5, 6, 7, 8, 9]


def dv_chave(chave43: str) -> int:
    soma = 0
    for i, d in enumerate(reversed(chave43)):
        soma += int(d) * PESOS[i % 8]
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def main():
    data = get_input()
    linhas = []
    with zipfile.ZipFile(data["lote_xml"]) as z:
        nomes = [n for n in z.namelist() if n.lower().endswith(".xml")]
        log(f"{len(nomes)} XMLs no lote")
        for nome in nomes:
            root = ET.fromstring(z.read(nome))
            inf = root.find(".//n:infNFe", NS)
            chave = (inf.get("Id") or "")[3:] if inf is not None else ""
            emit = root.findtext(".//n:emit/n:CNPJ", "", NS)
            total = float(root.findtext(".//n:ICMSTot/n:vNF", "0", NS))
            valida = len(chave) == 44 and dv_chave(chave[:43]) == int(chave[43])
            linhas.append({
                "arquivo": nome, "chave": chave, "cnpj_emitente": emit,
                "valor": total, "chave_valida": valida,
                "numero": root.findtext(".//n:ide/n:nNF", "", NS),
                "emissao": root.findtext(".//n:ide/n:dhEmi", "", NS)[:10],
            })

    df = pd.DataFrame(linhas)
    out = output_path("notas_validadas.xlsx")
    df.to_excel(out, index=False)
    resumo = {
        "notas": len(df),
        "invalidas": int((~df["chave_valida"]).sum()) if len(df) else 0,
        "valor_total": float(round(df["valor"].sum(), 2)) if len(df) else 0.0,
    }
    log("Resumo:", resumo)
    set_output({"arquivo_resultado": str(out), "resumo": resumo})


if __name__ == "__main__":
    main()
'''

CONFERE_FOLHA = '''"""Compara a folha do mês com a do mês anterior e aponta variações relevantes."""
import pandas as pd
from flowdesk_sdk import get_input, set_output, output_path, log


def main():
    data = get_input()
    limite = float(data.get("limite_variacao") or 10)
    atual = pd.read_excel(data["folha_atual"])
    anterior = pd.read_excel(data["folha_anterior"])
    log(f"{len(atual)} colaboradores no mês atual, {len(anterior)} no anterior")

    m = atual.merge(anterior, on="Matricula", how="outer",
                    suffixes=("_atual", "_anterior"), indicator=True)
    admitidos = m[m["_merge"] == "left_only"]
    desligados = m[m["_merge"] == "right_only"]

    comp = m[m["_merge"] == "both"].copy()
    comp["variacao_pct"] = (
        (comp["Liquido_atual"] - comp["Liquido_anterior"])
        / comp["Liquido_anterior"].replace(0, pd.NA) * 100
    ).round(2)
    alertas = comp[comp["variacao_pct"].abs() > limite]

    out = output_path("conferencia_folha.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        alertas.to_excel(w, sheet_name="Variacoes", index=False)
        admitidos.to_excel(w, sheet_name="Admitidos", index=False)
        desligados.to_excel(w, sheet_name="Desligados", index=False)

    resumo = {
        "colaboradores": int(len(comp)),
        "acima_do_limite": int(len(alertas)),
        "admitidos": int(len(admitidos)),
        "desligados": int(len(desligados)),
        "limite_pct": limite,
    }
    log("Resumo:", resumo)
    set_output({"arquivo_resultado": str(out), "resumo": resumo})


if __name__ == "__main__":
    main()
'''

EXTRATO_DOMINIO = '''"""Converte extrato bancário (CSV) para o layout de importação do Domínio."""
import csv
import re
from flowdesk_sdk import get_input, set_output, output_path, log

# regra simples de classificação por histórico -> conta contábil
REGRAS = [
    (r"(?i)tarifa|cesta|manuten", "4113"),
    (r"(?i)pix|ted|doc", "1102"),
    (r"(?i)fgts|inss|darf|das", "2131"),
    (r"(?i)energia|luz|agua|telefon", "4121"),
]
CONTA_PADRAO = "9999"


def classifica(historico: str) -> str:
    for padrao, conta in REGRAS:
        if re.search(padrao, historico):
            return conta
    return CONTA_PADRAO


def main():
    data = get_input()
    conta_banco = data.get("conta_banco") or "1101"
    linhas, sem_classificacao = [], 0

    with open(data["extrato"], encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            valor = float(str(row["valor"]).replace(".", "").replace(",", "."))
            conta = classifica(row.get("historico", ""))
            if conta == CONTA_PADRAO:
                sem_classificacao += 1
            debito, credito = (conta_banco, conta) if valor > 0 else (conta, conta_banco)
            linhas.append([row["data"], debito, credito, f"{abs(valor):.2f}".replace(".", ","),
                           "0", row.get("historico", "")[:200]])

    out = output_path("lancamentos_dominio.txt")
    with open(out, "w", encoding="latin-1", errors="replace") as f:
        for l in linhas:
            f.write("|".join(["6000"] + l) + "\\n")

    resumo = {"lancamentos": len(linhas), "sem_classificacao": sem_classificacao,
              "conta_banco": conta_banco}
    log("Resumo:", resumo)
    set_output({"arquivo_resultado": str(out), "resumo": resumo})


if __name__ == "__main__":
    main()
'''

CONTRATOS_VENCENDO = '''"""Lista contratos que vencem na janela informada e monta o aviso por e-mail."""
import datetime as dt
import pandas as pd
from flowdesk_sdk import get_input, set_output, output_path, log


def main():
    data = get_input()
    dias = int(data.get("dias") or 30)
    df = pd.read_excel(data["contratos"])
    df["Vencimento"] = pd.to_datetime(df["Vencimento"]).dt.date

    hoje = dt.date.today()
    limite = hoje + dt.timedelta(days=dias)
    venc = df[(df["Vencimento"] >= hoje) & (df["Vencimento"] <= limite)].copy()
    venc["dias_restantes"] = venc["Vencimento"].map(lambda d: (d - hoje).days)
    venc = venc.sort_values("dias_restantes")
    vencidos = df[df["Vencimento"] < hoje]
    log(f"{len(venc)} contratos vencem em até {dias} dias; {len(vencidos)} já vencidos")

    out = output_path("contratos_a_vencer.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        venc.to_excel(w, sheet_name="A_vencer", index=False)
        vencidos.to_excel(w, sheet_name="Vencidos", index=False)

    corpo = "\\n".join(
        f"- {r.Cliente}: {r.Objeto} vence em {r.Vencimento} ({r.dias_restantes} dias)"
        for r in venc.itertuples()
    )
    resumo = {"a_vencer": int(len(venc)), "vencidos": int(len(vencidos)), "janela_dias": dias}
    set_output({"arquivo_resultado": str(out), "resumo": resumo, "aviso": corpo})


if __name__ == "__main__":
    main()
'''

HORAS_CLIENTE = '''"""Consolida o apontamento de horas por cliente e colaborador."""
import pandas as pd
from flowdesk_sdk import get_input, set_output, output_path, log


def main():
    data = get_input()
    df = pd.read_excel(data["apontamentos"])
    df["Horas"] = pd.to_numeric(df["Horas"], errors="coerce").fillna(0)
    log(f"{len(df)} apontamentos, {df['Cliente'].nunique()} clientes")

    por_cliente = df.groupby("Cliente", as_index=False)["Horas"].sum()
    por_pessoa = df.groupby(["Colaborador", "Cliente"], as_index=False)["Horas"].sum()
    if "Valor_hora" in df.columns:
        df["Faturavel"] = df["Horas"] * df["Valor_hora"]
        por_cliente = por_cliente.merge(
            df.groupby("Cliente", as_index=False)["Faturavel"].sum(), on="Cliente")

    out = output_path("horas_por_cliente.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        por_cliente.sort_values("Horas", ascending=False).to_excel(
            w, sheet_name="Por_cliente", index=False)
        por_pessoa.to_excel(w, sheet_name="Por_colaborador", index=False)

    resumo = {"apontamentos": int(len(df)), "clientes": int(df["Cliente"].nunique()),
              "horas_totais": float(round(df["Horas"].sum(), 2))}
    log("Resumo:", resumo)
    set_output({"arquivo_resultado": str(out), "resumo": resumo})


if __name__ == "__main__":
    main()
'''

AMOSTRAGEM = '''"""Seleciona amostra de lançamentos para teste de auditoria (valor + aleatória)."""
import random
import pandas as pd
from flowdesk_sdk import get_input, set_output, output_path, log


def main():
    data = get_input()
    tamanho = int(data.get("tamanho_amostra") or 25)
    df = pd.read_excel(data["razao"])
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0).abs()
    log(f"{len(df)} lançamentos, total {df['Valor'].sum():.2f}")

    n_top = min(tamanho // 2, len(df))
    top = df.nlargest(n_top, "Valor")
    resto = df.drop(top.index)
    n_aleatorio = min(tamanho - n_top, len(resto))
    aleatoria = resto.sample(n=n_aleatorio, random_state=random.randint(1, 9999)) \\
        if n_aleatorio else resto.head(0)

    amostra = pd.concat([top.assign(criterio="valor"),
                         aleatoria.assign(criterio="aleatoria")])
    out = output_path("amostra_auditoria.xlsx")
    amostra.to_excel(out, index=False)

    cobertura = float(round(amostra["Valor"].sum() / (df["Valor"].sum() or 1) * 100, 2))
    resumo = {"populacao": int(len(df)), "amostra": int(len(amostra)),
              "cobertura_valor_pct": cobertura}
    log("Resumo:", resumo)
    set_output({"arquivo_resultado": str(out), "resumo": resumo})


if __name__ == "__main__":
    main()
'''

FATURAMENTO = '''"""Consolida o faturamento do mês por serviço e cliente."""
import pandas as pd
from flowdesk_sdk import get_input, set_output, output_path, log


def main():
    data = get_input()
    df = pd.read_excel(data["notas_emitidas"])
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0)
    df["Emissao"] = pd.to_datetime(df["Emissao"])
    df["Competencia"] = df["Emissao"].dt.to_period("M").astype(str)
    log(f"{len(df)} notas, competências: {sorted(df['Competencia'].unique())}")

    por_servico = df.groupby(["Competencia", "Servico"], as_index=False)["Valor"].sum()
    por_cliente = df.groupby(["Competencia", "Cliente"], as_index=False)["Valor"].sum()
    mensal = df.groupby("Competencia", as_index=False)["Valor"].sum()
    mensal["variacao_pct"] = (mensal["Valor"].pct_change() * 100).round(2)

    out = output_path("faturamento_mensal.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        mensal.to_excel(w, sheet_name="Mensal", index=False)
        por_servico.to_excel(w, sheet_name="Por_servico", index=False)
        por_cliente.sort_values("Valor", ascending=False).to_excel(
            w, sheet_name="Por_cliente", index=False)

    resumo = {"notas": int(len(df)), "faturamento_total": float(round(df["Valor"].sum(), 2)),
              "ticket_medio": float(round(df["Valor"].mean(), 2))}
    log("Resumo:", resumo)
    set_output({"arquivo_resultado": str(out), "resumo": resumo})


if __name__ == "__main__":
    main()
'''

# name, subdomain, pasta, status, descrição, campos do form, script, arquivo, runs, erros
SPECS = [
    {
        "name": "Conciliação de Cartões",
        "sub": "conciliacao-cartoes",
        "folder": "Financeiro",
        "status": "live",
        "desc": "Cruza as vendas do sistema com o extrato da operadora e aponta o que não caiu.",
        "fields": [
            {"name": "vendas", "label": "Vendas do sistema (.xlsx)", "type": "file"},
            {"name": "extrato_operadora", "label": "Extrato da operadora (.xlsx)", "type": "file"},
        ],
        "file": "conciliar.py",
        "code": CONCILIACAO_CARTOES,
        "reqs": "pandas\nopenpyxl\n",
        "runs": 42,
        "erros": 2,
        "log": "148 vendas x 151 lançamentos da operadora\nResumo: {'conciliadas': 143, 'nao_recebidas': 5, 'sem_venda': 8, 'valor_divergente': 3}",
    },
    {
        "name": "Validador de NF-e",
        "sub": "valida-nfe",
        "folder": "Fiscal",
        "status": "live",
        "desc": "Lê um lote de XMLs, valida a chave de acesso e consolida os totais por emitente.",
        "fields": [
            {"name": "lote_xml", "label": "Lote de XMLs (.zip)", "type": "file"},
        ],
        "file": "validar.py",
        "code": VALIDA_NFE,
        "reqs": "pandas\nopenpyxl\n",
        "runs": 67,
        "erros": 4,
        "log": "213 XMLs no lote\nResumo: {'notas': 213, 'invalidas': 1, 'valor_total': 1842390.55}",
    },
    {
        "name": "Conferência de Folha",
        "sub": "confere-folha",
        "folder": "Pessoal",
        "status": "live",
        "desc": "Compara a folha do mês com a anterior e destaca variações acima do limite.",
        "fields": [
            {"name": "folha_atual", "label": "Folha do mês (.xlsx)", "type": "file"},
            {"name": "folha_anterior", "label": "Folha do mês anterior (.xlsx)", "type": "file"},
            {"name": "limite_variacao", "label": "Limite de variação (%)", "type": "number"},
        ],
        "file": "conferir.py",
        "code": CONFERE_FOLHA,
        "reqs": "pandas\nopenpyxl\n",
        "runs": 18,
        "erros": 1,
        "log": "312 colaboradores no mês atual, 309 no anterior\nResumo: {'acima_do_limite': 11, 'admitidos': 6, 'desligados': 3}",
    },
    {
        "name": "Extrato Bancário para Domínio",
        "sub": "extrato-dominio",
        "folder": "Operações",
        "status": "live",
        "desc": "Classifica o extrato por histórico e gera o arquivo de importação do Domínio.",
        "fields": [
            {"name": "extrato", "label": "Extrato bancário (.csv)", "type": "file"},
            {"name": "conta_banco", "label": "Conta contábil do banco", "type": "text"},
        ],
        "file": "converter.py",
        "code": EXTRATO_DOMINIO,
        "reqs": "\n",
        "runs": 128,
        "erros": 9,
        "log": "Resumo: {'lancamentos': 487, 'sem_classificacao': 34, 'conta_banco': '1101'}",
    },
    {
        "name": "Contratos a Vencer",
        "sub": "contratos-vencendo",
        "folder": "Operações",
        "status": "live",
        "desc": "Monitora a base de contratos e avisa o que vence nos próximos dias.",
        "fields": [
            {"name": "contratos", "label": "Base de contratos (.xlsx)", "type": "file"},
            {"name": "dias", "label": "Janela (dias)", "type": "number"},
        ],
        "file": "monitorar.py",
        "code": CONTRATOS_VENCENDO,
        "reqs": "pandas\nopenpyxl\n",
        "runs": 30,
        "erros": 0,
        "log": "9 contratos vencem em até 30 dias; 2 já vencidos",
    },
    {
        "name": "Amostragem para Auditoria",
        "sub": "amostragem-auditoria",
        "folder": None,
        "status": "live",
        "desc": "Seleciona amostra de lançamentos por valor e aleatória, com cobertura calculada.",
        "fields": [
            {"name": "razao", "label": "Razão contábil (.xlsx)", "type": "file"},
            {"name": "tamanho_amostra", "label": "Tamanho da amostra", "type": "number"},
        ],
        "file": "amostrar.py",
        "code": AMOSTRAGEM,
        "reqs": "pandas\nopenpyxl\n",
        "runs": 23,
        "erros": 1,
        "log": "8104 lançamentos, total 12908431.77\nResumo: {'amostra': 25, 'cobertura_valor_pct': 61.4}",
    },
    {
        "name": "Horas por Cliente",
        "sub": "horas-cliente",
        "folder": None,
        "status": "draft",
        "desc": "Consolida o apontamento de horas por cliente e colaborador para faturamento.",
        "fields": [
            {"name": "apontamentos", "label": "Apontamentos do mês (.xlsx)", "type": "file"},
        ],
        "file": "consolidar.py",
        "code": HORAS_CLIENTE,
        "reqs": "pandas\nopenpyxl\n",
        "runs": 4,
        "erros": 2,
        "log": "1240 apontamentos, 37 clientes",
    },
    {
        "name": "Faturamento Mensal",
        "sub": "faturamento-mensal",
        "folder": "Financeiro",
        "status": "draft",
        "desc": "Consolida notas emitidas por serviço, cliente e competência.",
        "fields": [
            {"name": "notas_emitidas", "label": "Notas emitidas (.xlsx)", "type": "file"},
        ],
        "file": "consolidar.py",
        "code": FATURAMENTO,
        "reqs": "pandas\nopenpyxl\n",
        "runs": 6,
        "erros": 0,
        "log": "421 notas, competências: ['2026-05', '2026-06', '2026-07']",
    },
]


# Pedido original que deu origem a cada automação. A resposta do assistente é
# derivada do próprio spec, para não repetir a descrição em dois lugares.
PEDIDOS = {
    "conciliacao-cartoes": "Preciso cruzar as vendas do nosso sistema com o extrato da "
    "operadora de cartão e ver o que não caiu na conta.",
    "valida-nfe": "Recebo um zip com os XMLs das notas do mês. Quero validar a chave de "
    "acesso de cada uma e somar os totais por emitente.",
    "confere-folha": "Todo mês eu comparo a folha com a do mês anterior no olho. Quero que "
    "o sistema aponte quem variou acima de um limite que eu escolho.",
    "extrato-dominio": "Tenho o extrato do banco em CSV e preciso do arquivo pronto para "
    "importar no Domínio, já classificado pelo histórico do lançamento.",
    "contratos-vencendo": "Quero uma rotina que olhe a base de contratos e liste o que vence "
    "nos próximos dias, para eu avisar o cliente antes.",
    "amostragem-auditoria": "Para a auditoria eu preciso selecionar uma amostra do razão: os "
    "maiores valores mais alguns aleatórios, e saber quanto do total isso cobre.",
    "horas-cliente": "Preciso consolidar os apontamentos de horas por cliente e por "
    "colaborador para fechar o faturamento do mês.",
    "faturamento-mensal": "Quero consolidar as notas emitidas por serviço, por cliente e por "
    "competência, com a variação de um mês para o outro.",
}


def add_chat(db, proj: Project, spec: dict) -> bool:
    """Conversa que originou a automação, para o Smart Chat não abrir vazio.
    Idempotente: não faz nada se o projeto já tem mensagens."""
    if db.query(ChatMessage).filter(ChatMessage.project_id == proj.id).first():
        return False
    campos = ", ".join(f["label"] for f in spec["fields"])
    quando = utcnow() - dt.timedelta(days=61)
    resposta = (
        f"Montei a **{spec['name']}** em três etapas:\n\n"
        f"1. **Entrada** — formulário com: {campos}.\n"
        f"2. **Processar** — script `{spec['file']}` que faz o trabalho.\n"
        f"3. **Resultado** — a planilha para baixar, com o resumo do que foi processado.\n\n"
        + (
            "Está no ar. Pode rodar pelo Assistente ou pelo link publicado."
            if spec["status"] == "live"
            else "Ainda é rascunho. Teste pelo Assistente e publique quando estiver bom."
        )
    )
    db.add_all([
        ChatMessage(project_id=proj.id, role="user", content=PEDIDOS[spec["sub"]],
                    created_at=quando),
        ChatMessage(project_id=proj.id, role="assistant", content=resposta,
                    created_at=quando + dt.timedelta(seconds=40)),
    ])
    return True


def get_folder(db, org_id: int, name: str | None) -> int | None:
    if not name:
        return None
    f = (
        db.query(ProjectFolder)
        .filter(ProjectFolder.org_id == org_id, ProjectFolder.name == name)
        .first()
    )
    if not f:
        f = ProjectFolder(org_id=org_id, name=name)
        db.add(f)
        db.flush()
    return f.id


def add_executions(db, proj: Project, stage: Stage, spec: dict, rnd: random.Random) -> None:
    """Histórico sintético, mas coerente: n execuções nos últimos 60 dias, sendo
    `erros` com falha. ponytail: dados plausíveis, não execuções reais do runner."""
    agora = dt.datetime.utcnow()
    total, erros = spec["runs"], spec["erros"]
    for i in range(total):
        inicio = agora - dt.timedelta(
            days=rnd.uniform(0, 60), minutes=rnd.uniform(0, 600)
        )
        falhou = i < erros
        dur = rnd.uniform(1.5, 45.0)
        db.add(
            Execution(
                id=str(uuid.uuid4()),
                project_id=proj.id,
                stage_id=stage.id,
                stage_name=stage.name,
                stage_type="script",
                status="error" if falhou else "success",
                stdout="" if falhou else spec["log"],
                stderr=(
                    "KeyError: coluna esperada não encontrada na planilha enviada"
                    if falhou
                    else ""
                ),
                input_data={f["name"]: "<arquivo enviado>" for f in spec["fields"]},
                output_data={} if falhou else {"resumo": "ok"},
                started_at=inicio,
                finished_at=inicio + dt.timedelta(seconds=dur),
            )
        )


def main() -> None:
    alvo = settings.db_url.split("@")[-1].split("/")[0] if settings.db_url else "sqlite local"
    print(f"Banco alvo: {alvo}")
    db = SessionLocal()
    rnd = random.Random(7)
    try:
        org = db.query(Organization).first()
        if not org:
            raise SystemExit("Nenhuma organização no banco: rode o seed inicial antes.")

        criados = 0
        for spec in SPECS:
            existente = db.query(Project).filter(Project.subdomain == spec["sub"]).first()
            if existente:
                novo_chat = add_chat(db, existente, spec)
                print(f"- {spec['name']}: já existe"
                      + (", conversa adicionada" if novo_chat else ", pulando"))
                continue

            proj = Project(
                org_id=org.id,
                folder_id=get_folder(db, org.id, spec["folder"]),
                name=spec["name"],
                subdomain=spec["sub"],
                description=spec["desc"],
                status=spec["status"],
                output_folder_name="resultados",
                access_mode="domain",
                allowed_domain="irko.com.br",
            )
            db.add(proj)
            db.flush()
            storage.ensure_project_dirs(proj)

            entrada = Stage(
                project_id=proj.id, type="form", name="Entrada", key="entrada",
                pos_x=40, pos_y=120,
                config={
                    "title": spec["name"],
                    "description": spec["desc"],
                    "submit_label": "Executar",
                    "mode": "input",
                    "fields": spec["fields"],
                },
            )
            script = Stage(
                project_id=proj.id, type="script", name="Processar", key="processar",
                entry_file=spec["file"], timeout_seconds=180, pos_x=360, pos_y=120,
                config={"description": spec["desc"]},
            )
            saida = Stage(
                project_id=proj.id, type="form", name="Resultado", key="resultado",
                pos_x=680, pos_y=120,
                config={
                    "title": f"Resultado — {spec['name']}",
                    "mode": "result",
                    "result_file_key": "arquivo_resultado",
                    "summary_key": "resumo",
                },
            )
            db.add_all([entrada, script, saida])
            db.flush()
            db.add_all([
                Edge(project_id=proj.id, source_stage_id=entrada.id,
                     target_stage_id=script.id, variable_label="entrada"),
                Edge(project_id=proj.id, source_stage_id=script.id,
                     target_stage_id=saida.id, variable_label="resultado"),
            ])
            db.add_all([
                SourceFile(project_id=proj.id, path=spec["file"], content=spec["code"]),
                SourceFile(project_id=proj.id, path="requirements.txt", content=spec["reqs"]),
                SourceFile(project_id=proj.id, path="README.md",
                           content=f"# {spec['name']}\n\n{spec['desc']}\n"),
            ])
            db.add_all([
                Role(project_id=proj.id, name="User", description="Execução."),
                Role(project_id=proj.id, name="Dev", description="Edição."),
            ])
            if spec["status"] == "live":
                db.add(Build(project_id=proj.id, hash=uuid.uuid4().hex[:8],
                             framework_version="1.0.0", status="live",
                             snapshot={"note": "build de demonstração"}))

            add_chat(db, proj, spec)
            add_executions(db, proj, script, spec, rnd)
            storage.materialize_sources(db, proj)
            criados += 1
            print(f"+ {spec['name']} (/app/{spec['sub']}) — {spec['runs']} execuções")

        db.commit()
        print(f"\n{criados} automações criadas.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
