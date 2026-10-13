"""Project and scenario routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user, paginate
from ..models import Project, Scenario, ScenarioVersion, User
from ..schemas import ProjectIn, ProjectOut, ScenarioIn, ScenarioOut, ScenarioVersionOut

router = APIRouter(prefix="/api", tags=["projects", "scenarios"])


def _owned_project(db: Session, user: User, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if not p or p.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project not found")
    return p


# ---------- projects ----------

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc())).all()


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(owner_id=user.id, name=body.name, description=body.description)
    db.add(p)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="project name already exists")
    db.refresh(p)
    return p


# ---------- scenarios ----------

def _scenario_visible(db: Session, user: User, scenario_id: int) -> Scenario:
    s = db.get(Scenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="scenario not found")
    if s.is_template:
        return s
    project = db.get(Project, s.project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="scenario not found")
    return s


def _with_latest(db: Session, s: Scenario) -> ScenarioOut:
    latest = db.scalar(
        select(ScenarioVersion).where(ScenarioVersion.scenario_id == s.id)
        .order_by(ScenarioVersion.version.desc()).limit(1)
    )
    out = ScenarioOut.model_validate(s)
    out.latest_version = ScenarioVersionOut.model_validate(latest) if latest else None
    return out


@router.get("/scenarios")
def list_scenarios(
    q: str = "", category: str = "", page: int = 1, page_size: int = 20,
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    page, page_size = paginate(page, page_size)
    project_ids = select(Project.id).where(Project.owner_id == user.id)
    cond = (Scenario.is_template.is_(True)) | (Scenario.project_id.in_(project_ids))
    stmt = select(Scenario).where(cond)
    count_stmt = select(func.count(Scenario.id)).where(cond)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Scenario.name.ilike(like) | Scenario.description.ilike(like))
        count_stmt = count_stmt.where(Scenario.name.ilike(like) | Scenario.description.ilike(like))
    if category:
        stmt = stmt.where(Scenario.category == category)
        count_stmt = count_stmt.where(Scenario.category == category)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Scenario.is_template.desc(), Scenario.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_with_latest(db, s) for s in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/scenarios", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
def create_scenario(body: ScenarioIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project_id = None
    if body.project_id is not None:
        project_id = _owned_project(db, user, body.project_id).id
    else:
        project = db.scalar(select(Project).where(Project.owner_id == user.id).order_by(Project.id))
        if project is None:
            project = Project(owner_id=user.id, name="Default Project", description="Auto-created on first scenario")
            db.add(project)
            db.flush()
        project_id = project.id
    s = Scenario(project_id=project_id, is_template=False, key=body.key, name=body.name,
                 category=body.category, description=body.description)
    db.add(s)
    db.flush()
    v = ScenarioVersion(scenario_id=s.id, version=1, definition=body.definition.model_dump(),
                        change_note=body.change_note or "initial version")
    db.add(v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="scenario key already exists in this project")
    return _with_latest(db, s)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _with_latest(db, _scenario_visible(db, user, scenario_id))


@router.post("/scenarios/{scenario_id}/versions", response_model=ScenarioVersionOut, status_code=status.HTTP_201_CREATED)
def create_scenario_version(scenario_id: int, body: ScenarioIn,
                            user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _scenario_visible(db, user, scenario_id)
    if s.is_template:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="library templates are read-only; clone instead")
    next_version = (db.scalar(select(func.max(ScenarioVersion.version))
                              .where(ScenarioVersion.scenario_id == s.id)) or 0) + 1
    v = ScenarioVersion(scenario_id=s.id, version=next_version,
                        definition=body.definition.model_dump(),
                        change_note=body.change_note or f"version {next_version}")
    db.add(v)
    s.name = body.name
    s.description = body.description
    s.category = body.category
    db.commit()
    db.refresh(v)
    return v


@router.post("/scenarios/{scenario_id}/clone", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED)
def clone_scenario(scenario_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    src = _scenario_visible(db, user, scenario_id)
    latest = db.scalar(select(ScenarioVersion).where(ScenarioVersion.scenario_id == src.id)
                       .order_by(ScenarioVersion.version.desc()).limit(1))
    project = db.scalar(select(Project).where(Project.owner_id == user.id).order_by(Project.id))
    if project is None:
        project = Project(owner_id=user.id, name="Default Project", description="Auto-created")
        db.add(project)
        db.flush()
    key = f"{src.key}_copy"
    n = 1
    base = key
    while db.scalar(select(Scenario).where(Scenario.project_id == project.id, Scenario.key == key)):
        n += 1
        key = f"{base}{n}"
    s = Scenario(project_id=project.id, is_template=False, key=key, name=f"{src.name} (copy)",
                 category=src.category, description=src.description)
    db.add(s)
    db.flush()
    db.add(ScenarioVersion(scenario_id=s.id, version=1, definition=latest.definition,
                           change_note=f"cloned from {src.key} v{latest.version}"))
    db.commit()
    return _with_latest(db, s)
