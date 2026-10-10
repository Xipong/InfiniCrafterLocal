# Явный рост игровой области столкновения

Категория A12 исторического аудита. Это новое явное runtime правило, восстанавливающее
потерянную динамическую collision expressivity. Оно не является alias прежнего
`move_expanding_wave`: этот movement продолжает менять только sprite scale.

## Контракт

`set_projectile_hitbox_curve` применяется к явно выбранному projectile entity и
создаёт optional `runtimeProgram.entities[].hitboxCurve`. Все шесть параметров
обязательны при наличии capability:

| Параметр | Область | Значение |
|---|---|---|
| startScale | 0.25…8 | Множитель исходного gameplay hitbox до начала кривой |
| endScale | 0.25…8 | Множитель после окончания кривой |
| startDelayTicks | 0…21600 | Задержка начала кривой в active world ticks |
| durationTicks | 1…21600 | Продолжительность перехода |
| curve | linear / exponential | Линейный или геометрический переход |
| mirrorToSprite | boolean | Явно показать ту же кривую на базовом спрайте |

Например, `startScale=1`, `endScale=4`, `startDelayTicks=5`, `durationTicks=60`,
`curve=exponential`, `mirrorToSprite=false` удерживает исходный размер первые
пять active ticks, затем увеличивает его вдвое к tick35 и вчетверо к tick65.
Существующий статический `set_projectile_hitbox.hitboxScale` остаётся независимым
базовым множителем. Модель может явно задать и уменьшение размера.

Для active age `a` в world ticks используется
`t=clamp((a-startDelayTicks)/durationTicks,0,1)`. Линейная кривая равна
`startScale+(endScale-startScale)*t`; экспоненциальная —
`startScale*(endScale/startScale)^t`.

Native `ModifyDamageHitbox` умножает обе стороны существующего damage rectangle
на static hitboxScale и значение кривой, округляет тем же прежним MathF.Round,
сохраняет центр и нижнюю границу 2px. В самых больших допустимых настройках
сторона ограничена 192×3×8=4608px. Это authored gameplay choice с явными bounds.
Сам `Projectile.width/height` и tile-collision box не раздуваются: capability
управляет damage contact rectangle, а не прохождением через тайлы.

## Clock, multiplayer и визуальное представление

Кривая вычисляется непосредственно из `_age/(extraUpdates+1)`. Нет отдельного
накапливаемого scale state, RNG или нового бюджета. Изменение extraUpdates
увеличивает частоту отсчётов, не сокращает authored duration. `_age` не растёт
во время существующей spawn activation delay. Network hydration использует
прежний синхронизируемый active age и заново вычисляет тот же множитель.

`mirrorToSprite=false` не трогает visual scale. Видимый рост можно авторить
независимо прежним movement или последующими отдельными visual modifiers.
`mirrorToSprite=true` задаёт `drawScale * visual.scale * curveScale` для спрайта.
Этот полный product доходит до actual PNG/reuse renderer без прежнего clamp
`Projectile.scale` к 0.1…8. Допустимый product 0.015625…128 сохраняется и при
наличии явного `renderSizePx`: перевод размера полного PNG frame применяется
после него ровно один раз. У обычного `runtime_geometry` те же authored
multiplier определяют длину/толщину без старых minimum 8px/2px/1px и без
отсечения положительных сегментов короче 0.1px. Нулевые, отрицательные или
нечисловые physical extents отвергаются на конечной границе DrawLine.
При отсутствии curve либо `mirrorToSprite=false` остаются прежние visual
clamps/floors. `no_asset` по-прежнему не рисует body; mirror не создаёт asset.
VFX body-copy slots имеют собственные опубликованные scale rules: mirror
базового body не переопределяет их slot scale или legacy copy clamps.
Gameplay всегда берёт кривую и static hitboxScale, никогда `Projectile.scale`,
PNG dimensions или VFX artist scale. Поэтому замена визуального представления
не меняет damage geometry.

