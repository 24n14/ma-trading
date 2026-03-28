import talib
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def check_ma_signal(candles, ma_period=20):
    """
    Проверка MA сигнала
    :param candles: массив свечей [[timestamp, open, high, low, close, volume], ...]
    :param ma_period: период скользящей средней
    :return: словарь {'signal': 'BUY'/'SELL', 'ma': X.XX, 'price': X.XX} или None
    """

    if not candles or len(candles) < ma_period:
        logger.warning(f"Недостаточно данных для MA: {len(candles) if candles else 0} < {ma_period}")
        return None

    try:
        # ✅ Извлекаем только цены закрытия (индекс 4)
        closes = np.array([float(candle[4]) for candle in candles], dtype=np.float64)

        # ✅ Проверяем размерность
        if closes.ndim != 1:
            closes = closes.flatten()

        logger.debug(f"Массив closes shape: {closes.shape}, dtype: {closes.dtype}")

        # ✅ Вычисляем MA
        ma = talib.SMA(closes, timeperiod=ma_period)

        if ma is None or len(ma) == 0:
            logger.error("talib.SMA вернул пустой результат")
            return None

        # Последние значения
        current_price = closes[-1]
        ma_value = ma[-1]

        # ✅ Определяем сигнал
        if np.isnan(ma_value):
            logger.warning("MA значение = NaN")
            return None

        signal = 'BUY' if current_price > ma_value else 'SELL'

        logger.info(f"MA Сигнал: {signal} | Цена: {current_price:.2f} | MA({ma_period}): {ma_value:.2f}")

        return {
            'signal': signal,
            'ma': ma_value,
            'price': current_price,
            'trend': 'UP' if current_price > ma_value else 'DOWN'
        }

    except Exception as e:
        logger.error(f"Ошибка в check_ma_signal: {e}")
        return None
