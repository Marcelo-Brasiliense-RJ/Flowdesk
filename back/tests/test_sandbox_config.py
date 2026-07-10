import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.config import Settings


def test_defaults_do_sandbox_preservam_subprocess():
    s = Settings()
    assert s.execution_backend == "subprocess"  # on-premise não quebra
    assert s.container_image == "flowdesk-runtime:latest"
    assert s.container_memory == "512m"
    assert s.container_cpus == "1"
    assert s.container_pids == 128
    assert s.container_runtime == ""
