# toolbox/live-generation

- `generate_20_items_without_images.py` — Live20: preflight конфигурации, фиксированные кейсы, параллелизм 3, прозрачный учёт Author/Repair/Visual/VFX и HTTP-вызовов, запрет image backends, проверка image-boundary и сохранение приватных трасс вне Git.
- `live20_support_v5.py` — чистые вспомогательные функции отбора кейсов, контекстов стадий, температур, учёта запросов и transport retries.

Это acceptance-инструмент, не источник gameplay-семантики. Результат `summary.json` не заменяет C# replay или игру. См. `../README.md`.
