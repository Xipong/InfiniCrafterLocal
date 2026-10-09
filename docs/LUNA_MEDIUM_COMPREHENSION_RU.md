# 0.4.253: три холодных чтения Luna 6, medium

## Метод и результат

Три независимые сессии `openai/gpt-6-luna`, reasoning **medium**, по одному inference-вызову, без tools/source/истории проекта. Каждая получила полный актуальный production Author packet (system + Codex developer/user content) и создала предмет; затем объяснила назначенные функции. Все54 capabilities распределены по18 на читателя, но при генерации каждому доступен весь каталог. Это qualitative comprehension screen, не статистическая гарантия качества и не запуск трёх полных craft pipelines.

Все **3/3 Author objects** приняты неизменённым validator и compiler/strict wire без Repair. Механики различались: расходуемый метательный заряд; предмет с generated buff; инструмент с отдельным возвращающимся снарядом. Все54 function readings получены. Модели в основном правильно поняли единицы, зависимости и разделение поведения/описания; массового переименования или переработки языка по этому результату не требуется.

Это не3/3 семантически безошибочных отчёта: Luna-3 в финальном описании ошибочно приписала boomerang смерть от стены, хотя обе переданные карточки явно говорили wall→return/no kill. Luna-1 то же правило поняла верно. Ошибка сохранена в наблюдениях, а не скрыта за schema GREEN; увеличивать текст ещё одним повтором без доказательства пользы не стали.

## Обоснованные изменения

1. **Честное время родителей.** Один читатель заметил `parentUseTimeTicks=20` при реальных source17/10. Старый combat-only helper подставлял20, когда ни один родитель не наносил урон. В model-facing corridor теперь точные A/B useTime, отсутствие — null; производная `suggested` cadence убрана. Raw facts и numeric capability bounds сохранены; код не выбирает новый темп игры.
2. **Узкое условие maxStack.** Читатель обобщил ограничение1 на все reusable items. Текст теперь явно требует одновременно `place_item` и reusable spawn/use-body; без placement это правило не ограничивает stack. Validator не менялся и раньше имел именно узкое условие.
3. **База contact hitbox.** Вместо неопределённого «unscaled» пояснён текущий прямоугольник, который передаёт Terraria: не фиксированный PNG box. Сохраняется центр, размер округляется после hitboxScale, forgiveness добавляется с каждой стороны, минимум1px. Это описание уже существующего UseItemHitbox, не изменение геометрии.
4. **Умеренное сокращение.** Повторённое21раз описание числового consumer constraint сокращено323→268символов с сохранением binary64→float32, nonneutral/neutral, отказа без округления и предела round-trip. Boomerang summary сокращено210→164символа, сохранены owner-return, wall early return, tile collision off, отсутствие kill/bounce расхода и независимость NPC penetration. Остальные понятные функции не переписывались ради метрики.
5. **Правдивые границы событий.** `move_owner_on_event.safeTileOnly` проверяет только solid overlap, не bounds/lava как отдельный blink-on-use. AoE исключает direct target только для hit/crit; это не утверждение, что каждое expiry-событие лишено target payload. Обе карточки приведены к существующему consumer без изменения поведения.

Выявлена и явно описана незакрытая runtime-граница placement: Author schema допускает одновременно tile+wall, но текущая placement transaction исполняет один слой и отвергает оба enabled ID. В этом prose-only изменении схему не ужесточали и возможность тихо не удаляли; карточка теперь предупреждает об отказе вместо обещания неработающей композиции. Исполнение двойного placement требует отдельного runtime решения, не сокращения текста.

Различие tooltip Grenade/Bomb не признано ошибкой языка: модель вправе выбрать комбинацию, а отсутствующее разрушение тайлов не должно появляться из prose. Вопрос о неизвестной точной native hitbox не решён выдумыванием постоянного размера.

## Ёмкость и сохранность

- **54 capabilities / 241 params** без удаления, переименования или изменения типов, ranges, enums, requiredness, dependencies, reference rules, units и numeric projection metadata. Менялись только указанные `does`/`meaning` и advisory source timing.
- Каждый из трёх полных user packets стал короче на **868 символов** после всех уточнений, с точным сохранением полных parent cards. Provider token savings не измерялись.
- Все три полученных Author outputs по-прежнему валидны после правок. Восемь frozen delivery fixtures дают прежние bytes/SHA.
- Нет новой C#-механики, роутинга, дефолтов или подмены исходных данных тултипом. Native release отличается от0.4.252.3 только версией; прежние Lowery/cache/runtime fixes входят целиком.

## Для независимой перепроверки

Отдельный commit этой версии следует за принятым predecessor0.4.252.3; поэтому diff не смешивает ясность промпта с большим предыдущим аудитом. Владельцы изменений: `capability_registry.py`, `llm_authoring_prompt.py`; regression `test_luna_prompt_clarity.py`. Generated schema descriptions/inventory обновлены штатным exporter. Результаты полного pytest, CI, native/package проверки — в release notes/VERIFICATION.json.

Ограничения: без post-edit повторной model кампании, без мира/GPU/MP. Три удачных object-validation не доказывают идеальное понимание всех возможных комбинаций. Тексты, понятные читателям и совпадающие с consumer, оставлены как есть.
