# Технические исправления текущего мира

Локальный кандидат **0.4.252.2**, не опубликован и не установлен. Диагностический scope — world `1647275982`; исправления общих технических владельцев применимы к другим принятым экземплярам без правки сохранений. Старый мир исключён из выводов.

## Отчёты Author/Repair

- Canonical owner: `LocalGenerator/infini_local/core/runtime_authoring/program_schema.py`. `realization.description` допускает 1…4000, `playerExperience` 1…3000 Unicode code points.
- Реальные Author и complete-replacement Repair shape cards читают эти границы из canonical schema; это важно и при `json_object`/schema-off, где provider schema не раскрывает ограничения.
- Слишком длинное значение отвергается без подрезания authored смысла. Набор ранее допустимых значений не сужается; gameplay/Visual/VFX не меняются.
- `GeneratedParentSummarySpec` в `GeneratedItemData.Model.cs` сохраняет эти длины при full/network transport, считая Unicode scalars, а не UTF-16 units. Compact player save остаётся reference-only.
- Независимый review воспроизвёл escaped Unicode report >100000 bytes и потерю ID при native `Item.Clone`. Serializer теперь использует существующий 256 KiB потолок registry chunk transport как единую константу; local clone отдельно копирует тот же stripped/normalized graph без сетевого byte admission. Предел конечный, report не обрезается. Это не обещание вместить любой DTO: сверх256KiB network явно отказывает, но локальный clone не превращается в placeholder из-за сетевого размера.
- Прежние 700/500 появились при binding-policy refactor `3831d93`; явного технического обоснования этих чисел в исследованной истории не найдено. Конечный предел защищает от неограниченного отчёта, но прежний был недостаточен для составных предметов.

## Повторы транспорта и redaction

- `services/codex_auth.py` owns повторы одного уже сериализованного Codex Request: те же body/headers/image turn ID, без нового Author/Repair, смены модели или paid fallback.
- Transient HTTP 408/409/425/500/502/503/504, reset/URLError/incomplete body повторяются в едином monotonic generation-transport deadline. Частичные SSE deltas разных попыток не склеиваются.
- Image sends: `INFINI_SPRITE_RETRIES + 1`, 1…9. Text sends: `INFINI_LLM_FALLBACK_NETWORK_FAILS`, 1…10. Это один transport owner, не вложенные бюджеты.
- Auth/quota 401/402/403/429, permanent/request-shape HTTP, redirect/TLS refusal, malformed response и исчерпанный deadline terminal. OAuth credential acquisition сохраняет отдельный прежний budget. Blocking DNS не объявляется исправленным.
- `visual_sprite_generation.py` сохраняет terminal deadline attribution вместо прежнего ошибочного PNG-write wrapper; exhausted transport не входит в semantic sprite regeneration.
- Pattern-only `rt_` распознаётся только с начала токена. Обычный `*_dart_raw_openai_codex_0.png` сохраняется; known-secret/JWT/API-key redaction остаётся. Полные diagnostics по-прежнему sanitized.

## Native cursor и held proxy

- `Common/Systems/GeneratedCursorItemPresentationSystem.cs` подключает только verified native `DrawInterface_40_InteractItemIcon`: заменяет type-wide `ContentSamples.ItemsByType` на точный выбранный `Item`, только для generated selected preview с готовым instance PNG. Disabled/foreign icon и missing image сохраняют native поведение.
- Пропускается только дополнительный static tint tail этого cursor owner; native ItemSlot продолжает работать и выполняет PNG tint сам. Unknown IL shape/source owner отвергается до частичной emission; unload снимает hook. Guard финального tint проверяет его собственную receiver→texture последовательность после ammo Draw; более ранний `TextureAssets.Item` не разрешает чужой final `GlowMask`.
- `GeneratedItem.ModifyItemDraw` подавляет только совпадающий готовый static held proxy. Unrelated colored/glow textures, cache entries, authored `hideUseGraphic`/release timing и custom AfterParent слой не меняются.
- Native checks используют exact frozen game-saved `Campfire Twin Wooden Sword` DTO из текущего мира, включая identity, два экземпляра shared type, missing-PNG/foreign/disabled controls и source-shape mutant. Это CPU native consumer evidence, не GPU/world/MP acceptance.

