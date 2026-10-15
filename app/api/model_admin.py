from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.supabase_auth import require_admin
from app.models import PredictionModelConfig, PredictionRun

router = APIRouter(prefix='/model', tags=['model-admin'])

class ModelConfigIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=50)
    recency_weight: float = Field(ge=0, le=1)
    trend_weight: float = Field(ge=0, le=1)
    frequency_weight: float = Field(ge=0, le=1)
    graph_weight: float = Field(ge=0, le=1)
    active: bool = False

def out(c):
    return {'id':c.id,'name':c.name,'version':c.version,'recency_weight':float(c.recency_weight),'trend_weight':float(c.trend_weight),'frequency_weight':float(c.frequency_weight),'graph_weight':float(c.graph_weight),'active':c.active}

@router.get('/configs')
def configs(db: Session=Depends(get_db), _admin=Depends(require_admin)):
    return [out(c) for c in db.query(PredictionModelConfig).order_by(PredictionModelConfig.created_at.desc()).all()]

@router.post('/configs')
def create_config(payload: ModelConfigIn, db: Session=Depends(get_db), _admin=Depends(require_admin)):
    total=payload.recency_weight+payload.trend_weight+payload.frequency_weight+payload.graph_weight
    if abs(total-1)>0.001: raise HTTPException(400,'Os quatro pesos devem somar 1.00')
    if db.query(PredictionModelConfig).filter_by(name=payload.name,version=payload.version).first(): raise HTTPException(409,'Configuração já existe')
    if payload.active: db.query(PredictionModelConfig).update({PredictionModelConfig.active:False},synchronize_session=False)
    c=PredictionModelConfig(**payload.model_dump()); db.add(c); db.commit(); db.refresh(c); return out(c)

@router.post('/configs/{config_id}/activate')
def activate(config_id:int, db:Session=Depends(get_db), _admin=Depends(require_admin)):
    c=db.query(PredictionModelConfig).filter_by(id=config_id).first()
    if not c: raise HTTPException(404,'Configuração não encontrada')
    db.query(PredictionModelConfig).update({PredictionModelConfig.active:False},synchronize_session=False); c.active=True; db.commit(); return out(c)

@router.get('/runs')
def runs(limit:int=20, db:Session=Depends(get_db), _admin=Depends(require_admin)):
    rows=db.query(PredictionRun).order_by(PredictionRun.started_at.desc()).limit(min(limit,100)).all()
    return [{'id':r.id,'program_id':r.program_id,'model_config_id':r.model_config_id,'status':r.status,'question_count':r.question_count,'topic_count':r.topic_count,'model_version':r.model_version,'started_at':r.started_at.isoformat() if r.started_at else None,'completed_at':r.completed_at.isoformat() if r.completed_at else None,'error_message':r.error_message} for r in rows]
