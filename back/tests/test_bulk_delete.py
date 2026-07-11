import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Build, Execution, Organization, Project, Stage, User
from app.routers.projects import bulk_delete_projects
from app.schemas import BulkDeleteRequest


def _engine_with_fks():
    eng = sa.create_engine("sqlite:///:memory:")
    # espelha o Postgres: força FKs (SQLite as ignora por padrão)
    sa.event.listen(
        eng, "connect", lambda con, _: con.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(eng)
    return eng


def test_bulk_delete_removes_projects_with_executions():
    """Regressão: projeto com execução referenciando um build.

    No Postgres a FK Execution.build_id -> builds.id é enforced, então a ordem
    de purga importa. Reproduz a falha vista em produção (só 1 de N excluído).
    """
    with Session(_engine_with_fks()) as db:
        org = Organization(name="IRKO")
        db.add(org)
        db.flush()
        admin = User(
            org_id=org.id, email="admin@irko.com.br", name="Admin",
            role="admin", hashed_password="x",
        )
        db.add(admin)
        db.flush()
        ids = []
        for i in range(13):
            p = Project(org_id=org.id, name=f"p{i}", subdomain=f"p{i}")
            db.add(p)
            db.flush()
            stage = Stage(project_id=p.id, type="script", name="s", key=f"k{i}")
            db.add(stage)
            build = Build(project_id=p.id, hash="abc123")
            db.add(build)
            db.flush()
            db.add(Execution(
                id=f"e{i}", project_id=p.id, stage_id=stage.id, build_id=build.id,
            ))
            db.flush()
            ids.append(p.id)

        res = bulk_delete_projects(BulkDeleteRequest(ids=ids), db=db, user=admin)

        assert res["deleted"] == 13, res
        assert db.query(Project).count() == 0
