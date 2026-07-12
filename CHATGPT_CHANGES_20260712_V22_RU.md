# V22 — надёжность живого генератора и доставки

Коммит не добавляет кодовую семантику предметов. Planner/Visual Director по-прежнему решают, как именно смешиваются родители; код только сохраняет authored-решение, валидирует контракт и обеспечивает корректный жизненный цикл сервисов, кэша и ассетов.

## Что исправлено

### SD.CPP и тестовый runner

- SD.CPP завершается деревом процессов, а не только wrapper-процессом.
- На Windows используется `taskkill /T` с жёсткой эскалацией `/F`; на POSIX — отдельная process group.
- Закрываются лог-файлы, обрабатываются startup exit/timeout, signal handlers ставятся только из main thread и сохраняют предыдущие handlers.
- Pytest shard runner использует тот же process-tree cleanup. Старый зависающий хвост `sdcpp_service` больше не удерживает release validation.

### Image backend без скрытой подмены

- Канонизированы aliases backend’ов; неизвестное значение становится явной configuration error.
- Базовый default соответствует поставляемой конфигурации: `sdcpp`, а не `procedural`.
- ComfyUI без workflow больше не рисует procedural placeholder.
- Procedural backend возможен только при явном разрешении и выключенном strict AI authorship.
- Fresh generation блокируется при сломанном backend, но уже готовый валидный cache не объявляется испорченным только из-за текущего окружения.
- Preset «без картинок» действительно отключает обязательную доставку item sprite.
- `/health` и visual doctor показывают raw/canonical backend и причину ошибки.

### Cache quarantine

- Синтаксически битые, boundary-invalid и недоставляемые recipe cache-файлы переносятся в `invalid/` вместе с machine-readable причиной.
- Active index/health очищаются, поэтому один и тот же мусор не перечитывается при каждом крафте.
- Оригинальный payload сохраняется для диагностики, а следующая попытка начинает чистую регенерацию.

### Prompt/delivery quality

- Длинные prompts обрезаются на границе фразы/слова, а не посреди инструкции.
- Exact-дубли удаляются, технический sprite guard резервируется и не исчезает из конца prompt.
- Убраны скрытые художественные переписывания отрицаний вроде material/topology substitutions.
- Authored форма, включая буквальный целый верстак на мече, проходит без кодового выбора «правильной» конструкции.

### Конфигурация и live combine

- LLM env/config имеет одного канонического owner (`core.llm_config`); duplicate declarations в web server удалены.
- Добавлен coarse live-combine regression для `Деревянный меч + Верстак`: полный pipeline до cache, ранний strict preflight, отсутствие visual-only полей в `AttackSpec`, сохранение буквального authored prompt.
- Один объединённый regression-блок также проверяет backend failure, отсутствие procedural fallback, cache quarantine, SD.CPP cleanup и prompt compaction без раздувания suite десятками мелких тестов.

## Проверка

- `331/331` pytest tests passed (`87` файлов, 4 изолированных shard’а).
- Python compileall, JSON Schema, config registry, hygiene — PASS.
- AttackSpec parity `112/112`, GameplaySpec parity `65/65`.
- Projectile network parity `90/90` по порядку и wire type.
- Mutation gate `9/9`.
- Semantic runtime baseline `10/10`, `differences=[]`.
- Ruff PASS; Pyright `0 errors`.
- `ModSources` и изображения не изменялись.
- Реальная tModLoader/.NET сборка в текущем контейнере недоступна и не заявляется как пройденная.
