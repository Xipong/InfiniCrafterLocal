# `.agent`

Машинный control-plane репозитория для coding-агентов. Эта папка не загружается модом и не участвует в gameplay/runtime.

- `manifest.json` — канонические команды проверок и ownership-точки.
- `impact_rules.json` — связь изменённых файлов с обязательными проверками и контекстом.
- `task.schema.json` — контракт входной задачи агента.
- `run_result.schema.json` — контракт результата проверки.
- `current_state.json` — генерируемый `agentctl handoff`; не редактируется как источник истины вручную.

Расширение runtime-функции выполняется через канонический engine catalog и boundary/lifecycle policy. Добавлять логику в `.agent` нельзя: здесь только orchestration и evidence.
