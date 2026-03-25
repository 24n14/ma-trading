import logging
import ccxt
import datetime
import talib  # TA-Lib для индикаторов
import pandas as pd  # Для DataFrame
import time
import config
import requests
import asyncio
from info_in_telegram import TelegramNotifier

log_filename = "bot_log.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot_history.log", encoding='utf-8'),  # Запись в файл
        logging.StreamHandler()            # Дублирование в консоль
    ]
)

logger = logging.getLogger(__name__)
#<===глобальные переменные===>
symbol = config.SYMBOL
timeframe = config.TIMEFRAME
limit = config.LIMIT
ma_period = config.MA_PERIOD
AMOUNT = config.ORDER_AMOUNT
#<====настройки прокси ====>
proxy_settings = {
    'host': config.PROXY_HOST,
    'port': config.PROXY_PORT,
    'user': config.PROXY_USER,
    'password': config.PROXY_PASS
}
notifier = TelegramNotifier(config.TG_TOKEN,
    config.TG_CHAT_ID,
    proxy_data=proxy_settings if config.USE_PROXY else None)


#<===ПОДКЛЮЧЕНИЕ К ПРОКСИ===>
# 1. Формируем URL и словарь прокси
proxy_url = f"http://{config.PROXY_USER}:{config.PROXY_PASS}@{config.PROXY_HOST}:{config.PROXY_PORT}"
proxies = {
    'http': proxy_url,
    'https': proxy_url
} if config.USE_PROXY else None

# 2. Проверяем IP (безопасно)
test_ip = "Unknown"
try:
    test_ip = requests.get('https://api.ipify.org', proxies=proxies, timeout=10).text
    logger.info(f"Внешний IP через прокси: {test_ip}")
    msg = f"Работаем через прокси {test_ip}"
    asyncio.run(notifier.send_message(msg))
except Exception as e:
    logger.error(f"Не удалось проверить IP через прокси: {e}")

# 3. Подключаем к Bybit (ОБРАТИ ВНИМАНИЕ НА ОТСТУПЫ)
try:
    exchange = ccxt.bybit({
        'apiKey': config.API_KEY,
        'secret': config.SECRET_KEY,
        'proxies': proxies,  # CCXT сам подхватит прокси отсюда
        'options': {
            'enableDemoTrading': True,
            'defaultType': 'linear',
            'adjustForTimeDifference': True,
            'recvWindow': 10000
        }
    })
    # 2. Назначаем прокси напрямую объекту (это 100% законно в CCXT)
    if config.USE_PROXY:
        exchange.proxies = proxies
        logger.info("Прокси успешно внедрены в объект exchange.")
    # Переключаем на демо-сервера
    exchange.urls['api'] = exchange.urls['demotrading']

    # Проверка баланса (Авторизация)
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
    exit()  # Если биржа не подключилась, дальше идти нельзя

# 4. После этого блока идет твой last_trend = None и цикл while True...
last_trend = None

