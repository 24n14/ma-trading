import logging
import aiohttp


# Настройка логгера для этого модуля
logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token, chat_id, proxy_data=None):  # Добавили proxy_data здесь
        self.token = token
        self.chat_id = chat_id
        print(f"DEBUG: Создаю нотификатор с токеном: {self.token[:5]}*** и ID: {self.chat_id}")
        self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.proxy_data = proxy_data  # Словарь: host, port, user, password

    async def send_message(self, text):
        print(f"--- ПОПЫТКА ОТПРАВКИ: {text[:20]}... ---")
        """Асинхронная отправка сообщения в Telegram"""
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }

        proxy_url = None
        if self.proxy_data:
            proxy_url = (
                f"http://{self.proxy_data['user']}:{self.proxy_data['password']}@"
                f"{self.proxy_data['host']}:{self.proxy_data['port']}"
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        self.url,
                        json=payload,
                        proxy=proxy_url,
                        timeout=15
                ) as response:
                    if response.status == 200:
                        logger.info("Уведомление в Telegram доставлено через HTTP-прокси")
                    else:
                        logger.error(f"Ошибка Telegram: {response.status}")
        except Exception as e:
            logger.error(f"Сетевая ошибка через прокси: {e}")

