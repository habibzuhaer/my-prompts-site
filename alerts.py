from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app import crud, schemas, dependencies
from app.database import get_db

router = APIRouter(prefix="/alerts", tags=["alerts"])

@router.get("/", response_model=List[schemas.Alert])
def read_alerts(
    skip: int = 0, 
    limit: int = 100, 
    current_user: schemas.User = Depends(dependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    alerts = crud.get_alerts_by_user(db, user_id=current_user.id, skip=skip, limit=limit)
    return alerts
