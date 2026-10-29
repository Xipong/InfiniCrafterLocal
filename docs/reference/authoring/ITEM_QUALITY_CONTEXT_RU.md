# Качество контекста и явная физика

## Сохранность родителей

`parent_context_cards.py` передаёт точные accepted gameplay/runtime facts generated-родителя, включая независимые buffs, mobility, light и scale. Это read-only context, не приказ наследовать все функции. Для Visual/Repair отдельно передаётся принятая внешность с entity identity; Gameplay не выбирается из palette/silhouette/prose. Проекции копируют источник, не изменяют recipes. Generated parent передаёт полный exact accepted graph, не один guessed projectile или power/digest summary. Native ammo card сохраняет literal item/ammo observations и отдельно source-сертифицированные правила преобразования снаряда, условия и неизвестные hooks. При замене projectile сохраняются ammo-item damage/speed/knockback; профиль исходного снаряда не выдаётся за профиль выстрела. Наблюдаемое наличие не смешивается с player-free reference examples; текущий stack не передаётся. Подробные поля и границы — [native parent facts](../../development/pipeline/PARENT_NATIVE_FACTS_RU.md). Имя/теги не выбирают пример ammo или behavior; native runtime dump lookup остаётся буквальным factual tool context.

Настоящий `GeneratorClient.Prepare` получает сведения о tooltip в текущей UI culture с provenance и exact fullName. На локальном клиенте с активным игроком tModLoader формирует нативные строки и вызывает `ModItem`/`GlobalItem.ModifyTooltips` в обычном порядке. Передаются описательные строки и изменённые хуками native-строки, а не все обычные дублирующие характеристики. Изменённые хуками строки характеристик — отображаемые значения с учётом локального игрока, не базовые stats; это явно указано в `tooltipSource.modifiedNativeLines`. Хуки получают клон исходного Item: `CloneDefaults` сбрасывает prefix, сохраняя клонированные ModItem/GlobalItem instance data по правилам tModLoader; хуки получают отдельный Item; произвольные внутренние ссылки, custom Clone и глобальное состояние стороннего мода не sandbox-изолированы. Результат — ограниченное наблюдение, не полный отрисованный UI, не сертификат механики и не исполнение поведения родителя. На dedicated server и без точного local-player context локальные UI-хуки не исполняются: отдаётся только `Lang.GetTooltip` с `hookContext=unavailable` (в том числе исходный placeholder); сервер не притворяется клиентом. Получение hook-данных клиента для server-authoritative multiplayer здесь не реализовано. При исключении хука частичный результат не передаётся: сохраняется исходный literal с provenance `observed_literal_hook_failed`, если он уже был безопасно снят. При более 64 строках или 16 384 символах отказывается вся optional source observation, а не обрезанное предложение. Generated proxy tooltip не принимается за описание accepted generated definition.

Числовой `raw.item.crit` копирует базовый `Item.crit` request clone после удаления prefix, включая явный ноль. Тот же исходный факт сохраняется в fingerprint/runtimeFacts. Это не измеренный итоговый шанс игрока и не сумма с `generatedParent.accessory.genericCrit`/armor bonuses; accepted generated definition остаётся отдельным read-only контекстом. Поле не добавляет capability, не заставляет Author наследовать крит и не изменяет generated gameplay или сохранённый рецепт.

## Движение

`move_straight` сохраняет скорость без gravity/drag; generated proxy не исполняет native AI по `arrow`, имени или `aiStyle`. `move_gravity_arc` добавляет явно выбранный vertical velocity increment с первого projectile update. Author должен осмысленно выбрать траекторию; прямое движение остаётся допустимым, если оно намеренное. Код не добавляет bow preset и не меняет уже сохранённые снаряды.

Для exact `Terraria/WoodenArrowFriendly` передаётся проверенная read-only reference dry initial flight: vertical acceleration начинается на 15-м native AI invocation, increment 0.1 pixels/update, downward cap 16 pixels/update. Она наблюдалась через настоящий native `Projectile.AI` отдельно на SDK и установленной tML; два точных SHA256 `AI_001` IL сертифицированы независимо, а source reference сообщает фактически совпавший hash. При другой method identity reference отсутствует, а не угадывается по aiStyle. Это ограниченный исходный факт, не новый gameplay executor, не универсальная симуляция arbitrary/modded AI и не обещание идентичного liquid/collision/global-mod behavior. Generated immediate gravity не выдаётся за точную копию native delayed AI.

