import logging
import ccxt
import datetime
import talib
import pandas as pd
import time
import config
import requests
import asyncio
from info_in_telegram import TelegramNotifier

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

symbol = config.SYMBOL
timeframe = config.TIMEFRAME
limit = config.LIMIT
ma_period = config.MA_PERIOD
AMOUNT = config.ORDER_AMOUNT

TP_PERCENT = 0.02  # 2% Take Profit
SL_PERCENT = 0.01  # 1% Stop Loss

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
    asyncio.run(notifier.send_message(msg))
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

    logger.info(f"✅ АВТОРИЗАЦИЯ УСПЕШНА! Баланс: {usdt_balance} USDT")
    logger.info(f"Работа через прокси: {'ВКЛЮЧЕНА' if config.USE_PROXY else 'ВЫКЛЮЧЕНА'}")
    msg = f"АВТОРИЗАЦИЯ УСПЕШНА! Баланс {usdt_balance} USDT"
    asyncio.run(notifier.send_message(msg))
except Exception as e:
    logger.error(f"❌ Критическая ошибка при подключении к бирже: {e}")
    msg = f"❌ Критическая ошибка при подключении к бирже: {e}"
    asyncio.run(notifier.send_message(msg))
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


# 6. ФУНКЦИИ ДЛЯ РАБОТЫ С TP/SL
# ============================================

def open_position(exchange, symbol, side, amount, current_price):
    """Открытие позиции с расчётом TP и SL"""
    try:
        if side == 'long':
            order = exchange.create_market_buy_order(symbol, amount)
            side_text = "LONG 📈"
        else:
            order = exchange.create_market_sell_order(symbol, amount)
            side_text = "SHORT 📉"

        entry_price = order.get('average') or current_price
        tp_price = entry_price * (1 + TP_PERCENT) if side == 'long' else entry_price * (1 - TP_PERCENT)
        sl_price = entry_price * (1 - SL_PERCENT) if side == 'long' else entry_price * (1 + SL_PERCENT)

        # Обновляем глобальную переменную позиции
        active_position['is_open'] = True
        active_position['side'] = side
        active_position['entry_price'] = entry_price
        active_position['tp_price'] = tp_price
        active_position['sl_price'] = sl_price
        active_position['order_id'] = order.get('id')
        active_position['quantity'] = amount

        logger.info(
            f"✅ ПОЗИЦИЯ ОТКРЫТА ({side_text})\n"
            f"Вход: {entry_price:.2f} USDT\n"
            f"TP: {tp_price:.2f} USDT (+{TP_PERCENT*100}%)\n"
            f"SL: {sl_price:.2f} USDT (-{SL_PERCENT*100}%)\n"
            f"Объём: {amount}"
        )

        msg = (
            f"✅ ПОЗИЦИЯ ОТКРЫТА ({side_text})\n"
            f"Вход: {entry_price:.2f} USDT\n"
            f"TP: {tp_price:.2f} USDT\n"
            f"SL: {sl_price:.2f} USDT"
        )
        asyncio.run(notifier.send_message(msg))

        return True

    except Exception as e:
        logger.error(f"❌ Ошибка при открытии позиции: {e}")
        msg = f"❌ Ошибка при открытии позиции: {e}"
        asyncio.run(notifier.send_message(msg))
        return False


def check_tp_sl(exchange, symbol, current_price):
    """Проверка достижения TP или SL"""
    if not active_position['is_open']:
        return

    tp_price = active_position['tp_price']
    sl_price = active_position['sl_price']
    side = active_position['side']
    entry_price = active_position['entry_price']

    # Проверка Take Profit для LONG
    if side == 'long' and current_price >= tp_price:
        close_position(exchange, symbol, 'long', current_price, 'TP ✅')
        return

    # Проверка Stop Loss для LONG
    if side == 'long' and current_price <= sl_price:
        close_position(exchange, symbol, 'long', current_price, 'SL ❌')
        return

    # Проверка Take Profit для SHORT
    if side == 'short' and current_price <= tp_price:
        close_position(exchange, symbol, 'short', current_price, 'TP ✅')
        return

    # Проверка Stop Loss для SHORT
    if side == 'short' and current_price >= sl_price:
        close_position(exchange, symbol, 'short', current_price, 'SL ❌')
        return

    # Логирование текущего статуса
    profit_loss = ((current_price - entry_price) / entry_price) * 100 if side == 'long' else ((entry_price - current_price) / entry_price) * 100
    logger.info(
        f"📊 ПОЗИЦИЯ В РАБОТЕ ({side.upper()})\n"
        f"Текущая цена: {current_price:.2f}\n"
        f"TP: {tp_price:.2f} | SL: {sl_price:.2f}\n"
        f"P/L: {profit_loss:+.2f}%"
    )


