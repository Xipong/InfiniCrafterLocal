# Локальное исправление потери собственных projectile profiles в PR #330

Статус: опубликован в draft PR #330 как b12908dc06dc88da4baa6203f99a6cebd5e9e2a5. Все 24 файла и остальные blobs проверены. CI не запущен: текущий main 9e21dff уже включает #328/#331, GitHub сообщает конфликт handbook и native test registry. Интеграция main и проверка объединённого commit ещё требуются. Merge не выполнялся. Основа корректировки: fc6d429; pre-PR baseline: be28b720.

## Ошибка и граница исправления

Удаление выбранных inventory/fallback ammo-примеров ошибочно затронуло `nativeReplacementProjectileRaw`, включая собственные подтверждённые outputs оружия. Python также удалял эти profiles и их derived units. Предыдущие absence assertions и слишком широкое разрешение diff закрепляли потерю вместо продуктового контракта.

Восстановлены полные канонические projectile snapshots для известных literal outputs из certified native rules/fixed spawn sites и inspected weapon hooks. Ammo catalog и инвентарь не обходятся. Один профиль на ID сохраняет все его source sites, условия, порядок и provenance. Условность, blocked dispatch, opaque later hooks и final-shot unknown остаются явными. Незарегистрированный ID и недоступный snapshot имеют причину unknown. Лимит старой выборки трёх ammo-примеров не переносится на source outputs.

Python сохраняет объявленные replacement profiles, их provenance/scope/unresolved reason и derived motion units. Старые profiles сохраняются с исходным scope, без догадок о применимости. Конкретные inventory/fallback ammo samples и candidate bindings остаются исключены. Настоящий ammo-parent сохраняет собственные item/projectile facts. Никакие формулы урона или новые правила дизайна Author не вводились.

## Проверяемые примеры

- Настоящий baseline MoltenFury → FireArrow: восстановлены все 55 исходных raw полей без различий; новые `sourceReferences`/`profileScope` добавлены отдельно. В том числе penetrate=1, timeLeft=1200, extraUpdates=0, attack source, условный OnFire 1/3 на 180 ticks и lifetime=20 s.
- В этом конкретном FireArrow capture `motionReference` и `collisionReference` были null и до #330. Положительные motion/collision/child observations проверены отдельно: native profiles 1, 974 и 617→618 под явно объявленными headless hook fixtures.
- Pulse Bow, Hellwing, другие native replacements, fixed spawn и Daedalus delivery проверяются настоящими native packets. Conditional outputs не зависят от наличия подходящего ammo в инвентаре.
- Source-defined ModItem/GlobalItem cases покрывают более трёх разных outputs, повторные source sites, opaque later hook, suppression, invalid ID, unavailable defaults, пропущенный clock и один уровень child references. Это не live Calamity capture.

## Стадийные контракты

Independent replay старого настоящего MoltenFury source даёт точное baseline equality в 24 сочетаниях: Author/Visual/VFX и их Repair × json_schema/json_object × root/fingerprint. Полные FireArrow profile, source semantics и lifetime-derived rows возвращены.

Существовавшая до #330 presentation-проекция Visual/VFX по-прежнему исключает части `attackReference.motionDispatch/motion/collision/positionIntegration`. Полный Author mechanics context и прежняя stage-specific presentation граница проверяются отдельно. Сам старый presentation policy здесь не менялся; общий collision coverage gap исследуется отдельно.

## Проверки

Финальная интегрированная версия: 9156 Python PASS / 30 SKIP, все 6 официальных partitions и 282/282 test files ровно по одному разу; 664 native PASS / 0 FAIL; 17/17 static gates PASS. Хеши исходников неизменны между сборкой/проверками и frozen checkpoint. Проверен настоящий native ammo extractor и свежесть generated catalog/handbook.

419 canonical/native C# файлов собраны direct Roslyn: 0 errors, 2 известных CS1701 reference warnings. SDK CLI/MSBuild блокируется локальной ошибкой NuGet-Migrations mutex; direct Roslyn не объявляется MSBuild/tML package build. Skips: 29 Playwright и 1 linked-source asset transport test, не выполнивший свои 14 runtime checks. Compileall и workbench Python PASS; PowerShell regression unavailable, pwsh отсутствует. Игра, GPU, multiplayer и live LLM calls не запускались. Prewarm не добавлялся.

