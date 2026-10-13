# Если генератор не работает — 0.5.00

## Окно приложения не открывается

1. Запускай `OPEN_INFINICRAFT.bat` из полностью распакованного проекта.
2. Прочитай оставшееся в BAT сообщение. Нужны Python 3.11+ с Tcl/Tk, права на запись `LocalGenerator/.venv` и возможность установить зависимости Python.
3. Повтори запуск после исправления. Модели не ставятся вместе с Pillow/pydantic.

## Сервер не отвечает

Проверь [health](http://127.0.0.1:5055/health) и правильную папку/порт в **«Диагностике»**. `serverRoot` и `configPath` должны относиться к открытой копии проекта. Один сервер на порт; смена `INFINI_PORT` сама по себе не меняет endpoint мода.

- **Сохранение** не применяет настройки к уже работающему процессу. После изменения — безопасный restart.
- Занятый/непроверенный сервер не убивается автоматически. HTTP 409 busy, timeout или неизвестный root/PID — отказ, не разрешение скрытого kill.
- **Принудительный restart** требует отдельного подтверждения и может прервать craft; не доказывает refund/recovery. Если старый сервер не возвращает нужные данные, останови его прежним владельцем или `Ctrl+C`.
- Для подробной консоли доступен [06_START_SERVER_DIRECT.bat](../../06_START_SERVER_DIRECT.bat). Он обходит GUI guard: сначала убедись, что порт свободен, затем останови `Ctrl+C`.

`ok=true` — только готовность HTTP-сервиса. `/health` не проверяет живость отдельного sd.cpp (`serverAlive=null` означает «не проверялся»). Проверка image backend отдельно может обращаться к внешнему сервису; image probe может создавать рисунок и расходовать квоту. Не запускай его без необходимости.

## Craft завершился ошибкой

| Симптом | Что проверить |
|---|---|
| Auth / quota | Собственный аккаунт/key, условия и остаток квоты; смена JSON format не лечит quota |
| Schema/request rejected | Выбранный provider/model и transport envelope; `424 llm_request_rejected` не ошибка authored JSON |
| Model timeout | Стадию/ожидание в trace, доступность endpoint; не запускай параллельную копию |
| PNG/config error | Image backend URL или реальные пути exe/weights; внешний sd.cpp требует работающего сервера |
| Старый предмет без definition/PNG | `/getinfini`, `/infinicache stats`, native sync или доступность выбранного HTTP asset URL |
| Invalid texture/placeholder | Placeholder безопасен для показа, но не разрешает обход обязательного PNG delivery |

Точные transport ошибки и бюджеты: [request shape](../development/LLM_TRANSPORT_REQUEST_SHAPE_RU.md), [provider admission](../development/LLM_PROVIDER_ADMISSION_RU.md). Runtime recovery не гарантирует исправление любого повреждённого файла.

## Логи, очистка и отчёт

- **«Диагностика»** показывает последний health/trace snapshot, не realtime доказательство успешного результата. Refresh не вызывает модель. Opaque request IDs не native lane IDs.
- [Trace](http://127.0.0.1:5055/trace), `cache/events.ndjson` и stage artifacts помогают найти стадию/ошибку. GUI использует effective cache root; относительный root считается от `LocalGenerator`.
- Полное логирование default ON: sanitized prompts/ответы/stage requests без обрезки. OFF отключает дополнительный trace, не gameplay/history; сохрани и перезапусти. [Подробный контракт](COMMANDS_RU.md#полное-логирование-localgenerator).
- GUI очистка удаляет только три trace NDJSON, не recipes/PNG; чужой cache/непроверенный сервер и симлинки отвергаются. Дополнительные artifacts проверяй отдельно. [Команды](COMMANDS_RU.md).

Для issue приложи версию, способ запуска, стадию, точный error code и обезличенный фрагмент. **Не публикуй API keys/OAuth, личный config, raw prompts, токены или полные трассы без просмотра.** Offline checks не доказывают живую модель, GPU или MP.
