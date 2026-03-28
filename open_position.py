import logging

logger = logging.getLogger(__name__)


def open_position(symbol, quantity, sl_percent, active_position, notifier, loop,
                  exchange=None, side='long', tp_percent=0.02):
    """Открытие позиции с расчётом TP и SL"""

    # Проверка: позиция уже открыта?
    if active_position['is_open']:
        logger.warning("⚠️ Позиция уже открыта, игнорируем сигнал")
        return active_position

    try:
        # ✅ Получаем текущую цену
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # ✅ Создаём ордер
        if side == 'long':
            order = exchange.create_market_buy_order(symbol, quantity)
            side_text = "LONG 📈"
        else:
            order = exchange.create_market_sell_order(symbol, quantity)
            side_text = "SHORT 📉"

        # ✅ Берём реальную цену входа
        entry_price = order.get('average') or current_price

        # ✅ Расчёт TP и SL
        tp_price = entry_price * (1 + tp_percent) if side == 'long' else entry_price * (1 - tp_percent)
        sl_price = entry_price * (1 - sl_percent) if side == 'long' else entry_price * (1 + sl_percent)

        # ✅ Обновляем позицию
        active_position['is_open'] = True
        active_position['side'] = side
        active_position['entry_price'] = entry_price
        active_position['tp_price'] = tp_price
        active_position['sl_price'] = sl_price
        active_position['order_id'] = order.get('id')
        active_position['quantity'] = quantity

        logger.info(
            f"✅ ПОЗИЦИЯ ОТКРЫТА ({side_text})\n"
            f"Вход: {entry_price:.2f} USDT\n"
            f"TP: {tp_price:.2f} USDT (+{tp_percent * 100}%)\n"
            f"SL: {sl_price:.2f} USDT (-{sl_percent * 100}%)\n"
            f"Объём: {quantity}"
        )

        msg = (
            f"✅ ПОЗИЦИЯ ОТКРЫТА ({side_text})\n"
            f"Вход: {entry_price:.2f} USDT\n"
            f"TP: {tp_price:.2f} USDT\n"
            f"SL: {sl_price:.2f} USDT"
        )
        loop.run_until_complete(notifier.send_message(msg))

        return active_position

    except Exception as e:
        logger.error(f"❌ Ошибка при открытии позиции: {e}")
        msg = f"❌ Ошибка при открытии позиции: {e}"
        loop.run_until_complete(notifier.send_message(msg))
        return active_position
