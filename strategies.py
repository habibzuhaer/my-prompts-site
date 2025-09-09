from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app import crud, schemas, dependencies
from app.database import get_db

router = APIRouter(prefix="/strategies", tags=["strategies"])

@router.get("/", response_model=List[schemas.Strategy])
def read_strategies(
    skip: int = 0, 
    limit: int = 100, 
    current_user: schemas.User = Depends(dependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    strategies = crud.get_strategies_by_user(db, user_id=current_user.id, skip=skip, limit=limit)
    return strategies

@router.post("/", response_model=schemas.Strategy)
def create_strategy(
    strategy: schemas.StrategyCreate,
    current_user: schemas.User = Depends(dependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    return crud.create_user_strategy(db=db, strategy=strategy, user_id=current_user.id)

@router.get("/{strategy_id}", response_model=schemas.Strategy)
def read_strategy(
    strategy_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    strategy = crud.get_strategy_by_id(db, strategy_id=strategy_id)
    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy

@router.put("/{strategy_id}", response_model=schemas.Strategy)
def update_strategy(
    strategy_id: str,
    strategy: schemas.StrategyCreate,
    current_user: schemas.User = Depends(dependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    db_strategy = crud.get_strategy_by_id(db, strategy_id=strategy_id)
    if not db_strategy or db_strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    return crud.update_strategy(db=db, db_strategy=db_strategy, strategy_update=strategy)

@router.delete("/{strategy_id}")
def delete_strategy(
    strategy_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    strategy = crud.get_strategy_by_id(db, strategy_id=strategy_id)
    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    crud.delete_strategy(db, strategy_id=strategy_id)
    return {"message": "Strategy deleted successfully"}

@router.post("/{strategy_id}/toggle", response_model=schemas.Strategy)
def toggle_strategy(
    strategy_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    strategy = crud.get_strategy_by_id(db, strategy_id=strategy_id)
    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    
    return crud.toggle_strategy(db, strategy_id=strategy_id)
