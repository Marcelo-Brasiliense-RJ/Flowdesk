"""I2: conversão de .xls fora do padrão sem Excel COM (LibreOffice no Linux)."""
import subprocess
import sys as _sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
_sys.path.insert(0, str(BACK))

from app.services import storage


def test_linux_usa_libreoffice_nao_excel_com(monkeypatch, tmp_path):
    monkeypatch.setattr(storage.sys if hasattr(storage, "sys") else _sys, "platform", "linux", raising=False)
    # garante o platform visto DENTRO de _xls_to_xlsx
    monkeypatch.setattr(_sys, "platform", "linux")
    cmds = {}

    def fake_run(cmd, **k):
        cmds["cmd"] = cmd
        # simula o soffice criando o .xlsx de saída
        out = Path(cmd[cmd.index("--outdir") + 1]) / (Path(cmd[-1]).stem + ".xlsx")
        out.write_bytes(b"xlsx")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    src = tmp_path / "extrato.xls"
    src.write_bytes(b"legado")
    dst = storage._xls_to_xlsx(str(src))
    assert dst and Path(dst).exists()
    assert cmds["cmd"][0] == "soffice"          # portável, não powershell/Excel
    assert "--convert-to" in cmds["cmd"] and "xlsx" in cmds["cmd"]


def test_linux_sem_soffice_retorna_none(monkeypatch, tmp_path):
    monkeypatch.setattr(_sys, "platform", "linux")
    def boom(cmd, **k):
        raise FileNotFoundError("soffice not found")
    monkeypatch.setattr(subprocess, "run", boom)
    src = tmp_path / "x.xls"; src.write_bytes(b"legado")
    assert storage._xls_to_xlsx(str(src)) is None   # falha controlada, não lança
