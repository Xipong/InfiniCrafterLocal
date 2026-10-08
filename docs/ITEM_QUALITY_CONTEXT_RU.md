# Качество контекста и явная физика — 0.4.250

## Сохранность родителей

`parent_context_cards.py` передаёт точные accepted gameplay/runtime facts generated-родителя, включая независимые buffs, mobility, light и scale. Это read-only context, не приказ наследовать все функции. Для Visual/Repair отдельно передаётся принятая внешность с entity identity; Gameplay не выбирается из palette/silhouette/prose. Проекции копируют источник, не изменяют recipes.

Настоящий `GeneratorClient.Prepare` получает literal native tooltip через `Lang.GetTooltip`: строки, язык текущей UI culture, exact fullName и owner source. Prefix нормализуется только в request clone, оригинал и refund остаются прежними. Generated proxy tooltip не принимается за описание accepted generated definition. Если native text недоступен, он остаётся неизвестным. При более 64 строках или 16 384 символах отказывается вся optional source observation с provenance/status — предложение не обрезается и не подаётся как буквальная цитата. Tooltip не является числовым сертификатом native AI и не парсится хостом в механику.

## Движение

`move_straight` сохраняет скорость без gravity/drag; generated proxy не исполняет native AI по `arrow`, имени или `aiStyle`. `move_gravity_arc` добавляет явно выбранный vertical velocity increment с первого projectile update. Author должен осмысленно выбрать траекторию; прямое движение остаётся допустимым, если оно намеренное. Код не добавляет bow preset и не меняет уже сохранённые снаряды.

Для exact `Terraria/WoodenArrowFriendly` передаётся проверенная read-only reference dry initial flight: vertical acceleration начинается на 15-м native AI invocation, increment 0.1 pixels/update, downward cap 16 pixels/update. Она наблюдалась через настоящий native `Projectile.AI` отдельно на SDK и установленной tML; два точных SHA256 `AI_001` IL сертифицированы независимо, а source reference сообщает фактически совпавший hash. При другой method identity reference отсутствует, а не угадывается по aiStyle. Это ограниченный исходный факт, не новый gameplay executor, не универсальная симуляция arbitrary/modded AI и не обещание идентичного liquid/collision/global-mod behavior. Generated immediate gravity не выдаётся за точную копию native delayed AI.

## PNG

Image builder передаёт selected canvas, final-frame render extent и применимые authored scale/pivot/axis facts в техническом brief, отдельно от authored art. Более высокий canvas при неизменном renderSize не увеличивает размер в мире. Читаемость оценивается по display pixel budget; handle должен соответствовать authored grip, distinctive shape/count — самой композиции. Нет auto upscale/crop, догаданного grip и обязательного второго модельного judge. Техническая валидность PNG по-прежнему не удостоверяет художественную форму.

## Engineering limits и баланс

Author character guard увеличен с 96 500 до 196 608 после воспроизводимого отказа source-rich packets, в том числе 120 443-character literal-tooltip case. Это локальный engineering bound, не настройка модельного token context/output. Ни capabilities, ни parent facts не удаляются ради guard; превышение остаётся явным отказом. Размер actual serialized native snapshots проверяется отдельно от source-defined и synthetic controls.

Host recommended damage и parent-dependent damage envelope удалены. Literal parent damage и hard registry bounds сохранены; code не переводит healing/value/rarity в рекомендуемый урон. Codex catalog protocol использует актуальный version-gated discovery; catalog listing не является live inference acceptance.

## Проверка и обновление

Обновляй мод и LocalGenerator вместе. Новые context/physics/image/audio choices относятся к будущему authoring, runtime расхода и buff identity — к выполняемым accepted bindings. Исторические definitions/PNG, баланс принятых меча/лука и chain hold не переписываются. Offline builders, native headless consumer checks и обычный SDK/analyzer build проверяют указанные границы; игра/world/GPU/MP match и новые live generations не запускаются автоматически.
