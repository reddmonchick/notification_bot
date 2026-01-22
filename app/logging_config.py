import logging
import sys

def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Удаляем все хендлеры, которые могли быть добавлены aiogram
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(formatter)

    root.addHandler(handler)