## Future-only контракт и design-вопросы

### Повторный returning бросок

У `g_44202b25cacbee06` и `g_c606cc2b5adac118` повторный ручной launch до возврата воспроизведён. `spawn.count=1` ограничивает одну активацию, `autoReuse=false` — удержание кнопки; ни одно не задаёт live cardinality. В исходной генерации отсутствовал explicit live cap; owner-attached guard неприменим к free projectile.

Добавлен opt-in `set_projectile_concurrency(maxActive: integer 1…96)` → `entity.spawn.maxActive`. Модель сама выбирает 1 или больше; отсутствие не создаёт cap. Считаются live экземпляры по owner + generated item ID + entity ID, независимо от inventory copy/binding/input/root/descendant. Pending delayed work не live; due dispatch проверяет admission заново и возвращает неиспользованный event budget. Shared SpawnRuntimeEntity отказывает целой effective batch после existing global/depth/event limits, не режет её по остаточным entity slots. CanUseItem/CanSpawnRoot применяют тот же ранний gate. Existing owner-attached repeat-use singleton и Hold одной existing batch сохранены; cap не является refill mode или rollback native costs/других activation events.

Saved definitions по решению пользователя не правятся, runtime не классифицирует предметы по names/movement. Legacy omission/full/network/definition hash сохранены; present null/type/out-of-range и cap на item_body отвергаются. Headless consumer evidence покрывает последовательные production producers; OS-thread concurrency и synchronous foreign GlobalProjectile.OnSpawn reentry не приняты как проверенный scope.

### Grenade-Bomb Bundle

`g_a63f559cb7957389`: speed5.5, gravity0.2/update, life180, шесть отскоков, бесконечное penetration, один contact hit по каждому NPC, отдельный terminal AoE radius64/base60. Horizontal friction отсутствует; на ровном полу X сохраняется, отскоки происходят на updates15/39/59/76/91/105, седьмой contact убивает на118 раньше fuse180. Первый NPC hit не детонирует. Это объясняет непривычное движение/взрыв, но на проверенных реальных Update/Damage/Kill boundaries runtime defect не найден. Contact и blast — две authored damage paths, не double dispatch.

Пользователь уточнил симптом: ожидается detonation при попадании в NPC. Existing primitives уже выражают её через explicit `pierce=1` + `on_kill` AoE: native contact исчерпывает penetration, затем Update вызывает Kill/OnKill. Новый kill opcode/preset не нужен. Registry cards в реальных Author/Repair раскрывают pierce1/-1, отсутствие implicit on_hit explosion, terminal event, N отскоков/смерть на следующем contact, ×0.78 collided-axis reflection, gravity без horizontal friction и ранний return/disabling tile collision при wall contact. Это факты executor, не инструкция выбирать взрыв или сохранять родительские capabilities. Saved Bundle/баланс не меняются.

Ошибочное описание returning предмета (гибель от стены вместо возврата) показывает расхождение authored prose и последствий выбранной композиции. Guidance исправлено у canonical capability owner; отдельный semantic verifier и автоматическая подгонка runtime под описание не добавлены. Это не доказательство, что будущая модель больше не ошибётся.

## Проверка и границы

Есть сохранённые RED→GREEN для report validation/prompt disclosure/C# parent transport, transport retry/redaction и exact native cursor output. Generated schemas, Repair audit и config registry обновляются canonical tools. Независимые review и integrated checks/SDK build записаны в task artifacts; окончательные counts/hash находятся в delivery receipt, а не в исторических release notes.

Не запускались игра, live AI/provider, новые генерации или MP-матч; worlds/players/config/auth и установленный мод не менялись. Поставка обновляет мод и LocalGenerator вместе, сохраняя личные config/cache/recipes/PNG.