def close_position(exchange, symbol, side, current_price, reason):
    """Закрытие позиции по TP или SL"""
    try:
        entry_price = active_position['entry_price']
        quantity = active_position['quantity']

        if side == 'long':
            order = exchange.create_market_sell_order(symbol, quantity)
        else:
            order = exchange.create_market_buy_order(symbol, quantity)

        exit_price = order.get('average') or current_price
        profit_loss = (exit_price - entry_price) * quantity if side == 'long' else (entry_price - exit_price) * quantity
        profit_loss_percent = ((exit_price - entry_price) / entry_price) * 100 if side == 'long' else ((entry_price - exit_price) / entry_price) * 100

        # Закрываем позицию
        active_position['is_open'] = False

        emoji = "✅" if profit_loss > 0 else "❌"
        logger.info(
            f"{emoji} ПОЗИЦИЯ ЗАКРЫТА ({reason})\n"
            f"Вход: {entry_price:.2f}\n"
            f"Выход: {exit_price:.2f}\n"
            f"Прибыль/Убыток: {profit_loss:.2f} USDT ({profit_loss_percent:+.2f}%)"
        )

        msg = (
            f"{emoji} ПОЗИЦИЯ ЗАКРЫТА ({reason})\n"
            f"Вход: {entry_price:.2f}\n"
            f"Выход: {exit_price:.2f}\n"
            f"Прибыль/Убыток: {profit_loss:+.2f} USDT ({profit_loss_percent:+.2f}%)"
        )
        asyncio.run(notifier.send_message(msg))

        # Обновляем баланс
        time.sleep(1)
        new_balance = exchange.fetch_balance()['total'].get('USDT', 0)
        logger.info(f"💰 Новый баланс: {new_balance:.2f} USDT")
        msg = f"💰 Новый баланс: {new_balance:.2f} USDT"
        asyncio.run(notifier.send_message(msg))

    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии позиции: {e}")
        msg = f"❌ Ошибка при закрытии позиции: {e}"
        asyncio.run(notifier.send_message(msg))


# 7. ГЛАВНЫЙ ТОРГОВЫЙ ЦИКЛ
# ============================================

last_trend = None

try:
    while True:
        now = datetime.datetime.now(datetime.UTC)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        since_timestamp = int(start_of_day.timestamp() * 1000)

        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            logger.info(f"Запрос данных для {symbol} на таймфрейме {timeframe}")
            logger.info(f"Получено {len(candles)} свечей")

            if candles is None:
                continue

        except ccxt.NetworkError as e:
            logger.error(f"Проблема с сетью: {e}. Ждем 30 сек...")
            msg = f"Проблема с сетью: {e}. Ждем 30 сек..."
            asyncio.run(notifier.send_message(msg))
            time.sleep(30)
            continue

        # Преобразуем в DataFrame
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # Расчёт SMA
        df['ma'] = talib.SMA(df['close'], timeperiod=ma_period)

        # Определение тренда
        df['trend'] = 'Neutral'
        df.loc[df['close'] > df['ma'], 'trend'] = 'Up'
        df.loc[df['close'] < df['ma'], 'trend'] = 'Down'

        last_row = df.iloc[-1]
        current_trend = last_row['trend']
        price = last_row['close']
        ma_val = f"{last_row['ma']:.2f}" if not pd.isna(last_row['ma']) else 'NaN'

        # 🔥 ПРОВЕРЯЕМ TP/SL ЕСЛИ ПОЗИЦИЯ ОТКРЫТА
        if active_position['is_open']:
            check_tp_sl(exchange, symbol, price)

        # Логика входа в позицию
        if not pd.isna(last_row['ma']):
            if current_trend == 'Up' and last_trend != 'Up':
                logger.warning(f"🔔 СИГНАЛ НА ПОКУПКУ: Цена {price:.2f} > MA {ma_val}")
                msg = f"🔔 СИГНАЛ НА ПОКУПКУ: Цена {price:.2f} > MA {ma_val}"
                asyncio.run(notifier.send_message(msg))

                if not active_position['is_open']:
                    open_position(exchange, symbol, 'long', AMOUNT, price)

            elif current_trend == 'Down' and last_trend != 'Down':
                logger.warning(f"🔔 СИГНАЛ НА ПРОДАЖУ: Цена {price:.2f} < MA {ma_val}")
                msg = f"🔔 СИГНАЛ НА ПРОДАЖУ: Цена {price:.2f} < MA {ma_val}"
                asyncio.run(notifier.send_message(msg))

                if not active_position['is_open']:
                    open_position(exchange, symbol, 'short', AMOUNT, price)

            last_trend = current_trend
            logger.info(f"📊 Цена: {price:.2f} | MA: {ma_val} | Тренд: {current_trend}")

            time.sleep(60)

except Exception as e:
    logger.error(f"Критическая ошибка: {e}", exc_info=True)
    msg = f"Критическая ошибка: {e}"
    asyncio.run(notifier.send_message(msg))
    time.sleep(10)

except KeyboardInterrupt:
    print("\n")
    logger.info("Бот остановлен. Все ордера под контролем.")
    msg = f"Бот остановлен. Все ордера под контролем."
    asyncio.run(notifier.send_message(msg))
