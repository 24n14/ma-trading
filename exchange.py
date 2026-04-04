import logging
import ccxt
import talib
import numpy as np
import pandas as pd
import time
import config
import requests
import asyncio
from info_in_telegram import TelegramNotifier
from open_position import open_position
from ma import check_ma_signal
from tp_sl import check_tp_sl
from macd import calculate_macd
from checking_signals import check_combined_signal_advanced
from wait_for_candle_close import wait_for_candle_close, get_timeframe_seconds
# Настройка логирования
log_filename = "bot_history.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot_history.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 2. ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================
global active_position
symbol = config.SYMBOL
timeframe = config.TIMEFRAME
limit = config.LIMIT
ma_period = config.MA_PERIOD
AMOUNT = config.ORDER_AMOUNT

TP_PERCENT = config.TAKE_PROFIT  # 2% Take Profit
SL_PERCENT = config.STOP_LOSS  # 1% Stop Loss

# Переменные для отслеживания позиции
active_position = {
    'is_open': False,
    'side': None,
    'entry_price': 0,
    'tp_price': 0,
    'sl_price': 0,
    'order_id': None,
    'quantity': 0
}

# 3. КОНФИГУРАЦИЯ ПРОКСИ
# ============================================
loop = asyncio.new_event_loop()  # Потом везде использовать: loop.run_until_complete(notifier.send_message(msg)) вместо asyncio.run(notifier.send_message(msg))
asyncio.set_event_loop(loop)
proxy_settings = {
    'host': config.PROXY_HOST,
    'port': config.PROXY_PORT,
    'user': config.PROXY_USER,
    'password': config.PROXY_PASS
}
notifier = TelegramNotifier(config.TG_TOKEN,
    config.TG_CHAT_ID,
    proxy_data=proxy_settings if config.USE_PROXY else None)
proxy_url = (
    f"http://{config.PROXY_USER}:{config.PROXY_PASS}@"
    f"{config.PROXY_HOST}:{config.PROXY_PORT}"
)

proxies = {
    'http': proxy_url,
    'https': proxy_url
}

# 2. Проверяем IP (безопасно)
test_ip = "Unknown"
try:
    test_ip = requests.get('https://api.ipify.org', proxies=proxies, timeout=10).text
    logger.info(f"Внешний IP через прокси: {test_ip}")
    msg = f"Работаем через прокси {test_ip}"
    loop.run_until_complete(notifier.send_message(msg))
except Exception as e:
    logger.error(f"Не удалось проверить IP через прокси: {e}")

# 4. ИНИЦИАЛИЗАЦИЯ БИРЖИ
# ============================================

try:
    exchange = ccxt.bybit({
        'apiKey': config.API_KEY,
        'secret': config.SECRET_KEY,
        'proxies': proxies,
        'options': {
            'enableDemoTrading': True,
            'defaultType': 'linear',
            'adjustForTimeDifference': True,
            'recvWindow': 10000
            }
    })
    # 2. Назначаем прокси напрямую объекту
    if config.USE_PROXY:
        exchange.proxies = proxies
        logger.info("Прокси успешно внедрены в объект exchange.")
    # Переключаем на демо-сервера
    exchange.urls['api'] = exchange.urls['demotrading']
    balance = exchange.fetch_balance()
    usdt_balance = balance['total'].get('USDT', 0)
    # ===== ДОБАВЛЯЕМ УСТАНОВКУ ПЛЕЧА =====
    try:
        # Устанавливаем плечо для монеты (на Bybit это обязательный шаг)
        exchange.set_leverage(config.LEVERAGE, config.SYMBOL)
        logger.info(f"✅ Плечо {config.LEVERAGE}x успешно установлено для {config.SYMBOL}")
    except Exception as e:
        # Если плечо уже 10, Bybit выдаст ошибку "leverage not modified" — это нормально
        logger.warning(f"⚠️ Установка плеча: {e}")
    # =====================================
    logger.info(f"✅ АВТОРИЗАЦИЯ УСПЕШНА! Баланс: {usdt_balance} USDT")
    logger.info(f"Работа через прокси: {'ВКЛЮЧЕНА' if config.USE_PROXY else 'ВЫКЛЮЧЕНА'}")
    msg = f"АВТОРИЗАЦИЯ УСПЕШНА! Баланс {usdt_balance} USDT"
    loop.run_until_complete(notifier.send_message(msg))
except Exception as e:
    logger.error(f"❌ Критическая ошибка при подключении к бирже: {e}")
    msg = f"❌ Критическая ошибка при подключении к бирже: {e}"
    loop.run_until_complete(notifier.send_message(msg))
    exit()

