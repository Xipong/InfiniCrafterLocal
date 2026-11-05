# Универсальное расширение native ammo analyzer

Локальный результат: `ifc-conversion-analyzer-20261105`, отдельная копия integrated outer-guard/restoration tree. Основной tree не изменён; Git-объекты, ветки, коммиты, PR и запуск игры не выполнялись.

## Что исправлено

Старый matcher требовал, чтобы весь item-блок состоял только из literal assignment и простых projectile equality guards. Поэтому сложный расчёт траектории рядом с простой state-dependent записью скрывал доказуемую механику.

Новый `native_ammo_control_flow.py` работает с общей структурой IL:

- Проверяет item header/body ownership и входы в середину выражений.
- Строит predecessor graph и обратную достижимость. Прыжок из завершённой соседней ветки, пересекающий диапазон offsets, не считается enclosing guard, если из него нет пути к рассматриваемому item-блоку.
- Для каждой literal-записи выделяет управляющий CFG slice; unrelated reconverging conditions не попадают в результат.
- Раскрывает только уникальные dominating local definitions без address escape и competing stores. Сохраняет offsets чтений, defining store и `value_at_store`.
- Сохраняет opcode/taken edge, signedness и исходные арифметические операции. Не исполняет IL, calls или hooks и не вычисляет gameplay state в production.
- Ограничивает item-блок 1024 инструкциями, expression walk и сериализуемое дерево условия. Нет item/projectile-ID router или списка типов оружия.

Это расширение read-only source observations, не преобразование model-authored runtimeProgram и не синтез механики ребёнка.

## Реальный tML

Сертификаты и все baseline metadata не изменены. Семантический diff generated catalog содержит ровно две строки:

- Item4953, ItemCheck_Shoot: store10873 = projectile932 при `((Player.itemAnimationMax - Player.itemAnimation) / 2) == 2`. В условии сохранён снимок local135, store10599 и branch10866. PickAmmo rule1→932 остаётся отдельно. Prepare выдаёт `conditionally_replaced`, один полный профиль932 и оба source references.
- Item3859: literal710 внутри сложного item-блока теперь доказан как безусловный относительно входа в этот блок.

Условие4953 занимает 759 compact JSON-символов; whole-method IL и соседние trajectory calculations в prompt не добавляются. Сохраняется `finalShotOutcome=unknown_without_gameplay_execution`.

## RED → GREEN

- До исправления: 3 новых Python positive regressions failed, 9 negative controls passed. `python-red.log`.
- Настоящий C#/tML Prepare до regeneration: expected `conditionally_replaced`, actual `unknown_native_projectile_semantics`. `native-red.log`.
- После исправления: native ItemCheck_Shoot/NewProjectile oracle проверил 28 прежних weapon/ammo комбинаций и 24 новых state/ammo комбинации. Все 52 совпали. Есть elapsed=5 для проверки целочисленного деления и negative special-ammo paths. `native-green.log`.
- Native replacement profiles: 3/3 checks passed, включая точность полного canonical snapshot, обе ссылки на один profile, opaque hooks и deferred/cancelled capture. `native-profiles.log`.
- Final Python: 56 passed, включая оба Author response formats с настоящим Prepare export. Adjacent decoder/hit/attack tests: 51 passed. Итого 107 passed, без skips. Результаты в `python-final.log`, `python-neighbors.log`.
- Generated catalog freshness PASS; C# source policies PASS. `generator-check.log`, `csharp-policy.log`.
- Direct Roslyn compilation against actual tML references PASS; все C# source hashes совпадают с compile manifest. Это не утверждение о MSBuild release build.
- Independent review воспроизвёл два дефекта промежуточного решения (contradictory snapshot guards, item-header reentry), оба исправлены. Независимо повторены все 24 CFG tests; оставшихся soundness blockers в заявленном scope не найдено.

## Явные границы

- Arbitrary control-dependent calls, byref targets, address-exposed dependencies, неоднозначные defs, relevant cycles, malformed targets, EH и реальные неподдержанные outer guards не превращаются в положительный факт.
- Противоречивые literal equalities одного immutable snapshot отвергаются; полного SAT/SMT решения произвольных условий нет.
- Доказанный store не скрывает последующую opaque запись. Unknown bookkeeping остаётся per-store.
- Реальные remaining item-specific неизвестные записи: item3542/offset319 (computed projectile+1 под RNG guard) и item1157/offset16434 (RNG-selected projectile). Они не выданы за literal mappings.
- Новое offline vanilla CFG доказательство не применяется автоматически к произвольным mod hooks. Native profile tests подтверждают, что opaque hooks не исполняются и не получают выдуманных output IDs.
- Не проверены live game/GPU/network/multiplayer, complete RNG/trajectory/cadence или full integrated release suite. Эти результаты не объявляются releaseReady.

## Передача изменений

`conversion-analyzer.patch` — review patch против frozen restoration/outer-guard source; `changed-files.json` — 10 путей с base/current SHA256; `catalog-semantic-diff.json` — точные две строки; `summary.json` — binary hash/footprint. Fresh actual Prepare exports находятся в `native-packets/`.
