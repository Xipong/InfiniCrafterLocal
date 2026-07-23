# Независимый аудит стабилизации prompt/runtime contract — snapshot `c82d168`

**Дата аудита:** 2026-07-23
**Входной архив:** `InfiniCrafterLocal_clean_source_with_git_c82d168.zip`
**Исходный HEAD:** `c82d16814b56ba62f008ddcd9e81a432e2aaf280`
**Ветка исправлений:** `audit/verify-contract-stabilization`
**Аудируемый отчёт:** `agent_reports/prompt_contract_stabilization_archaeology_20260723_RU.md`
**SHA-256 отчёта до правок:** `00278f53369a7dc6706e4cd03417556466c2a4420010ddbf666b74e8a25e74b1`

## 1. Вердикт

Архитектурное направление в основном правильное: typed function registry, отдельный final projection owner, bounded repair, Visual/VFX contracts и offline replay действительно существуют в коде. Это не выдуманная архитектура.

Но состояние `c82d168` нельзя считать полностью стабилизированным, а исходный отчёт нельзя считать целиком независимо verified. Обнаружены два воспроизводимых false-PASS seam, несколько переутверждений и одна группа устаревших source-of-truth указателей:

1. Author/provider принимал выдуманные finite VFX tokens, а compiler мог молча собрать из такого call частичный/default cue.
2. Historical replay возвращал пустую выборку для typed функций, которые понижаются в `shoot_projectile`; такой пустой прогон выглядел зелёным.
3. `allowed_result_kinds` был назван applicability metadata registry, но во всех production entries он пуст и не является owner текущей applicability policy.
4. Replay умел выбирать по функциям, но не имел отдельного selector по form; call-shapes использовались только при построении corpus.
5. Frozen function surface не фиксировал весь typed metadata: lowerer identity, wire/provenance attributes и полную param metadata.
6. Несколько agent maps продолжали направлять новые engine functions в `schema.py`, хотя реальный owner уже `function_contract_registry.py`.
7. Live/token/transport числа, `fa01d50` и часть заявленных local gates не воспроизводимы из переданного архива.

Исправления сделаны generic и fail-closed, без item-name hardcodes, новых LLM-ролей или повторного Live.

## 2. Граница доказательств

### 2.1. Что доказуемо из архива

- Git repository полный, `shallow=false`.
- В архиве есть closing commits:
  - `c45144768ec82607e7ac6b3eb92f91a467f40cbe` — `refactor: stabilize authored runtime contracts`;
  - `c82d16814b56ba62f008ddcd9e81a432e2aaf280` — `docs: correct architecture token cost framing`.
- Код typed registry, compiler/final projection, repair, Visual/VFX и replay присутствует и доступен для статического и offline исполнения.
- Production callers, найденные поиском, используют `final_projection.py` для final runtime projection; второго production owner тех же final sections в snapshot не найдено.
- Author domain pipeline выполняет один initial pass и не более одного same-author scoped repair. ID rename и param mutations сначала полностью проверяются, param changes относятся к старому callId owner, rename применяется после них.

### 2.2. Что отсутствует

В архиве нет `artifacts/tool-runs`, `summary.json`, `logical_llm.ndjson`, `prompt_trace.ndjson`, делегат-логов и Live ledger. Commit `fa01d50` также отсутствует в object database, хотя repository не shallow. Поэтому из этого входа нельзя независимо пересчитать или подтвердить:

- 81 Author-containing run, 20 fingerprints / 21 segment;
- ≈8.93–9.08M Gemini tokens и поминутную таблицу прогонов;
- Live20 20/20, 69 logical/HTTP requests, zero retries и 332,108 tokens;
- byte-for-byte pre/post-Live snapshot hashes;
- ≈100M/≈90M agent-token split — это явно owner-reported estimate, а не локальный ledger.

Эти утверждения не опровергнуты. Их статус — **historical report / external evidence unavailable**, а не independently verified данным архивом.

## 3. Воспроизводимые дефекты исходного `c82d168`

### 3.1. High: finite VFX contract был открыт для галлюцинаций