`move_flail_tether` возвращается при false owner.channel, после отпускания/дальности return защёлкнут. Прямой active spawn exact target требует явного configure_item_use.channel=true; passive/event copies читают уже существующий channel владельца и не получают безусловного item requirement. Validator и frozen Repair используют одну canonical condition. Code19 следует живому cursor каждый AI, не initial launch axis. `move_front_hand` none→full даёт только6px хода; hitboxOffsetPx — фиксированный центр, не длина thrust/добавочный сдвиг sprite. Сравнение native parent geometry остаётся решением Author, без автоувеличения радиуса.

Native tool powers работают для use_item_body/spawn_entity, но временно обнулены для чистого apply_item_effects и place_item. Каждый следующий eligible active projection восстанавливает pick/axe/hammer из canonical definition; contactDamage/noMelee сами не отключают mining. Saved definitions не переписываются.

## PNG

Image builder передаёт selected canvas, final-frame render extent и применимые authored scale/pivot/axis facts в техническом brief, отдельно от authored art. Более высокий canvas при неизменном renderSize не увеличивает размер в мире. Читаемость оценивается по display pixel budget; handle должен соответствовать authored grip, distinctive shape/count — самой композиции. Нет auto upscale/crop, догаданного grip и обязательного второго модельного judge. Техническая валидность PNG по-прежнему не удостоверяет художественную форму.

## Engineering limits и баланс

Author character guard — **225000 Unicode-символов** полного compact JSON dossier (`ensure_ascii=False`, separators без пробелов), вне SYSTEM/HTTP wrappers и response schema. Необоснованное расширение до 400000 отменено вместе с глобальным словарём buff-ID. Parent-local effect references, source-derived ammo variants и literal source context проверяются в этом же бюджете; это локальный engineering bound, не token context/output. Вложенные numeric consumer constraints используют точные packet-local ссылки на полные определения; capabilities, domains, dependencies и source-rich parents не вырезаются. Общие правила секунд и округления задаются в `fieldGuide.paramNotation`; дословный повтор этого введения в отдельных параметрах удаляется, но собственное описание каждого потребителя сохраняется. Описание structured shape опускается только при полном совпадении с сохранённым `meaning` того же параметра; вложенные описания и ограничения остаются. Превышение остаётся явным отказом без clipping. Размер actual serialized native snapshots проверяется отдельно от source-defined и synthetic controls.

Author оценивает actual ingredient power/acquisition/rarity/economy совместно, reusable benefit и полный throughput (children/chains/bounces/cadence/yield/payment frequency). Ammo damage — вклад в совместимый launcher, не самостоятельная атака; снятие launcher requirement — новая выгода. Бесплатное повторное использование допустимо, обязательного cooldown всем вещам нет. Это model-facing guidance, не новый автоматический nerf или доказанное качество свежей генерации.

Host recommended damage и parent-dependent damage envelope удалены. Literal parent damage и hard registry bounds сохранены; code не переводит healing/value/rarity в рекомендуемый урон. Codex catalog protocol использует актуальный version-gated discovery; catalog listing не является live inference acceptance.

## Проверка и обновление

Точные повторения native read-only значений разделяются через `sourceSameAs: N` —
индекс полного значения в `nativeSourceFacts[N]` того же dossier. Consumer instruction
общая для Author/Repair. Раскрытие ссылок восстанавливает каждый исходный факт,
scope/неизвестность, scalar type, порядок и кратность; это не clipping, отбор
ammo или новый словарь готовых эффектов. Literal tooltips и accepted
`generatedParent` не заменяются ссылками. Source-unit guide строится по полным
фактам до sharing; guard проверяет фактически отправляемое представление.
Повторяющиеся разрешённые target-kind списки карточек также разделяются через
`targetsRef` → `fieldGuide.targetKindSets`: каждый kind и порядок сохраняются,
ни одна capability/граница/зависимость не удаляется. Это ссылки контекста,
не новые значения в authored runtimeProgram. Пулы фактов остаются в динамическом
USER-сегменте, не превращаясь в общие DEVELOPER-инструкции.

Обновляй мод и LocalGenerator вместе. Новые context/physics/image/audio choices относятся к будущему authoring, runtime расхода и buff identity — к выполняемым accepted bindings. Исторические definitions/PNG, баланс принятых меча/лука и chain hold не переписываются. Offline builders, native headless consumer checks и обычный SDK/analyzer build проверяют указанные границы; игра/world/GPU/MP match и новые live generations не запускаются автоматически.
