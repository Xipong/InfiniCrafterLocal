# Технические исправления текущего мира

Действующие контракты технических owners; отдельные fixture observations ниже не являются общим game/GPU/MP stamp. Сохранения и личная конфигурация не редактируются.

## Отчёты Author/Repair

- Canonical owner — `core/runtime_authoring/program_schema.py`; optional `concept`/`realization` и текстовый `selfEvaluation` — advisory context, не gameplay authority. Report-only ошибки не требуют Repair. Полная [Author boundary](../reference/LOW_LEVEL_RUNTIME_AUTHORING_RU.md#construction).
- Optional `description` до 4000 и `playerExperience` до 3000 Unicode code points потребляются parent summary; `selfEvaluation` до 4000 — advisory текст, без обязательных verdict/check rows. Код не дописывает отчёт и не меняет runtime по prose.
- `GeneratedParentSummarySpec` сохраняет name/identity/description/playerExperience при full/network transport, считая Unicode scalars. Compact player save остаётся reference-only.
- Network serializer использует общий 256 KiB предел registry chunk transport. Local clone отдельно копирует тот же normalized graph без сетевого byte admission: превышение network bound даёт явный отказ, а не clipping report или placeholder clone. Это не обещание вместить любой DTO.

## Повторы транспорта и redaction

- `services/codex_auth.py` owns повторы одного уже сериализованного Codex Request: те же body/headers/image turn ID, без нового Author/Repair, смены модели или paid fallback.
- Transient HTTP 408/409/425/500/502/503/504, reset/URLError/incomplete body повторяются в едином monotonic generation-transport deadline. Частичные SSE deltas разных попыток не склеиваются.
- Image sends: `INFINI_SPRITE_RETRIES + 1`, 1…9. Text sends: `INFINI_LLM_FALLBACK_NETWORK_FAILS`, 1…10. Это один transport owner, не вложенные бюджеты.
- Auth/quota 401/402/403/429, permanent/request-shape HTTP, redirect/TLS refusal, malformed response и исчерпанный deadline terminal. OAuth credential acquisition сохраняет отдельный прежний budget. Blocking DNS не объявляется исправленным.
- `visual_sprite_generation.py` сохраняет terminal deadline attribution вместо прежнего ошибочного PNG-write wrapper; exhausted transport не входит в semantic sprite regeneration.
- Pattern-only `rt_` распознаётся только с начала токена. Обычный `*_dart_raw_openai_codex_0.png` сохраняется; known-secret/JWT/API-key redaction остаётся. Полные diagnostics по-прежнему sanitized.

## Native cursor и held proxy

- `Common/Systems/Presentation/GeneratedCursorItemPresentationSystem.cs` подключает только verified native `DrawInterface_40_InteractItemIcon`: заменяет type-wide `ContentSamples.ItemsByType` на точный выбранный `Item`, только для generated selected preview с готовым instance PNG. При смерти preview выбранного generated item подавляется до native cache swap, включая disabled cached icon; живые disabled/missing previews и explicit foreign icons сохраняют native поведение.
- Пропускается только дополнительный static tint tail этого cursor owner; native ItemSlot продолжает работать и выполняет PNG tint сам. Unknown IL shape/source owner отвергается до частичной emission; unload снимает hook. Guard финального tint проверяет его собственную receiver→texture последовательность после ammo Draw; более ранний `TextureAssets.Item` не разрешает чужой final `GlowMask`.
- `GeneratedItem.ModifyItemDraw` подавляет только совпадающий готовый static held proxy. Unrelated colored/glow textures, cache entries, authored `hideUseGraphic`/release timing и custom AfterParent слой не меняются.
- Native checks используют exact frozen game-saved `Campfire Twin Wooden Sword` DTO из текущего мира, включая identity, два экземпляра shared type, missing-PNG/foreign/disabled controls и source-shape mutant. Это CPU native consumer evidence, не GPU/world/MP acceptance.

## Явные runtime choices

### Повторный returning бросок

`spawn.count` ограничивает одну активацию, `autoReuse=false` — удержание кнопки; ни одно не задаёт live cardinality. Для free projectile owner-attached singleton не является общим cap.

Opt-in `set_projectile_concurrency(maxActive: integer 1…96)` → `entity.spawn.maxActive`. Модель сама выбирает 1 или больше; отсутствие не создаёт cap. Считаются live экземпляры по owner + generated item ID + entity ID, независимо от inventory copy/binding/input/root/descendant. Pending delayed work не live; due dispatch проверяет admission заново и возвращает неиспользованный event budget. Shared SpawnRuntimeEntity отказывает целой effective batch после existing global/depth/event limits, не режет её по остаточным entity slots. CanUseItem/CanSpawnRoot применяют тот же ранний gate. Existing owner-attached repeat-use singleton и Hold одной existing batch сохранены; cap не является refill mode или rollback native costs/других activation events.

Saved definitions по решению пользователя не правятся, runtime не классифицирует предметы по names/movement. Legacy omission/full/network/definition hash сохранены; present null/type/out-of-range и cap на item_body отвергаются. Headless consumer evidence покрывает последовательные production producers; OS-thread concurrency и synchronous foreign GlobalProjectile.OnSpawn reentry не приняты как проверенный scope.

### Явная detonation и terminal events

`pierce=1` + `on_kill` AoE выражает взрыв после исчерпания penetration: native contact, затем Kill/OnKill. `on_hit` сам по себе не убивает projectile. Bounce count, collided-axis reflection, gravity, tile collision и terminal events имеют независимые consumers; код не выводит detonation/fuse/friction из названия или prose. Parent behavior — read-only context, не требование наследовать capabilities. Полные [event distinctions](../reference/LOW_LEVEL_RUNTIME_AUTHORING_RU.md#validation-events) принадлежат canonical registry/consumer.

## Проверка и границы

Generated schemas, Repair audit и config registry проверяются canonical tools; команды и доступные уровни proof — [TESTING](TESTING_RU.md). Offline/headless output не доказывает game-loop, GPU, live AI/provider или MP match. Обновление мода и LocalGenerator не требует редактирования личных config/cache/recipes/PNG.