Оба Visual Director/Repair packets получают exact accepted `hitboxCurve`
read-only и формулу соответствующего body режима. Отсутствие поля сохраняется;
Visual не может добавить curve, поменять её endpoints или выбрать mirror.
Тот же accepted object передаётся image backend: в facts отдельного baked body
и в `sharedEntityMultipliers` root PNG для каждого `reuse_item_icon` consumer.
Reuse не создаёт дополнительного image job; старое отсутствие остаётся отсутствием.

Beam и whip имеют специальные line-collision owners, поэтому их сочетание с
этой **прямоугольной** кривой отклоняется в Author и strict wire/C# DTO. Длины и
толщины этих линий остаются их собственными решениями. Mirrored curve также
не может одновременно владеть sprite scale с `move_expanding_wave`: нужно явно
отключить mirror либо удалить/заменить один из конфликтующих calls.

## Admission, receipts и Repair

Registry содержит exact params, units, source/consumer ownership и composition
requirements. Compiler пишет каждый leaf с отдельным receipt в точный entity
path. При наличии provenance strict wire требует ровно один receipt для каждого
present curve leaf; injection нового component без его receipts отвергается.
Обычный wire-only DTO без runtimeContract остаётся допустимым delivery форматом.

Present null/partial/unknown object, нечисло, boolean вместо числа, NaN/Infinity,
неизвестная curve и выход за bounds отвергаются. C# optional container не
материализуется при отсутствии, его поля используют JsonRequired и проверки
диапазонов с отказом без clamp. Старые документы без новой capability сохраняют
точный gameplay/runtime payload.

Repair отсутствующего/ошибочного scalar меняет только этот leaf; соседние
endpoints, время, curve и mirror остаются frozen. Для конфликта mirror разрешено
исправление именно mirrorToSprite. Удаление либо замена конфликтующего call
остаётся явным выбором Repair; код не выбирает нужный дизайн самостоятельно.

## Доказательства и проверка

Историческое основание: `3a0569a` добавил collision growth;
`f04ee02:GeneratedProjectile.Impact.cs:85–100` использовал отношение текущего
scale к исходному, а `Runtime.cs:939–943` наращивал scale. После `25caddf`
сохранился visual movement, но пропала эта collision ветвь. Новый контракт
восстанавливает явную игровую зависимость без связи с произвольным VFX scale.

`test_hitbox_curve_contract.py` проверяет полный Author/compiler/strict-wire/
receipt/Repair путь, numeric native-range parity и восемь frozen gameplay
fingerprints, снятых до изменения. Counter metadata о числе registry
requirements не является gameplay payload.

Пять EngineRuntimeChecks используют настоящий `ModifyDamageHitbox`, production
curve math, host/DTO и hydration: linear/exponential midpoints, рост и уменьшение,
extraUpdates1/3/6, неизменный центр, независимость от sprite scale, явный mirror,
проверки partial/null/malformed JSON. Они добавлены в штатный native harness.
Два consumer checks наблюдают настоящие FNA SpriteBatch CPU vertices после
`DrawAuthoredEntityVisual`/`DrawRuntimeGeometry`: PNG и reuse, с/без frame size,
product 0.015625/12/128, сохранённый absent/independent режим и generic segment
0.0625px. Только GPU flush перехвачен; это не имитация формулы renderer.
Portable source mutations отдельно доказывают чувствительность к возврату
каждого clamp/floor и потере optional exact-width policy.

Native C# build, исполнение EngineRuntimeChecks и игровой SP/MP smoke здесь
**notRun**: среда не содержит dotnet/tModLoader/dependency assemblies. Portable
source/contract checks не выдаются за игровой эксперимент. При review нужно
дополнительно проверить реальный contact damage на нескольких возрастах, tile
collision и отображение удалённого projectile после позднего подключения.
