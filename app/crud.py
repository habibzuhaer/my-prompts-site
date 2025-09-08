from sqlalchemy.orm import Session
import uuid
from app import models, schemas
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(
        email=user.email, 
        hashed_password=hashed_password,
        id=uuid.uuid4()
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_strategies_by_user(db: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100):
    return db.query(models.Strategy).filter(
        models.Strategy.user_id == user_id
    ).offset(skip).limit(limit).all()

def get_strategy_by_id(db: Session, strategy_id: uuid.UUID):
    return db.query(models.Strategy).filter(models.Strategy.id == strategy_id).first()

def create_user_strategy(db: Session, strategy: schemas.StrategyCreate, user_id: uuid.UUID):
    db_strategy = models.Strategy(
        **strategy.dict(),
        user_id=user_id,
        id=uuid.uuid4()
    )
    db.add(db_strategy)
    db.commit()
    db.refresh(db_strategy)
    return db_strategy

def update_strategy(db: Session, db_strategy: models.Strategy, strategy_update: schemas.StrategyCreate):
    for field, value in strategy_update.dict().items():
        setattr(db_strategy, field, value)
    db.commit()
    db.refresh(db_strategy)
    return db_strategy

def delete_strategy(db: Session, strategy_id: uuid.UUID):
    db_strategy = db.query(models.Strategy).filter(models.Strategy.id == strategy_id).first()
    if db_strategy:
        db.delete(db_strategy)
        db.commit()
    return db_strategy

def toggle_strategy(db: Session, strategy_id: uuid.UUID):
    db_strategy = db.query(models.Strategy).filter(models.Strategy.id == strategy_id).first()
    if db_strategy:
        db_strategy.is_active = not db_strategy.is_active
        db.commit()
        db.refresh(db_strategy)
    return db_strategy

def create_alert(db: Session, message: str, trigger_value: float, strategy_id: uuid.UUID, user_id: uuid.UUID):
    db_alert = models.Alert(
        message=message,
        trigger_value=trigger_value,
        strategy_id=strategy_id,
        user_id=user_id,
        id=uuid.uuid4()
    )
    db.add(db_alert)
    db.commit()
    db.refresh(db_alert)
    return db_alert

def get_alerts_by_user(db: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 100):
    return db.query(models.Alert).filter(
        models.Alert.user_id == user_id
    ).order_by(models.Alert.created_at.desc()).offset(skip).limit(limit).all()

def update_user_telegram_chat_id(db: Session, user_id: uuid.UUID, chat_id: str):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user:
        db_user.telegram_chat_id = chat_id
        db.commit()
        db.refresh(db_user)
    return db_user