import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def get_binance_price(symbol: str) -> Optional[float]:
    """Get current price from Binance API"""
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        return float(data['price'])
    except Exception as e:
        logger.error(f"Error fetching price from Binance for {symbol}: {e}")
        return None
