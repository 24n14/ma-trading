import talib
import numpy as np
import config


def calculate_macd(closes, fast=config.MACD_FAST, slow=config.MACD_SLOW,
                   signal_period=config.MACD_SIGNAL):
    """
    Расчёт MACD
    :param closes: список или массив цен закрытия
    :param fast: быстрый период (по умолчанию из config)
    :param slow: медленный период
    :param signal_period: период сигнальной линии
    :return: словарь с MACD результатами
    """

    # ✅ Конвертируем в numpy массив
    closes = np.array(closes, dtype=np.float64)

    # ✅ Проверка данных
    if len(closes) < slow:
        return None

    # Расчёт MACD
    macd_line, signal_line, histogram = talib.MACD(
        closes,
        fastperiod=fast,
        slowperiod=slow,
        signalperiod=signal_period
    )

    # Получаем последние значения
    last_macd = macd_line[-1]
    last_signal = signal_line[-1]
    last_histogram = histogram[-1]

    # ✅ Определение сигнала (отдельный ключ!)
    if np.isnan(last_macd) or np.isnan(last_signal):
        macd_signal = 'Neutral'
    elif last_macd > last_signal:
        macd_signal = 'Buy'
    elif last_macd < last_signal:
        macd_signal = 'Sell'
    else:
        macd_signal = 'Neutral'

    # ✅ Возвращаем один словарь с разными ключами
    return {
        'macd': float(last_macd),
        'signal_line': float(last_signal),  # ← переименовал для ясности
        'histogram': float(last_histogram),
        'signal': macd_signal  # ← сигнал BUY/SELL
    }
