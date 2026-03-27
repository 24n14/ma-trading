import os
from dotenv import load_dotenv

load_dotenv()

#  ===== НАСТРОЙКИ ПОДКЛЮЧЕНИЯ =====
API_KEY = os.getenv('API_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')
ENABLE_DEMO = True  # True для демо-счета, False для реального
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = 6210921859

#  ===== ПАРАМЕТРЫ ТОРГОВЛИ =====
SYMBOL = 'BTC/USDT:USDT'
CATEGORY = 'linear'
TIMEFRAME = '15m'
ORDER_AMOUNT = 0.01
LIMIT = 100
TP_PCT = 0.02  # 2% Тейк-профит
SL_PCT = 0.01  # 1% Стоп-лосс
in_position = False
entry_price = 0.0
#  ====ПАРАМЕТРЫ ИНДИКАТОРА====
MA_PERIOD = 5
#  =====ПАРАМЕТРЫ ПРОКСИ =====
PROXY_HOST = '154.219.207.178'
PROXY_PORT = '63690'
PROXY_USER = os.getenv('PROXY_USER')
PROXY_PASS = os.getenv('PROXY_PASS')
USE_PROXY = True
