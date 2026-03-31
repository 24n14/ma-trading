import logging

import close_position

logger = logging.getLogger(__name__)
# 6. ФУНКЦИИ ДЛЯ РАБОТЫ С TP/SL
# ============================================
def check_tp_sl(exchange, symbol, active_position, current_price, notifier):
    """Проверка достижения TP или SL"""
    if not active_position['is_open']:
        return active_position

    tp_price = active_position['tp_price']
    sl_price = active_position['sl_price']
    side = active_position['side']
    entry_price = active_position['entry_price']

    # Проверка Take Profit для LONG
    if side == 'long' and current_price >= tp_price:
        active_position = close_position.close_position(
            exchange, symbol, 'long', current_price, 'TP ✅', active_position, notifier
        )
        # Уведомление
        if notifier:
            notifier.send(f"✅ TP достигнут на {symbol}!")
        return active_position

    # Проверка Stop Loss для LONG
    if side == 'long' and current_price <= sl_price:
        active_position = close_position.close_position(
            exchange, symbol, 'long', current_price, 'SL ❌', active_position, notifier
        )
        # Уведомление
        if notifier:
            notifier.send(f"❌ SL сработал на {symbol}!")
        return active_position

    # Проверка Take Profit для SHORT
    if side == 'short' and current_price <= tp_price:
        active_position = close_position.close_position(
            exchange, symbol, 'short', current_price, 'TP ✅', active_position, notifier
        )
        # Уведомление
        if notifier:
            notifier.send(f"✅ TP достигнут на {symbol}!")
        return active_position

    # Проверка Stop Loss для SHORT
    if side == 'short' and current_price >= sl_price:
        active_position = close_position.close_position(
            exchange, symbol, 'short', current_price, 'SL ❌', active_position, notifier
        )
        # Уведомление
        if notifier:
            notifier.send(f"❌ SL сработал на {symbol}!")
        return active_position

    # Логирование текущего статуса
    profit_loss = ((current_price - entry_price) / entry_price) * 100 if side == 'long' else ((entry_price - current_price) / entry_price) * 100
    logger.info(
        f"📊 ПОЗИЦИЯ В РАБОТЕ ({side.upper()})\n"
        f"Текущая цена: {current_price:.2f}\n"
        f"TP: {tp_price:.2f} | SL: {sl_price:.2f}\n"
        f"P/L: {profit_loss:+.2f}%"
    )
    return active_position
