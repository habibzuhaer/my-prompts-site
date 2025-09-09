from celery import Celery
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import crud, models
from app.services import binance_service, telegram_service
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create Celery instance
celery = Celery(__name__)
celery.conf.broker_url = "redis://localhost:6379/0"
celery.conf.result_backend = "redis://localhost:6379/0"

@celery.task(name="check_strategies")
def check_strategies():
    """Check all active strategies for conditions"""
    db: Session = SessionLocal()
    try:
        active_strategies = db.query(models.Strategy).filter(
            models.Strategy.is_active == True
        ).all()
        
        for strategy in active_strategies:
            # Check if it's time to check this strategy
            if strategy.last_checked and (
                (datetime.utcnow() - strategy.last_checked).total_seconds() < strategy.check_interval
            ):
                continue
                
            # Get current price
            price = binance_service.get_binance_price(strategy.symbol)
            if price is None:
                continue
                
            # Check condition
            condition_met = False
            if strategy.condition_type == "price_above" and price > strategy.condition_value:
                condition_met = True
            elif strategy.condition_type == "price_below" and price < strategy.condition_value:
                condition_met = True
                
            if condition_met:
                # Create alert
                message = f"🚨 Alert: {strategy.symbol} {strategy.condition_type.replace('_', ' ')} {strategy.condition_value}. Current price: {price}"
                alert = crud.create_alert(
                    db, 
                    message=message, 
                    trigger_value=price, 
                    strategy_id=strategy.id,
                    user_id=strategy.user_id
                )
                
                # Send notifications
                user = db.query(models.User).filter(models.User.id == strategy.user_id).first()
                if user and "telegram" in strategy.notification_type and user.telegram_chat_id:
                    telegram_service.send_telegram_message(user.telegram_chat_id, message)
                    
                # TODO: Send WebSocket notification for web clients
                
            # Update last checked time
            strategy.last_checked = datetime.utcnow()
            db.commit()
            
    except Exception as e:
        logger.error(f"Error in check_strategies task: {e}")
        db.rollback()
    finally:
        db.close()

@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks"""
    # Check strategies every 30 seconds
    sender.add_periodic_task(30.0, check_strategies.s(), name='check-strategies-every-30s')
