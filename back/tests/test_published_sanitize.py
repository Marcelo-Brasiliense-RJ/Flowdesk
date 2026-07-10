"""S2/S4: o app publicado não expõe traceback cru nem input_data (caminhos do servidor)."""
import json
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.routers.published import _execution_public_view


class _Execu:
    id = "e1"
    status = "error"
    output_data = {"erro": "ValueError: coluna 'X' ausente"}
    stderr = ('Traceback (most recent call last):\n'
              '  File "C:\\\\srv\\\\flowdesk\\\\back\\\\runs\\\\uuid\\\\proc.py", line 3\n'
              'ValueError: coluna \'X\' ausente')
    input_data = {"arquivo": "C:/srv/flowdesk/back/_uploads/uuid/extrato.xlsx"}


def test_view_nao_vaza_input_nem_traceback():
    v = _execution_public_view(_Execu(), progress=[])
    blob = json.dumps(v)
    assert "input" not in v                      # S4: sem input_data
    assert "Traceback" not in blob               # S2: sem traceback cru
    assert "_uploads" not in blob                 # S4: sem caminho de upload do servidor
    assert "srv\\\\flowdesk" not in blob and "srv/flowdesk" not in blob  # sem path do servidor
    assert "coluna 'X' ausente" in v["erro"]     # mensagem amigável preservada


def test_view_sucesso_sem_erro():
    class Ok:
        id = "e2"; status = "success"
        output_data = {"resumo": "ok"}
        stderr = ""
        input_data = {"arquivo": "C:/srv/_uploads/uuid/a.xlsx"}
    v = _execution_public_view(Ok(), progress=[])
    assert v["erro"] == ""
    assert "input" not in v