try:
    logger.info("Бот запущен и начинает работу...")

    # Загружаем рынки
    markets = exchange.load_markets()
    market = exchange.market(symbol)
    min_amount = market['limits']['amount']['min']
    logger.info(f"Минимальный лот для {symbol}: {min_amount}")

    if AMOUNT < min_amount:
        logger.error(f"ВНИМАНИЕ: Твой лот {AMOUNT} меньше минимального {min_amount}!")
        AMOUNT = min_amount

except Exception as e:
    logger.error(f"Ошибка при инициализации: {e}")
    exit()


# 5. АНАЛИЗ ЦЕНЫ
# ============================================

def analyze_price(candles, ma_period):
    """Анализ тренда с использованием скользящей средней"""
    df = pd.DataFrame(
        candles,
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['ma'] = talib.SMA(df['close'], timeperiod=ma_period)

    df['trend'] = 'Neutral'
    df.loc[df['close'] > df['ma'], 'trend'] = 'Up'
    df.loc[df['close'] < df['ma'], 'trend'] = 'Down'

    last_row = df.iloc[-1]

    return {
        'price': last_row['close'],
        'ma': last_row['ma'],
        'trend': last_row['trend'],
        'ma_str': f"{last_row['ma']:.2f}"
    }

# 7. ГЛАВНЫЙ ТОРГОВЫЙ ЦИКЛ
# ============================================
last_trend = None

try:
    # ⏳ ЖДЕМ ЗАКРЫТИЯ СВЕЧИ ПЕРЕД СТАРТОМ БОТА
    logger.info("⏳ Синхронизируемся с биржей... ожидаем закрытия текущей свечи")
    wait_for_candle_close(exchange, symbol, timeframe)
    logger.info("✅ Синхронизация завершена! Начинаем торговлю")
    while True:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

            if candles is None:
                continue

            # Преобразование в массив цен (ОДИН РАЗ)
            closes = np.array([candle[4] for candle in candles], dtype=np.float64)
            price = closes[-1]

            # ✅ MA сигнал
            ma_signal = check_ma_signal(candles, ma_period)
            logger.info(f"🔵 MA SIGNAL: {ma_signal}")

            # ✅ MACD сигнал (ОДИН РАЗ)
            macd_result = calculate_macd(closes)
            if macd_result:
                logger.info(f"🟣 MACD: {macd_result['macd']:.2f} | "
                            f"Signal Line: {macd_result['signal_line']:.2f} | "
                            f"Histogram: {macd_result['histogram']:.2f} | "
                            f"MACD Signal: {macd_result['signal']}")
            else:
                logger.info("🟣 MACD: Недостаточно данных")
                macd_result = None

            # ✅ Комбинированный сигнал (ПРАВИЛЬНЫЕ ПАРАМЕТРЫ)
            if ma_signal and macd_result:
                combined_signal = check_combined_signal_advanced(ma_signal, macd_result)
                logger.info(f"🟢 COMBINED SIGNAL: {combined_signal}")
            else:
                logger.warning("⚠️ Не удалось получить оба сигнала")
                combined_signal = 'HOLD'

            # 🔥 ПРОВЕРЯЕМ TP/SL
            if active_position['is_open']:
                active_position = check_tp_sl(
                    exchange, symbol, active_position, price, notifier
                )

            # ЛОГИКА ВХОДА
            if combined_signal == 'BUY' and not active_position['is_open']:
                quantity = round((config.POSITION_SIZE * config.LEVERAGE) / price, 3)
                active_position = open_position(
                    symbol=symbol,
                    quantity=quantity,
                    sl_percent=config.STOP_LOSS,
                    active_position=active_position,
                    notifier=notifier,
                    loop=loop,
                    exchange=exchange,
                    side='long',
                    tp_percent=TP_PERCENT
                )

            elif combined_signal == 'SELL' and not active_position['is_open']:
                quantity = round((config.POSITION_SIZE * config.LEVERAGE) / price, 3)
                active_position = open_position(
                    symbol=symbol,
                    quantity=quantity,
                    sl_percent=config.STOP_LOSS,
                    active_position=active_position,
                    notifier=notifier,
                    loop=loop,
                    exchange=exchange,
                    side='short',
                    tp_percent=TP_PERCENT
                )

            #time.sleep(60)
            # ⏳ ЖДЕМ ЗАКРЫТИЯ СВЕЧИ ПЕРЕД СЛЕДУЮЩЕЙ ИТЕРАЦИЕЙ
            wait_for_candle_close(exchange, symbol, timeframe)

        except ccxt.NetworkError as e:
            logger.error(f"Проблема с сетью: {e}")
            time.sleep(30)
            continue

except Exception as e:
    logger.error(f"Критическая ошибка: {e}", exc_info=True)

except KeyboardInterrupt:
    logger.info("Бот остановлен")