В исходном registry параметры `visual_effect_cue.rendererKind`, `channel` и `particleSystemId` были обычными strings. Provider validation принимал, например:

```text
rendererKind = hallucinatedRenderer
channel = imaginaryChannel
particleSystemId = pl:not-real
```

Direct compiler затем отбрасывал неизвестные отдельные поля, но мог оставить остальные и создать другой, частичный cue. Это противоречило утверждению о finite typed boundary и создавало именно тот класс ошибки, который архитектура должна была предотвращать: «LLM придумала token → schema приняла → compiler молча изменил смысл».

**Исправление:** Author и VFX Director теперь используют общие canonical tuples/sets для event, renderer, channel, lane, roles, emission, particle-system ID и importance. Provider schema закрыт enum-ами. Defensive compiler path делает весь `visual_effect_cue` inert, если любой явно supplied finite token неизвестен; он больше не проецирует частичный/default cue из невалидного call.

Дополнительно закрыты соседние finite поля `effect`, `onHit` и `armorSlot`, которые оставались shadow strings в части function cards.

### 3.2. High: affected replay мог дать ложный зелёный результат

Typed Author calls (`fire_ranged_weapon`, `cast_magic_weapon`, `perform_melee_attack`, `deploy_sentry`, `spawn_temporary_helper_projectile`) понижаются в canonical `shoot_projectile`. Frozen v1 corpus хранит только уже normalized calls. Исходный selector искал literal changed function в normalized plan:

```text
select_cases_by_changed_functions(corpus, ["fire_ranged_weapon"]) -> 0 cases
```

Пустая выборка не считалась ошибкой. Следовательно, заявленный workflow «changed function → affected replay» мог не проверить ничего.

**Исправление:** registry получил immutable `lowered_function_names`; replay различает authored и normalized function inventory. Новый corpus builder сохраняет `_rawFn`/`authoredFn` отдельно от executable plan. Для provenance-aware corpus typed function выбирается точно. Для legacy corpus без authored provenance selector консервативно выбирает canonical lowerer cases; `fire_ranged_weapon` в текущем frozen corpus выбирает 68 `shoot_projectile` cases. Unknown и uncovered functions fail-closed вместо пустого PASS.

Ограничение сохранено честно: legacy mapping широкая и не доказывает exact typed-family coverage. Следующий corpus следует пересобрать из dumps, сохраняющих raw typed provenance.

Дифференциальные probes на detached `c82d168` и audit tree:

| Probe | `c82d168` | После исправления |
|---|---:|---:|
| provider принимает hallucinated VFX triple | `true`, 0 errors | `false`, 3 errors |
| compiler создаёт cue из того же invalid call | partial cue | cue отсутствует |
| replay cases для `fire_ranged_weapon` | 0 | 68 conservative legacy cases |

### 3.3. Medium: applicability metadata не была активным owner

`EngineFunctionContract.allowed_result_kinds` существует, но все 25 entries оставляют его пустым. Production applicability продолжает жить в `reports.py` и runtime-family policy. Исходный отчёт называл registry владельцем applicability metadata без этой оговорки.

**Исправление:** docstrings, architecture maps и отчёт теперь явно называют поле reserved metadata и указывают реального текущего owner. Семантика applicability намеренно не переносилась в этом audit commit: это отдельная migration с высоким blast radius.

### 3.4. Medium: frozen surface был неполным

Исходный fixture фиксировал catalog/provider/accepted params/repair groups, но не полный immutable typed contract. Изменение `wire_obligation`, `compiled_fields`, `prompt_group`, `function_card_visible`, nested wire paths или lowerer identity могло не дать ожидаемого frozen diff.

**Исправление:** fixture теперь содержит `typedContracts` с полной per-function/per-param metadata и lowerer mapping.

### 3.5. Medium: source-of-truth документация могла вернуть старую архитектуру

`.agent/manifest.json`, `AGENT_INDEX_RU.md`, architecture/folder maps и capability guide местами указывали `schema.py` как место добавления engine function. После миграции это неверно и могло снова создать shadow contract.

**Исправление:** function inventory/provider/prompt/wire/repair/lowerer направлены в `function_contract_registry.py`; `schema.py` оставлен owner family/affordance, numeric и cross-param policy.

