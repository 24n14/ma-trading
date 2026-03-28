import logging
import numpy as np
import config
from macd import calculate_macd
from ma import check_ma_signal

logger = logging.getLogger(__name__)


def check_combined_signal_advanced(ma_signal, macd_result):
    """
    Комбинированный сигнал: MA + MACD
    :param ma_signal: словарь {'signal': 'BUY'/'SELL', 'ma': X, 'price': Y, 'trend': 'UP'/'DOWN'}
    :param macd_result: словарь {'signal': 'BUY'/'SELL', 'macd': X, 'signal_line': Y, 'histogram': Z}
    :return: 'BUY', 'SELL', или 'HOLD'
    """

    if not ma_signal or not macd_result:
        logger.warning("⚠️ Недостаточно данных для комбинированного анализа")
        return 'HOLD'

    try:
        ma_sig = ma_signal.get('signal')
        macd_sig = macd_result.get('signal')

        # ✅ ОБА СОГЛАСНЫ НА BUY
        if ma_sig == 'BUY' and macd_sig == 'Buy':
            logger.info("✅ MA и MACD СОГЛАСНЫ: BUY")
            return 'BUY'

        # ✅ ОБА СОГЛАСНЫ НА SELL
        if ma_sig == 'SELL' and macd_sig == 'Sell':
            logger.info("✅ MA и MACD СОГЛАСНЫ: SELL")
            return 'SELL'

        # ⚠️ ПРОТИВОРЕЧИЕ
        logger.warning(f"⚠️ MA: {ma_sig} vs MACD: {macd_sig} → HOLD")
        return 'HOLD'

    except Exception as e:
        logger.error(f"❌ Ошибка в check_combined_signal_advanced: {e}")
        return 'HOLD'

