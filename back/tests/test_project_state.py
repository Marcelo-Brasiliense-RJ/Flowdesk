import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Organization, Project


def test_project_orchestration_defaults_after_flush():
    eng = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        org = Organization(name="IRKO")
        s.add(org)
        s.flush()
        p = Project(org_id=org.id, name="x", subdomain="x")
        s.add(p)
        s.flush()
        assert p.phase == ""
        assert p.plan == {}
        assert p.accounting_profile == {}
