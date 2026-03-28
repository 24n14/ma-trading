import logging
import time
import asyncio

logger = logging.getLogger(__name__)

async def close_position(exchange, symbol, side, current_price, reason,
                   active_position, notifier):
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

        active_position['is_open'] = False

        emoji = "✅" if profit_loss > 0 else "❌"
        msg = (
            f"{emoji} ПОЗИЦИЯ ЗАКРЫТА ({reason})\n"
            f"Вход: {entry_price:.2f}\n"
            f"Выход: {exit_price:.2f}\n"
            f"Прибыль/Убыток: {profit_loss:+.2f} USDT ({profit_loss_percent:+.2f}%)"
        )
        logger.info(msg)
        await notifier.send_message(msg)
        await asyncio.sleep(1)
        new_balance = exchange.fetch_balance()['total'].get('USDT', 0)
        balance_msg = f"💰 Новый баланс: {new_balance:.2f} USDT"
        logger.info(balance_msg)
        await notifier.send_message(balance_msg)

        return active_position  # ✅ ВОЗВРАЩАЕМ!

    except Exception as e:
        logger.error(f"❌ Ошибка при закрытии позиции: {e}")
        try:
            await notifier.send_message(f"❌ Ошибка: {e}")
        except:
            pass
        return active_position