## Дополнительная найденная граница: внешний projectile guard

После первого полного checkpoint найден старый дефект source extractor: MoltenFury native ItemCheck_Shoot сначала проверяет current projectile=1, затем weapon type=120 и только тогда заменяет projectile на 2. Старый extractor терял внешний predicate. Настоящий JesterArrow oracle дал projectile 5, а прежняя source-модель ожидала 2. Узкая корректировка общего contiguous-enclosing-guard proof теперь включена в финальный проверенный checkpoint. Новое более широкое CFG/SSA extension, Last Prism и Dark Spark в него не входят.

Hellwing Bow проверен как более показательный случай: Wooden→485, Flaming→2, Jester→5, Holy→91. Собственный bat profile 485 восстановлен точно по всем 55 исходным полям. Условие относится к текущему projectile 1, а не к ammo-item ID; это сохраняет правильный смысл также для Endless Quiver. Текущая wiki описывает 1.4.5.x, где менялся разброс специальных стрел; native oracle здесь закреплён на tML 1.4.4.9, поэтому wiki не используется как источник точного spread.

Повторные одинаковые guards, оба порядка вложенности item/projectile, byref/local targets, противоречивые predicates, foreign entries и opaque writes проверены. Неполное доказательство не становится unconditional conversion. Доказанные literal source sites сохраняют профиль отдельно от неизвестной применимости; непроверенная принадлежность не превращается в weapon-owned profile. Любой unresolved native write сохраняет aggregate unknown, не стирая доказанные правила. 28 настоящих shot cases и независимое review прошли.

## Реальные размеры запросов

Измерены 42 фактических offline HTTP body на версию через production request builders для Chat/Responses/Codex, двух форматов и Author/Visual/VFX/repair. Для обычных трёх Chat стадий итог: json_object 528443 bytes (528383 chars), на 9.00% меньше pre-PR baseline; json_schema 666582 bytes (666522 chars), на 7.27% меньше baseline. Возвращённые полезные профили добавляют около 42 KB относительно дефектного опубликованного PR. Ничего не обрезается для достижения меньшего размера.

Tokenizer недоступен. chars/4 даёт лишь приблизительный ориентир 132097 / 166632 на три стадии, не измеренные токены, цену или usage. Live inference не выполнялся. Полные bodies, сравнительные JSON/CSV и hashes сохранены.

## Свежий headless profiling

Шесть отдельных процессов завершились exit 0. Одинаковый profiler; обычный craft без предварительного dump/catalog setup, два родителя, раздельно main capture и worker resolve. Внутри каждого run полный payload warm/cold parity=true. Craft sample catalogs пусты, это не FPS замер загруженной Calamity.

| Boomstick + Molten Fury | До PR330 | Исправленный checkpoint |
| --- | ---: | ---: |
| Первый main capture | 898.2 ms | 676.5 ms |
| Два warm main capture | 80.3 / 38.4 ms | 6.36 / 5.02 ms |
| Первый worker resolve | 15.16 s | 9.79 s |
| Source-cache-reset worker | 15.02 s | 8.48 s |

Дефектный опубликованный PR давал worker cold 4.72 s, но не собирал нужные replacement profiles; восстановление данных ожидаемо дороже и не должно оцениваться как ненужная потеря скорости. Cold plain/mixed main capture всё ещё 509–557 ms, поэтому полного устранения первого фриза нет. Исправленный source-cache-reset maxPump=11.63 ms: бюджет мягкий, один callback не прерывается. Reset не сбрасывает static Lazy/native certificates/JIT и не называется полным cold restart. Эти ограничения не скрываются.

## Итоговая граница

В проверенном объёме независимый broad-diff аудит не нашёл других непреднамеренных потерь PR330. Это не гарантия полноты по всем модам. Существующие helper-spawn/magic coverage gaps изучаются отдельно. Этот checkpoint восстанавливает конкретную регрессию и исправляет доказанный внешний predicate; не вводит формулу урона, новый дизайн Author, prewarm или более широкое CFG extension.
