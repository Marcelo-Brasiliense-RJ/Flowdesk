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
'''
