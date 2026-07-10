"""heal_seed_scripts restaura o script canônico do conciliador em bases antigas."""
import sys
from pathlib import Path

BACK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACK))

from app.database import Base, SessionLocal, engine
from app.models import Project, SourceFile
from app.seed import RECONCILE_SCRIPT, heal_seed_scripts, seed_if_empty


def test_heal_restaura_script_defasado(monkeypatch):
    # garante o schema (o teste consulta o banco sem passar pelo lifespan do app)
    Base.metadata.create_all(engine)
    # o seed exige SEED_PASSWORD (senha seed não é mais hardcoded)
    monkeypatch.setenv("SEED_PASSWORD", "test-seed-123")
    seed_if_empty()
    db = SessionLocal()
    proj = db.query(Project).filter(Project.subdomain == "conciliador").first()
    assert proj is not None
    sf = db.query(SourceFile).filter(
        SourceFile.project_id == proj.id, SourceFile.path == "processar.py"
    ).first()
    sf.content = "# versao antiga quebrada\nplanilha_x = None\n"
    proj_id = proj.id  # captura antes do close para evitar DetachedInstanceError
    db.commit()
    db.close()

    curados = heal_seed_scripts()
    assert curados >= 1

    db = SessionLocal()
    sf = db.query(SourceFile).filter(
        SourceFile.project_id == proj_id, SourceFile.path == "processar.py"
    ).first()
    assert sf.content == RECONCILE_SCRIPT
    db.close()