## 4. Что в исходном отчёте было корректно

По коду подтверждены следующие архитектурные тезисы:

- pipeline не был расширен judge/router ролями;
- typed immutable function registry и provider/prompt projections реально существуют;
- `final_projection.py` используется production orchestration как owner final runtime sections;
- bounded same-author repair отделён от main orchestration и fail-closed по scope;
- Visual role registry и strict structured schemas существуют;
- offline corpus replay действительно выполняет production compiler/final projection без LLM;
- пост-Live fixes, описанные для executable use effect, `mode=none`, summon body и VFX event reachability, присутствуют в snapshot.

Поэтому правильный диагноз — не «модель всё выдумала», а **правильная основная миграция с несколькими реальными false-PASS seam и слишком сильной доказательной формулировкой отчёта**.

## 5. Исправления в audit branch

- canonical VFX vocabulary вынесен в один executable owner и переиспользуется Author schema, compiler, VFX Director, manifest/lint/runtime slots;
- prompt prose для particle-system IDs также строится из canonical vocabulary;
- unknown finite VFX token отклоняется provider boundary и не может стать partial cue при direct compiler bypass;
- closed enums добавлены для executor effect/onHit, sentry-safe onHit и armor slot;
- typed lowerer identity добавлена в immutable function registry;
- affected replay стал provenance-aware, legacy-conservative и fail-closed;
- corpus builder сохраняет authored function inventory отдельно, не пропуская internal keys в executable plan;
- frozen contract surface расширен полной typed metadata;
- agent maps и extension guide исправлены на фактического owner;
- исходный archaeology report получил provenance/verification corrections и ссылку на этот аудит.

## 6. Выполненная проверка после исправлений

### 6.1. Portable sandbox

`tools/validate_sandbox.py`:

- `ok=true`;
- syntax/JSON: 282 Python, 13 JSON;
- config registry: PASS;
- C# contract scanner: PASS;
- project hygiene: PASS;
- `releaseReady=false`, потому что в окружении нет Hypothesis.

Согласно repository policy полный pytest в таком sandbox повторно не запускался.

### 6.2. Детерминированные gates

- compileall: PASS;
- schema export: 5/5 current;
- config registry: PASS;
- contract parity: PASS;
- C# delivery contract: PASS;
- mutation gate: PASS;
- semantic runtime baseline: 10 cases, 0 differences;
- runtime impact: PASS;
- C# contract scanner: PASS;
- project hygiene: PASS;
- Planner prompt: 26,988 / 27,000, 25 functions, no problems/warnings.

### 6.3. Точечные regressions без pytest harness

- registry validation errors: 0;
- 9 finite VFX fields проверены на provider rejection и defensive compiler inertness;
- legacy typed lowerer selection: 68 cases вместо 0;
- full committed replay corpus: 82 cases, 0 fingerprint failures.

## 7. Невыполненные проверки и остаточные границы

- Новый Gemini Live не запускался: отдельного разрешения пользователя не было.
- Полный `pytest`/255, Ruff, Pyright и tML Debug/Release не воспроизведены в этом контейнере. В нём отсутствуют Hypothesis, Ruff/Pyright tools и исходный внешний build/Live harness.
- Числа разделов 1–10 и Live ledger не пересчитаны из первичных артефактов, потому что их нет в архиве.
- Applicability пока остаётся отдельной policy surface, а не полностью derived registry field.
- Frozen v1 replay corpus не содержит authored provenance; точность выбора typed lowerers будет доказана только после пересборки corpus из подходящих historical dumps.
- Отдельного form selector нет; call-shape coverage используется builder-ом, но affected API выбирает по changed functions.

## 8. Итог

После audit fixes архитектура заметно ближе к заявленной цели change locality и перестала давать два конкретных ложных PASS. Тем не менее корректная формулировка статуса — **offline deterministic contract candidate**, а не безусловно Live-confirmed/release-ready tree в данном окружении. Следующее сильное доказательство — provenance-aware corpus rebuild и один разрешённый acceptance Live после полноценного dependency/build gate, а не новый цикл глобальной рестабилизации.
