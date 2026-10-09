# Уточнения Author/Repair и холодное чтение Luna 6

Это последовательный генератор предметов, не агент с инструментами. Модель получает свою задачу, точные входы, доступные механики и формат результата; описание оркестратора и остальных LLM-стадий ей не требуется. Concept → runtimeProgram → realization/selfEvaluation сохранены. RuntimeProgram остаётся единственным источником исполняемой механики; описание, category и tooltip не маршрутизируют поведение.

## Что изменено

- Исправлен путь к каталогу: `runtimeCapabilityContract.catalog.capabilities`. В карточке `configure_item_use` явно названы владельцы cadence/animation — `configure_item_stats`.
- Убраны противоречивое «других model passes нет» и лишняя лекция про последующие стадии/Repair. Общие nullable transport правила говорят только о форме; локальные Repair-инструкции по-прежнему закрепляют omission=no-change и frozen fields.
- `primaryEntityId` объяснён как выбор существующего владельца представления, не несуществующее дополнительное поле, controller или cap. Полное условие hidden-item случая сохранено.
- Optional с явным default не смешивается с одной лишь neutral-аннотацией. `localNpcHitCooldownEngineUnits` остаётся обязательным в обоих immunity modes, но owner его не использует — это теперь сказано прямо, без изменения requiredness.
- Batch count отделён от живого cap; hold не обещает новый spawn каждый tick. Возврат к владельцу тоже завершает projectile и вызывает on_kill. Точные bounce-исключения названы на карточке collision, не выбираются кодом по имени предмета.
- `damage_area_on_event` исключает непосредственную цель только для on_hit/on_crit. OnKill получает null directTarget, а не историю последнего попадания. Эта разница теперь видна Author и Repair; damage/runtime не менялись.
- Из model-facing `balanceCorridor` убран неинтерпретируемый `powerBudget`: это прежняя host-эвристика, смешивающая combat/tool/healing/rarity/value, без метрики расходования бюджета. Source facts и границы capabilities сохранены; новая рекомендация урона не добавлялась. Прочие consumers старого внутреннего профиля не переделывались.
- SelfEvaluation покрывает выбранные player actions/entity behavior/authored event actions. Связанные calls можно объединить в одну строку с точными refs; не требуется отдельная строка для каждого потенциального события без подписанного действия. Итоговое сравнение не выдаётся за сыгранный runtime test.

## Существенный data fix в Repair

Repair должен написать `realizationReplacement`, но прежний dossier терял исходный concept и параметры независимых корректных механик. Два документа с `intervalTicks=45/60` давали идентичный целый Repair request. Индекс bindings читал устаревшие root action/target и выдавал null.

Теперь существующий `acceptedItemContext` содержит точные read-only копии concept/runtimeProgram; индекс читает `usePolicy`. Это полный pre-repair источник, включая невалидные поля, а не уже принятый результат. Модель интерпретирует его вместе с только разрешёнными изменениями. Старый realization — не доказательство механики. **Permissions, create/delete policy и frozen merge не расширены.** Hostile counterexamples подтвердили сохранение независимого damage/interval/cost/accepted absence.

## Luna 6 — фактическое холодное чтение

Два независимых запуска `openai/gpt-6-luna` через существующий Nous route получили только реальные serialized Author messages на полных сохранённых parent cards Grenade+Bomb. Репозиторий, прошлый разбор и инструменты не использовались. Задача: составить предмет, затем отдельно назвать непонятное. Это qualitative screen, не статистика качества и не полноценная игровая генерация.

- **До:** Author valid, compiled wire valid. Модель заметила неопределённый powerBudget, чрезмерно широкое требование event coverage и противоречивое описание passes. Её report неверно перенёс исключение direct target на on_kill; ошибка прослежена до неточной registry-card prose.
- **После:** Author valid, compiled wire valid; эти замечания и прежняя ошибка не повторились. Новый вопрос про required-but-inactive cooldown исправлен последним уточнением. Последнее уточнение проверено офлайн, третий cold run ради одной строки не выполнялся.
- Вопрос «какой damageClass наследовать при разных родителях» не решался роутером: это намеренно выбор модели. Предложение сделать cooldown optional отвергнуто — изменена ясность, не контракт. Отсутствующее разрушение tiles не подменено словами из tooltip.

Capabilities/params/ranges/requiredness, validator semantics и C# не изменены. Восемь frozen authored fixtures дают прежние exact delivery bytes/SHA; первая модельная программа также компилируется прежним образом. Уточнения увеличили полный user packet примерно на 1,1 тыс. символов — это не оптимизация размера. Полные pins, cold outputs, проверки и source-bound evidence: task artifact `cache-and-prompt-deep-followup`.
