import logging
import sys

def setup_logging():
    # Получаем root-логгер
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Удаляем все существующие хендлеры (aiogram мог добавить свои)
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Создаём хендлер, который пишет в stdout (Docker читает именно его)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    # Формат логов
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    handler.setFormatter(formatter)

    # Добавляем хендлер в root
    root.addHandler(handler)
