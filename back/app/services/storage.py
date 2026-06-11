"""Disk storage layout per project + file-manager helpers.

Layout under back/storage/<project_id>/:
    src/                      materialized source code (from SourceFile rows)
    _uploads/<uuid>/          raw upload sessions
    uploads/                  organized uploads
    <output_folder_name>/     processed results
    runs/<execution_uuid>/    per-run input.json / output.json
"""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import STORAGE_DIR
from ..models import Project, SourceFile


def project_root(project_id: int) -> Path:
    root = STORAGE_DIR / str(project_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_project_dirs(project: Project) -> Path:
    root = project_root(project.id)
    for sub in ["src", "_uploads", "uploads", project.output_folder_name, "runs"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def materialize_sources(db: Session, project: Project) -> Path:
    """Write all SourceFile rows to <project>/src so scripts can run."""
    root = ensure_project_dirs(project)
    src_dir = root / "src"
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


_SDK_SOURCE = '''"""FlowDesk runtime SDK injected into every project (do not edit).

Use inside Script stages to read the upstream input and write results:

    from flowdesk_sdk import get_input, set_output, output_path, log

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
    """Caminho do arquivo enviado no Form anterior, independente do nome do campo.
    Use assim: df = pd.read_excel(get_file()). Para o 2o arquivo: get_file(1)."""
    data = get_input()
    if isinstance(name, str) and data.get(name):
        return data[name]
    paths = [v for v in data.values() if isinstance(v, str) and v and Path(v).exists()]
    if isinstance(name, int):
        return paths[name] if name < len(paths) else None
    return paths[0] if paths else data.get("arquivo")


def output_path(name: str) -> Path:
    d = Path(_OUTPUT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def set_output(data) -> None:
    if not isinstance(data, dict):
        data = {"resultado": data}
    # default=str serializa Path e outros objetos com seguranca
    Path(_OUTPUT).write_text(
        json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8"
    )


def log(*args) -> None:
    print(*args, flush=True)


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
