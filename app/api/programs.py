from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.supabase_auth import require_admin
from app.models import Institution, Program, ProgramWeight

router = APIRouter(prefix="/programs", tags=["programs"])


class WeightIn(BaseModel):
    knowledge_area_id: int
    weight: float = Field(gt=0)
    source_year: int | None = None


@router.get("")
def list_programs(db: Session = Depends(get_db)):
    programs = db.query(Program).options(joinedload(Program.institution), joinedload(Program.weights)).all()
    return programs


@router.get("/{program_id}")
def get_program(program_id: int, db: Session = Depends(get_db)):
    program = db.query(Program).options(joinedload(Program.institution), joinedload(Program.weights)).filter(Program.id == program_id).first()
    if not program:
        raise HTTPException(status_code=404, detail="Curso não encontrado")
    return program


@router.post("")
def create_program(institution_name: str, program_name: str, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    institution = db.query(Institution).filter_by(name=institution_name).first()
    if not institution:
        institution = Institution(name=institution_name)
        db.add(institution)
        db.flush()
    existing = db.query(Program).filter_by(institution_id=institution.id, name=program_name).first()
    if existing:
        return existing
    program = Program(institution_id=institution.id, name=program_name)
    db.add(program)
    db.commit()
    db.refresh(program)
    return program


@router.post("/{program_id}/weights")
def set_program_weight(program_id: int, weight: WeightIn, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    if not db.query(Program).filter(Program.id == program_id).first():
        raise HTTPException(status_code=404, detail="Curso não encontrado")
    entry = db.query(ProgramWeight).filter_by(
        program_id=program_id,
        knowledge_area_id=weight.knowledge_area_id,
        source_year=weight.source_year,
    ).first()
    if entry:
        entry.weight = weight.weight
    else:
        entry = ProgramWeight(program_id=program_id, **weight.model_dump())
        db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
