import logging
import datetime
import time

logger = logging.getLogger(__name__)


def get_timeframe_seconds(tf):
    """Конвертирует таймфрейм в секунды"""
    mapping = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '30m': 1800,
        '1h': 3600,
        '4h': 14400,
        '1d': 86400
    }
    return mapping.get(tf, 300)


def wait_for_candle_close(exchange, symbol, timeframe):
    """Получает время закрытия свечи от биржи и ждет"""
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Получаем последнюю свечу
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=1)

            # ohlcv[0][0] — timestamp открытия свечи (в миллисекундах)
            candle_open_time = ohlcv[0][0] / 1000  # переводим в секунды
            timeframe_sec = get_timeframe_seconds(timeframe)
            candle_close_time = candle_open_time + timeframe_sec

            now_sec = datetime.datetime.now().timestamp()
            wait_time = candle_close_time - now_sec

            if wait_time > 0:
                logger.info(f"⏳ Ожидание {wait_time:.1f} сек до закрытия свечи {timeframe}")
                time.sleep(wait_time + 0.5)  # +0.5 сек подстраховки
                return True
            else:
                # Свеча уже закрыта, выходим
                logger.info(f"✅ Свеча {timeframe} уже закрыта")
                return True

        except Exception as e:
            retry_count += 1
            logger.error(f"❌ Ошибка получения времени свечи (попытка {retry_count}/{max_retries}): {e}")

            if retry_count < max_retries:
                time.sleep(2)
            else:
                logger.error(f"❌ Не удалось получить данные после {max_retries} попыток")
                return False
