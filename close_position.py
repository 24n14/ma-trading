import logging
import time
import asyncio

logger = logging.getLogger(__name__)


async def close_position(exchange, symbol, side, current_price, reason,
                         active_position, notifier):
    """Закрытие позиции по TP или SL с верификацией"""
    try:
        entry_price = active_position['entry_price']
        quantity = active_position['quantity']
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Создаём рыночный ордер на закрытие
                if side == 'long':
                    order = exchange.create_market_sell_order(symbol, quantity)
                else:
                    order = exchange.create_market_buy_order(symbol, quantity)

                # Проверяем, что ордер создан
                if not order or 'id' not in order:
                    logger.error(f"❌ Ошибка: ордер не создан для {symbol}")
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue

                order_id = order['id']
                logger.info(f"📝 Ордер создан: {order_id}")

                # Ждём заполнения ордера (max 5 секунд)
                filled = False
                for _ in range(5):
                    await asyncio.sleep(1)
                    try:
                        order_status = exchange.fetch_order(order_id, symbol)

                        if order_status['status'] == 'closed':
                            filled = True
                            order = order_status
                            break
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка при проверке статуса: {e}")

                if not filled:
                    logger.warning(f"⚠️ Ордер не заполнен полностью, отмена...")
                    try:
                        exchange.cancel_order(order_id, symbol)
                    except:
                        pass
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue

                # Получаем финальную цену закрытия
                exit_price = order.get('average') or order.get('price') or current_price

                if not exit_price:
                    logger.error(f"❌ Не удалось получить цену закрытия")
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue

                # Расчёт P&L
                if side == 'long':
                    profit_loss = (exit_price - entry_price) * quantity
                    profit_loss_percent = ((exit_price - entry_price) / entry_price) * 100
                else:
                    profit_loss = (entry_price - exit_price) * quantity
                    profit_loss_percent = ((entry_price - exit_price) / entry_price) * 100

                # Обновляем позицию
                active_position['is_open'] = False
                active_position['exit_price'] = exit_price
                active_position['profit_loss'] = profit_loss
                active_position['profit_loss_percent'] = profit_loss_percent
                active_position['close_reason'] = reason
                active_position['close_time'] = int(time.time())

                # Отправляем уведомление
                emoji = "✅" if profit_loss > 0 else "❌"
                msg = (
                    f"{emoji} ПОЗИЦИЯ ЗАКРЫТА на {symbol}\n"
                    f"📊 Вход: {entry_price:.2f} | Выход: {exit_price:.2f}\n"
                    f"💰 P&L: {profit_loss:.2f} ({profit_loss_percent:.2f}%)\n"
                    f"🔔 Причина: {reason}"
                )

                logger.info(msg)
                if notifier:
                    notifier.send(msg)

                return active_position

            except Exception as e:
                logger.error(f"❌ Ошибка при закрытии позиции (попытка {retry_count + 1}): {e}")
                retry_count += 1
                await asyncio.sleep(1)

        # Если все попытки исчерпаны
        logger.error(f"❌ Не удалось закрыть позицию после {max_retries} попыток")
        if notifier:
            notifier.send(f"❌ ОШИБКА: не удалось закрыть позицию на {symbol}!")

        return active_position

    except Exception as e:
        logger.error(f"❌ Критическая ошибка в close_position: {e}")
        if notifier:
            notifier.send(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
        return active_position
