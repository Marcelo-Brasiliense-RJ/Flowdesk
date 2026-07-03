"""Disk storage layout per project + file-manager helpers.

Layout under back/storage/<project_id>/:
    _uploads/<uuid>/          raw upload sessions
    uploads/                  organized uploads
    <output_folder_name>/     processed results
    runs/<execution_uuid>/    per-run input.json / output.json

O código executável (script do projeto + flowdesk_sdk.py) NÃO fica aqui: vai para
RUNTIME_SRC_DIR (fora de back/), pois é regravado a cada execução e, sob back/, o
`uvicorn --reload` reiniciaria o servidor no meio do teste. Ver config.RUNTIME_SRC_DIR.
"""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import RUNTIME_SRC_DIR, STORAGE_DIR
from ..models import Project, SourceFile


def project_root(project_id: int) -> Path:
    root = STORAGE_DIR / str(project_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_project_dirs(project: Project) -> Path:
    root = project_root(project.id)
    for sub in ["_uploads", "uploads", project.output_folder_name, "runs"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def materialize_sources(db: Session, project: Project) -> Path:
    """Grava os SourceFile do projeto em RUNTIME_SRC_DIR/<id> (fora de back/) para o
    subprocesso rodar. Fica fora do storage de propósito: assim regravar esses .py a
    cada execução não dispara o watcher do `uvicorn --reload`. Retorna o src_dir, usado
    como PYTHONPATH e local do script; os dados do projeto seguem em STORAGE_DIR."""
    ensure_project_dirs(project)
    src_dir = RUNTIME_SRC_DIR / str(project.id)
    src_dir.mkdir(parents=True, exist_ok=True)
    files = (
        db.query(SourceFile)
        .filter(SourceFile.project_id == project.id, SourceFile.is_dir == False)  # noqa: E712
        .all()
    )
    for f in files:
        try:
            target = safe_join(src_dir, f.path)  # block path traversal in stored paths
        except ValueError:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f.content or "", encoding="utf-8")
    # always provide the runtime SDK helper
    (src_dir / "flowdesk_sdk.py").write_text(_SDK_SOURCE, encoding="utf-8")
    return src_dir


def safe_join(base: Path, *parts: str) -> Path:
    """Join and ensure the result stays within base (prevents traversal)."""
    target = (base.joinpath(*parts)).resolve()
    base_resolved = base.resolve()
    if base_resolved != target and base_resolved not in target.parents:
        raise ValueError("Path traversal detected")
    return target


def list_dir(root: Path, rel: str) -> list[dict]:
    folder = safe_join(root, rel) if rel else root
    if not folder.exists() or not folder.is_dir():
        return []
    entries: list[dict] = []
    for p in sorted(folder.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        stat = p.stat()
        entries.append(
            {
                "name": p.name,
                "is_dir": p.is_dir(),
                "size": stat.st_size if p.is_file() else 0,
                "modified_at": dt.datetime.fromtimestamp(
                    stat.st_mtime, dt.timezone.utc
                ).isoformat(),
                "path": str(p.relative_to(root)).replace("\\", "/"),
            }
        )
    return entries


def delete_path(root: Path, rel: str) -> None:
    target = safe_join(root, rel)
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def read_progress(project_id: int, execution_id: str) -> list[dict]:
    """Eventos progress() de uma execução (vazio se não houver)."""
    import json as _json

    p = STORAGE_DIR / str(project_id) / "runs" / execution_id / "progress.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(_json.loads(line))
        except Exception:
            continue
    return out


_SDK_SOURCE = '''"""FlowDesk runtime SDK injected into every project (do not edit).

Use inside Script stages to read the upstream input and write results:

    from flowdesk_sdk import get_input, set_output, output_path, log, progress

    data = get_input()                 # dict with upstream form values
    src = data["arquivo"]              # path to an uploaded file
    out = output_path("resultado.xlsx")
    # ... process ...
    set_output({"arquivo_resultado": str(out), "linhas": 42})
"""
import json
import os
from pathlib import Path

_INPUT = os.environ.get("FLOWDESK_INPUT", "")
_OUTPUT = os.environ.get("FLOWDESK_OUTPUT", "")
_OUTPUT_DIR = os.environ.get("FLOWDESK_OUTPUT_DIR", ".")


def get_input() -> dict:
    if _INPUT and Path(_INPUT).exists():
        return json.loads(Path(_INPUT).read_text(encoding="utf-8"))
    return {}


def get_file(name=None):
    """Caminho do arquivo enviado no Form anterior. get_file() pega o 1o arquivo;
    get_file(i) pega o i-esimo. Com N arquivos o Form nomeia os campos
    'arquivo1'..'arquivoN', entao get_file(i) resolve 'arquivo{i+1}' por NOME (a
    ordem dos campos, que e a ordem do plano), e so cai no posicional se esse nome
    nao existir. Isso evita alimentar o parser errado quando o usuario escolhe os
    arquivos fora de ordem (a ordem de escolha vira a ordem de insercao no input)."""
    data = get_input()
    if isinstance(name, str) and data.get(name):
        return data[name]
    paths = [v for v in data.values() if isinstance(v, str) and v and Path(v).exists()]
    if isinstance(name, int):
        by_field = data.get(f"arquivo{name + 1}")
        if isinstance(by_field, str) and by_field and Path(by_field).exists():
            return by_field
        return paths[name] if name < len(paths) else None
    return paths[0] if paths else data.get("arquivo")


def output_path(name: str) -> Path:
    d = Path(_OUTPUT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _json_default(o):
    # numpy/pandas escalares expõem .item() -> int/float nativo (não string)
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)


def set_output(data) -> None:
    if not isinstance(data, dict):
        data = {"resultado": data}
    Path(_OUTPUT).write_text(
        json.dumps(data, ensure_ascii=False, default=_json_default), encoding="utf-8"
    )


def log(*args) -> None:
    print(*args, flush=True)


_RUN_DIR = os.environ.get("FLOWDESK_RUN_DIR", ".")


def progress(etapa, detalhe="") -> None:
    """Etapa visível ao usuário na linha do tempo da execução.
    Use linguagem simples: progress("Lendo extrato", "564 lançamentos")."""
    import datetime as _dt
    rec = {"etapa": str(etapa), "detalhe": str(detalhe),
           "ts": _dt.datetime.now().strftime("%H:%M:%S")}
    p = Path(_RUN_DIR) / "progress.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    print(f"[etapa] {etapa} {detalhe}", flush=True)


def get_table(nome) -> list:
    """Linhas (list[dict]) de uma tabela interna do projeto (ex: regras De/Para).
    O runtime materializa as tabelas em tables.json antes da execução."""
    p = Path(_RUN_DIR) / "tables.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get(nome, [])


def read_table(path, **kw):
    """Lê planilha (xlsx/xls/csv) com tolerância a xls fora do padrão (Domínio).
    Cadeia: pandas normal -> conversão via Excel instalado -> erro claro."""
    import pandas as pd
    spath = str(path)
    ext = os.path.splitext(spath)[1].lower()
    if ext == ".csv":
        return pd.read_csv(spath, **kw)
    try:
        return pd.read_excel(spath, **kw)
    except Exception:
        if ext != ".xls":
            raise
    # xls do Domínio: converte com o Excel da máquina (on-premise Windows)
    import subprocess, tempfile
    dst = os.path.join(tempfile.gettempdir(), "fd_conv_" + os.path.basename(spath) + ".xlsx")
    ps = (
        "$x=New-Object -ComObject Excel.Application;$x.Visible=$false;"
        "$x.DisplayAlerts=$false;$wb=$x.Workbooks.Open('{src}');"
        "$wb.SaveAs('{dst}',51);$wb.Close($false);$x.Quit()"
    ).format(src=spath.replace("'", "''"), dst=dst.replace("'", "''"))
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=120)
    if r.returncode != 0 or not os.path.exists(dst):
        detalhe = (r.stderr or b"").decode("latin1", "replace").strip()[:300]
        raise RuntimeError(
            "Não consegui ler este .xls (formato fora do padrão e a conversão "
            "via Excel falhou). Exporte como .xlsx ou .csv e envie de novo. "
            f"[detalhe: {detalhe or 'sem stderr'}]")
    return pd.read_excel(dst, **kw)


# ---- PDF / OCR (leitura de documentos, com confiança para validação) ----
_OCR_ENGINE = None


def _ocr_image(path):
    """OCR local (RapidOCR) de uma imagem. Retorna [(texto, confianca), ...]."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
    res, _ = _OCR_ENGINE(str(path))
    return [(t, float(s)) for _box, t, s in (res or [])]


def extract_document(path=None, ocr_threshold=0.8):
    """Lê PDF (editável OU escaneado) ou imagem e devolve texto + confiança.

    Detecta sozinho: PDF com camada de texto -> extrai direto (sem OCR);
    PDF sem texto ou imagem -> OCR local (RapidOCR). Imports são lazy: scripts
    que não usam isto não carregam as libs pesadas.

    Retorna dict:
      text: str (texto completo)
      lines: [{text, confidence(0..1 ou None), page}]
      source: "pdf_text" | "ocr" | "raw_text" | "unsupported" | "none"
      mean_confidence: float | None
      low_confidence: linhas abaixo de ocr_threshold (etapa 1 da validação)
      needs_review: True quando veio de OCR e há baixa confiança
    """
    import os
    # revisão humana: se a pessoa corrigiu o texto na tela de revisão e pediu
    # reprocesso, o texto corrigido substitui o OCR (fonte mais confiável).
    corrigido = get_input().get("_texto_corrigido")
    if isinstance(corrigido, str) and corrigido.strip():
        linhas = [{"text": l, "confidence": None, "page": 1}
                  for l in corrigido.splitlines() if l.strip()]
        return {"text": corrigido, "lines": linhas, "source": "human_review",
                "mean_confidence": None, "low_confidence": [], "needs_review": False}
    if path is None:
        path = get_file()
    if not path:
        return {"text": "", "lines": [], "source": "none",
                "mean_confidence": None, "low_confidence": [], "needs_review": False}
    ext = os.path.splitext(str(path))[1].lower()
    lines = []
    source = "ocr"

    if ext == ".pdf":
        import pdfplumber
        pages_text = []
        with pdfplumber.open(str(path)) as pdf:
            for pg in pdf.pages:
                pages_text.append(pg.extract_text() or "")
        if len("".join(pages_text).strip()) >= 20:
            source = "pdf_text"
            for i, t in enumerate(pages_text):
                for ln in t.splitlines():
                    if ln.strip():
                        lines.append({"text": ln, "confidence": None, "page": i + 1})
        else:
            import fitz
            doc = fitz.open(str(path))
            try:
                for i, page in enumerate(doc):
                    pix = page.get_pixmap(dpi=200)
                    tmp = str(path) + ".p" + str(i) + ".png"
                    pix.save(tmp)
                    for t, s in _ocr_image(tmp):
                        lines.append({"text": t, "confidence": s, "page": i + 1})
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            finally:
                doc.close()
    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"):
        for t, s in _ocr_image(path):
            lines.append({"text": t, "confidence": s, "page": 1})
    else:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                txt = fh.read()
            return {"text": txt,
                    "lines": [{"text": l, "confidence": None, "page": 1}
                              for l in txt.splitlines() if l.strip()],
                    "source": "raw_text", "mean_confidence": None,
                    "low_confidence": [], "needs_review": False}
        except Exception:
            return {"text": "", "lines": [], "source": "unsupported",
                    "mean_confidence": None, "low_confidence": [], "needs_review": False}

    confs = [l["confidence"] for l in lines if l["confidence"] is not None]
    mean_conf = round(sum(confs) / len(confs), 4) if confs else None
    low = [l for l in lines if l["confidence"] is not None and l["confidence"] < ocr_threshold]
    needs_review = source == "ocr" and (bool(low) or (mean_conf is not None and mean_conf < 0.85))
    return {"text": "\\n".join(l["text"] for l in lines), "lines": lines,
            "source": source, "mean_confidence": mean_conf,
            "low_confidence": low, "needs_review": needs_review}


def extract_text(path=None):
    """Atalho: retorna só o texto de um PDF/imagem (editável ou escaneado)."""
    return extract_document(path).get("text", "")
'''
