# V23 — Visual Director contract и live asset sequencing

Этот патч не добавляет художественную семантику в код. Planner и Visual Director по-прежнему решают, будет ли второй родитель приклеен целиком, разобран на детали, превращён в материал или сохранён отдельной частью. Код отвечает только за сохранность authored-решения, JSON-форму, технические роли ассетов и наличие runtime consumer.

## Что исправлено

### Один контракт Visual Director

- Вынесен чистый `visual_director_contract.py`: bounded parent evidence, фактический JSON Schema, usefulness/projection checks.
- Директор получает raw Terraria facts обоих родителей, canonical facts, `sourceRolePreservation`, planner `visualIntent`, compiled attack facts и provenance уже существующих visual-полей.
- Code-fallback `visual.imagePrompt` больше не выдаётся директору как authored planner evidence.
- Fresh response использует по одному top-level prompt на item/projectile/impact/child/field. Старые `bakedAssets.<role>.prompt` мигрируют shape-only и удаляются как второй competing source.
- Unknown asset roles вроде `bakedAssets.aura` отклоняются даже если backend проигнорировал response schema.
- Singleton JSON strings для list-полей (`qualityNotes`, `animationPlan`, `assetDependencies`, `vfxMaterialHints`, palette) канонизируются без изменения смысла; прочие неверные типы остаются ошибками.

### Атомарное применение

- Visual Director теперь проектируется в deep-copy и коммитится только после полной boundary/palette/prompt/asset проверки.
- Ошибка на позднем шаге больше не оставляет сырой `visualKit`, частично изменённый `visual`, presentation-поля в `attack` или ложный success debug.
- Rejected raw output и transport mode сохраняются только в diagnostics.

### Реальный sequencing ассетов

- Hybrid VFX manifest создаётся до optional asset runtime gates. Field sprite больше не отклоняется только потому, что подтверждающий VFX slot появлялся двумя стадиями позже.
- После VFX compile применяются runtime gates, затем strict visual-authoring boundary, и только потом вызывается image backend.
- Явный model-authored `particle_vfx` для child больше не принудительно превращается кодом в `baked_sprite`; C# runtime fallback остаётся доступен, поэтому optional PNG действительно остаётся решением Visual Director.
- Cache hit проходит те же VisualKit/VFX boundaries и narrow legacy migration, что fresh craft.

### Prompt integrity

- Cleanup использует word-boundary patterns: `texture`, `grounded`, `clock hands`, `room inside an orb` и `landscape painted on a shield` больше не уничтожаются из-за подстрок `text`, `ground`, `hands`, `room`, `landscape`.
- Shared style guide доходит до всех role prompts.
- Runtime multiplicity не переписывает authored topology: connected bundle/multipart body сохраняется, а runtime по-прежнему создаёт authored количество экземпляров.
- Role guards ограничивают только техническую роль sprite (item/projectile/impact/child/field), не выбирая дизайн предмета.

### Transport и диагностика

- Visual Director отправляет реальную Pydantic-derived JSON Schema. Если OpenAI-compatible gateway отклоняет `response_format`, transport безопасно повторяет запрос без неё; Pydantic boundary остаётся окончательным validator.
- Debug фиксирует requested/used response format, provider, reasoning mode, model, status, bounded context size и выполненные legacy shape repairs.

## Что не менялось

- `ModSources` и C# gameplay/runtime.
- Урон, balance, runtime families, child budgets и network protocol.
- Изображения и бинарные ассеты.
- Код не определяет, как именно должны выглядеть меч, верстак или их комбинация.

## Проверка

- `349/349` pytest tests passed (`87` файлов, 4 isolated shard'а: `100 + 96 + 79 + 74`).
- Python compileall, JSON Schema, config registry, hygiene — PASS.
- AttackSpec parity `112/112`, GameplaySpec parity `65/65`.
- Projectile network parity `90/90` по порядку и wire type.
- Mutation gate `9/9`.
- Semantic runtime baseline `10/10`, `differences=[]`.
- Ruff PASS; Pyright `0 errors`.
- `ModSources` и изображения не изменялись.
- Реальная tModLoader/.NET сборка в текущем контейнере недоступна и не заявляется как пройденная.