try:
    logger.info("Бот запущен и начинает работу...")

    # Загружаем рынки, чтобы бот знал правила торговли
    markets = exchange.load_markets()
    market = exchange.market(symbol)
    min_amount = market['limits']['amount']['min']
    logger.info(f"Минимальный лот для {symbol}: {min_amount}")

    # Теперь мы можем проверить наш AMOUNT
    if AMOUNT < min_amount:
        logger.error(f"ВНИМАНИЕ: Твой лот {AMOUNT} меньше минимального {min_amount}!")
        AMOUNT = min_amount  # Исправляем на ходу

    while True:
        # 1. Инициализация (Значения по умолчанию)
        ma_val = "N/A"
        price = 0.0
        current_trend = "Neutral"
        try:
            # Динамический since: начало сегодняшнего дня в UTC
            now = datetime.datetime.now(datetime.UTC)  # Текущее время в UTC
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            since_timestamp = int(start_of_day.timestamp() * 1000)  # В миллисек для ccxt Исторический период свечей===>

            try:
                logger.info(f"Запрос данных для {symbol} на таймфрейме {timeframe} ...")
                candles = exchange.fetch_ohlcv(symbol,  timeframe, limit=limit) #since=since_timestamp)  # Загрузка свечей (теперь с since!)===>
                logger.info(f"Получено {len(candles)} свечей за сегодня")
            except ccxt.NetworkError as e:
                logger.error(f"Проблема с сетью: {e}. Ждем 30 сек...")
                msg = f"Проблема с сетью: {e}. Ждем 30 сек..."
                asyncio.run(notifier.send_message(msg))
                time.sleep(30)
                continue  # Пробуем заново

            # Преобразуем в DataFrame для удобства
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')  # Конвертация в читаемую дату
            # Расчёт SMA через TA-Lib (быстрее и точнее, чем ручной цикл)
            df['ma'] = talib.SMA(df['close'], timeperiod=ma_period)
            # Определение тренда (простой пример: если close > ma — up, иначе down)
            df['trend'] = 'Neutral'
            df.loc[df['close'] > df['ma'], 'trend'] = 'Up'
            df.loc[df['close'] < df['ma'], 'trend'] = 'Down'

            # Берем последнюю строку для анализа
            last_row = df.iloc[-1]
            current_trend = last_row['trend']
            price = last_row['close']
            ma_val = f"{last_row['ma']:.2f}" if not pd.isna(last_row['ma']) else 'NaN'
            if not pd.isna(last_row['ma']):
                if current_trend == 'Up' and last_trend != 'Up':
                    logger.warning(f"СИГНАЛ НА ПОКУПКУ: Цена {price:.2f} выше MA: {ma_val} Тренд: {current_trend}")
                    msg = f"СИГНАЛ НА ПОКУПКУ: Цена {price:.2f} выше MA: {ma_val} Тренд: {current_trend}"
                    asyncio.run(notifier.send_message(msg))
                    try:
                        # Рыночный ордер на покупку (Market Buy)
                        order = exchange.create_market_buy_order(symbol, AMOUNT)
                        order_id = order['id']
                        # Даем бирже 0.5 секунды на обработку и запрашиваем статус заново
                        time.sleep(0.5)
                        order_id = order.get('id', 'N/A')
                        logger.info(f"Ордер отправлен успешно! ID: {order_id}")
                        msg = f"Ордер отправлен успешно!"
                        asyncio.run(notifier.send_message(msg))
                        time.sleep(1)  # Даем бирже секунду обновить баланс
                        new_balance = exchange.fetch_balance()['total'].get('USDT', 0)
                        logger.info(f"💰 Сделка совершена. Новый баланс: {new_balance:.2f} USDT")
                        msg = f"💰 Сделка совершена. Новый баланс: {new_balance:.2f} USDT"
                        asyncio.run(notifier.send_message(msg))
                    except Exception as e:
                        logger.error(f"Не удалось купить: {e}")
                        msg = f"Не удалось купить: {e}"
                        asyncio.run(notifier.send_message(msg))
                elif current_trend == 'Down' and last_trend != 'Down':
                    logger.warning(f"СИГНАЛ НА ПРОДАЖУ: Цена {price:.2f} ниже MA: {ma_val} Тренд: {current_trend}")
                    msg = f"СИГНАЛ НА ПРОДАЖУ: Цена {price:.2f} ниже MA: {ma_val} Тренд: {current_trend}"
                    asyncio.run(notifier.send_message(msg))
                    try:
                        # Рыночный ордер на продажу (Market Sell)
                        order = exchange.create_market_sell_order(symbol, AMOUNT)
                        order_id = order['id']
                        # Даем бирже 0.5 секунды на обработку и запрашиваем статус заново
                        time.sleep(0.5)
                        order_id = order.get('id', 'N/A')
                        logger.info(f"Ордер отправлен успешно! ID: {order_id}")
                        msg = f"Ордер отправлен успешно!"
                        asyncio.run(notifier.send_message(msg))
                        time.sleep(1)  # Даем бирже секунду обновить баланс
                        new_balance = exchange.fetch_balance()['total'].get('USDT', 0)
                        logger.info(f"💰 Сделка совершена. Новый баланс: {new_balance:.2f} USDT")
                        msg = f"💰 Сделка совершена. Новый баланс: {new_balance:.2f} USDT"
                        asyncio.run(notifier.send_message(msg))
                    except Exception as e:
                        logger.error(f"Не удалось продать: {e}")
                        msg = f"Не удалось продать: {e}"
                        asyncio.run(notifier.send_message(msg))

                last_trend = current_trend  # Запоминаем текущий тренд для следующего круга
                # 5. Краткий вывод в консоль
                logger.info(f"Цена: {price:.2f} | MA: {ma_val} | Тренд: {current_trend}")
                # Пауза
                time.sleep(60)

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
            msg = f"Критическая ошибка: {e}"
            asyncio.run(notifier.send_message(msg))
            time.sleep(10)

except KeyboardInterrupt:
    # ЭТОТ БЛОК СРАБОТАЕТ ПРИ НАЖАТИИ НА STOP
    print("\n") # Просто пустая строка для красоты в консоли
    logger.info("Прощай, хозяин! Я ухожу на покой, все ордера под контролем.")
    msg = f"Прощай, хозяин! Я ухожу на покой, все ордера под контролем."
    asyncio.run(notifier.send_message(msg))
    # Здесь можно добавить логику закрытия соединений, если нужно