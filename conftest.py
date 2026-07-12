# Файл-маркер для pytest. Содержимого не требуется.
#
# Когда pytest находит conftest.py, он считает эту папку корнем проекта
# и добавляет её в список путей, где Python ищет модули.
# Благодаря этому в тестах работает строка:
#     from src.schema import Scenario
# Без этого файла она упадёт с ошибкой
#     ModuleNotFoundError: No module named 'src'
