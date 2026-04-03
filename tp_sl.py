import logging
import time
import close_position

logger = logging.getLogger(__name__)


def check_tp_sl(exchange, symbol, active_position, current_price, notifier):
    """Проверка достижения TP или SL с верификацией закрытия"""
    if not active_position['is_open']:
        return active_position

    tp_price = active_position['tp_price']
    sl_price = active_position['sl_price']
    side = active_position['side']
    entry_price = active_position['entry_price']
    position_size = active_position['size']

    # Определяем, сработал ли TP или SL
    tp_triggered = (side == 'long' and current_price >= tp_price) or \
                   (side == 'short' and current_price <= tp_price)

    sl_triggered = (side == 'long' and current_price <= sl_price) or \
                   (side == 'short' and current_price >= sl_price)

    if tp_triggered:
        active_position = _close_with_verification(
            exchange, symbol, side, current_price, 'TP ✅',
            active_position, notifier, position_size
        )
    elif sl_triggered:
        active_position = _close_with_verification(
            exchange, symbol, side, current_price, 'SL ❌',
            active_position, notifier, position_size
        )
    else:
        # Логирование статуса
        pl = ((current_price - entry_price) / entry_price) * 100 if side == 'long' \
            else ((entry_price - current_price) / entry_price) * 100
        logger.info(
            f"📊 {side.upper()} | Цена: {current_price:.2f} | TP: {tp_price:.2f} | SL: {sl_price:.2f} | P/L: {pl:+.2f}%")

    return active_position


def _close_with_verification(exchange, symbol, side, price, reason,
                             active_position, notifier, expected_size):
    """Закрытие позиции с проверкой полного исполнения"""
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Закрываем позицию
            result = close_position.close_position(
                exchange, symbol, side, price, reason, active_position, notifier
            )

            # Проверяем, что позиция действительно закрылась
            closed_size = _verify_position_closed(exchange, symbol, side)

            if closed_size >= expected_size * 0.99:  # 99% - допуск на округление
                logger.info(f"✅ Позиция {side} на {symbol} закрыта полностью ({closed_size}/{expected_size})")
                if notifier:
                    notifier.send(f"✅ {reason} на {symbol}! Закрыто {closed_size} контрактов")
                active_position['is_open'] = False
                return result

            else:
                logger.warning(f"⚠️ Позиция закрыта частично: {closed_size}/{expected_size}")
                retry_count += 1
                time.sleep(1)

        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии позиции: {e}")
            retry_count += 1
            time.sleep(1)

    logger.error(f"❌ Не удалось полностью закрыть позицию после {max_retries} попыток")
    return active_position


def _verify_position_closed(exchange, symbol, side):
    """Проверка, закрылась ли позиция на бирже"""
    try:
        # Пример для Binance (адаптируй под свою биржу)
        position = exchange.fetch_positions(symbols=[symbol])

        if not position:
            return 0

        for pos in position:
            if pos['symbol'] == symbol and pos['side'] == side:
                return float(pos['contracts']) if pos['contracts'] else 0

        return 0  # Позиция закрыта

    except Exception as e:
        logger.error(f"❌ Ошибка проверки позиции: {e}")
        return -1  # Ошибка при проверке
