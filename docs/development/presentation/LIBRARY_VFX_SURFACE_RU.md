# Реальная поверхность библиотек Visual/VFX

Проверено 2026-10-30 по ParticleLibrary **3.2.1.0**, commit
`7b945efa780a4376ce5abaa8a284c06f159074f6` (SHA DLL совпал с manifest стенда),
и Luminance **1.0.11**, commit `5b4095a5d59e901ac171208f67a1d1e934c69373`
из informational version используемой DLL. [Ресурсы, SHA256 и размеры](../evidence/library-vfx-resources-2026-10-30.json).
Это проверка исходников/PNG и CPU-контракта, не просмотр результата в игре/GPU.

## Что действительно доступно модели

`libraryParticle` использует V3 instancing ParticleLibrary, но не произвольный
Behavior/Emitter и не генерируемый код. `particle.textureId` явно выбирает:

| ID | Реальный ресурс | Форма |
|---|---|---|
| `star` | ParticleLibrary/Assets/Textures/Star | Мягкое радиальное свечение 128×128, **не звёздочка** |
| `solidPixel` | ParticleLibrary/Assets/Textures/WhitePixel | Белый пиксель; authored width/height растягивают его в прямоугольник |
| `bloomCircle` | Luminance/Assets/GreyscaleTextures/BloomCircleSmall | Широкий мягкий круг света |
| `bloomFlare` | Luminance/Assets/GreyscaleTextures/BloomFlare | Многолучевая вспышка |
| `bloomLine` | Luminance/Assets/GreyscaleTextures/BloomLine | Узкая вертикальная световая полоса: длинная ось текстуры Y |
| `chromaticBurst` | Luminance/Assets/GreyscaleTextures/ChromaticBurst | Цветное спектральное кольцо, несмотря на папку Greyscale; RGB дополнительно умножает исходный цвет |
| `shineFlare` | Luminance/Assets/GreyscaleTextures/ShineFlare | Четырёхлучевая звезда по осям |

У всех перечисленных файлов alpha непрозрачная. Для свечений `additive` делает
чёрный фон невидимым; `alpha` **рисует чёрный прямоугольник**. Это явно доступный
выбор, не скрытая коррекция. Несколько крупных additive-масок могут засветить
кадр: никакой автоматической художественной компенсации здесь нет.

`particle.sampling` явно выбирает `point` (PointClamp, резкие texels) или
`linear` (LinearClamp, плавная интерполяция). Он не меняет размер/геометрию.
Fresh Director обязан выбрать; старые сохранения без поля сохраняют PointClamp.
Группы sampler отрисовываются раздельно с общим бюджетом и восстановлением
состояния GPU после каждой группы. Размеры частиц заданы world px независимо от разрешения PNG; движение, спин, цвет,
opacity, lifetime и бюджет остаются отдельными authored controls.

Старый `star` сохраняет имя, ресурс и оба режима blend. Никаких эвристических
переназначений по названию предмета. Выбранный путь фиксируется в immutable
snapshot. Четыре постоянных буфера (2 слоя × 2 blend) переиспользуются по текстурам;
каждая группа загружается и немедленно отрисовывается до смены texture binding.
Общий admission/instance/source-draw budget не перезапускается между группами.
Ресурсы загружаются лениво на graphics thread; отсутствие одного ресурса не
подменяется Star и не отключает уже готовые другие. Его emission ждёт ограниченное
время и завершается без изображения, с диагностикой точного пути.

## Чего здесь нет и почему

ParticleLibrary содержит generic buffers, пользовательские `Behavior<T>.Update`
и `Texture`, emitter infrastructure; большая часть текстур — UI, а GlowParticle и
ExampleParticle снова радиальные glow-маски. Это не скрытый каталог сотен готовых
красивых эффектов. Открывать произвольные C# поведения/регистрации модели нельзя.

Luminance дополнительно предоставляет primitive trails/circles, pixelation,
shader management, render targets, metaballs, particle infrastructure и camera
managers. Сейчас открыты точные PNG выше и native `ScreenShakeSystem` с явными
параметрами. Остальные API **не объявлены доступными**: им нужны самостоятельные
контракты владения, geometry/material inputs, lifecycle, budget и проверки,
а многие — callbacks, shader или global render target state. Их нельзя честно
назвать обычным alias lowering готового model-owned описания. Существующие
`shape`, `texturedPath`, `historyTrail` дают свои explicit bounded controls;
добавление библиотечного backend имеет смысл лишь при новой исполняемой
возможности, а не ради имени зависимости.

## Те же ресурсы как ингредиенты остальных renderers

`spriteElement`, `texturedPath` и `historyTrail` (`draw=sprites`) принимают
`texture: {"source":"library", "assetId":"shineFlare"}` — тот же зарегистрированный набор ID.
Это использует их существующие offset/attachment/lifetime profiles/history/UV,
не добавляя вторую систему профилей для instanced particles. Native selector
не требует `assets[]`, Image-вызова или готовности generated PNG.

`source` остаётся authority: snapshot хранит отдельный library ID. Обычный
item/entity/asset path, даже совпадающий строкой с ресурсом мода, **не становится**
native selector. Общий material native cache зависит только от зарегистрированного
ID и готовности graphics resources, не от включения ParticleLibrary backend или
его instancing shader. Недоступный выбранный ресурс не заменяется другой текстурой.

Sampler этих material renderers сохраняет прежнее поведение; новый
`particle.sampling` относится только к `libraryParticle`. `texturedPath` растягивает
U вдоль пути по существующему wire-контракту. BloomLine длинный по Y: автоматического
поворота UV нет. Opacity/blend не исправляют чёрный фон библиотеки автоматически.

## UV: переориентация рисунка без изменения геометрии

`texture.uv = {"quarterTurns":1,"mirrorU":false,"mirrorV":false}` — единый
контракт для spriteElement, texturedPath и sprite-ветки historyTrail.
Сначала отражаются sampling U/V, затем применяется четверть оборота:
0: `(u,v)`; 1: `(v,1-u)`; 2: `(1-u,1-v)`; 3: `(1-v,u)`.
Это формулы **координат выборки**, а не команда повернуть projectile/путь.

Модель выбирает переориентацию рисунка внутри прежнего world-прямоугольника;
его размеры, положение, исходный pivot/grip и история не меняются. При этом
нарисованный пиксель рукояти может переместиться: код не угадывает новый grip
по повернутому изображению. Существующий body flip применяется до authored UV.
Нечётные turns у прямоугольной текстуры не меняют размеры world quad.

У path сначала вычисляются существующие stretch/repeat/scroll UV, затем transform.
`PointWrap` остаётся wrap: значения вне 0..1 не обрезаются, и при нечётном turn
повторение переходит с texture U на texture V. Так BloomLine с длинной осью Y
можно явно направить вдоль пути. Ни новый PNG, ни shader, ни pixel-копия не нужны.
Свежий Director/Repair передаёт полный bundle даже для identity:
`{"quarterTurns":0,"mirrorU":false,"mirrorV":false}`. Это одинаково для
json_object и strict json_schema; nullable transport alias не используется.
Старый saved wire без bundle сохраняет точную identity и отсутствие поля;
явный null, неполный bundle и turns вне 0..3 не принимаются.

## Три различные фактуры, а не дубли библиотек

Общий selector дополнен тремя pinned Luminance noise-текстурами 512×512:

| ID | Ресурс в `Luminance/Assets/Noise/` | Рисунок |
|---|---|---|
| `branchingNoise` | `DendriticNoiseZoomedOut` | Ветвящиеся светлые прожилки вокруг тёмных ячеек |
| `turbulentNoise` | `TurbulentNoise` | Неоднородные облачные вихри, почти серый RGB |
| `blotchNoise` | `WavyBlotchNoise` | Мягкие округлые светлые/тёмные пятна |

Это **непрозрачные фактуры**, не готовые прозрачные облака/дым. Их можно
использовать существующим texture selector в spriteElement, texturedPath,
спрайтовом historyTrail и как libraryParticle: world-размер, UV и цвет
по-прежнему выбираются отдельно. Additive подавляет чёрный фон; alpha его
сохраняет. Никакой автоматической маски, erosion shader или новой анимации
за именем noise не скрывается. Статическая фактура движется только уже
явно выбранными UV/transform controls.

Оставлен один coarse dendritic ресурс, без второго близкого варианта масштаба.
Не добавлены Pixel из второй библиотеки или очередные GlowParticle: для них
уже есть canonical solidPixel и glow-ресурсы. Старые saved ID не переназначены.

## Отдельные оригинальные эффекты Terraria

`rendererKind=nativeEffect` — явно выбранный **готовый native рецепт**, а не
lowering универсальной формы. Payload `nativeEffect.type`:

| ID | Terraria recipe | Что видно / доступный input |
|---|---|---|
| `goldCrossBurst` | Excalibur | Золотистые осевые искры: 8 sparkles на 30 ticks + 8 Dust; без movement |
| `rainbowBurst` | RainbowRodHit | Радиальная многоцветная вспышка: 12 sparkles на 60 ticks + 24 Dust; обязательный movement |
| `darkLightningBurst` | BlackLightningHit | Короткие чёрно-индиговые анимированные разряды на 24 ticks; без movement |
| `shimmerStar` | ShimmerBlock | Одна случайно окрашенная звезда на 45 ticks с дрейфом/ускорением; обязательный movement |

`movement={"x":0,"y":0}` задаётся только для двух читающих его native recipes,
в world px/tick, каждая компонента −24..24. Он не наследуется от источника.
Это input stock-рецепта, не обещание скорости каждой частицы: rainbow burst
масштабирует/распределяет движение, shimmer star добавляет movement/45 как
ускорение каждый tick.
Позиция — зафиксированный anchor; эффект detached и может закончить native
lifetime уже после исчезновения источника. Цвет, размер, длительность,
over-player layer и части native motion принадлежат stock-коду. Поэтому
color/scale/duration/blend/layer/count здесь **не принимаются**, а не молча
игнорируются. Начало и cadence — существующие `startTick`/`repeatEvery`:
для события repeatEvery=0, для periodic ≥1; у item periodic startTick=0.

Резервирование целого burst: goldCrossBurst — 16, rainbowBurst — 36,
darkLightningBurst — 8 (консервативная граница native float-loop), shimmerStar — 1.
И maxParticlesPerTick, и maxParticlesTotal должны вмещать одну такую порцию:
несовместимый persisted budget отклоняется при admission, не молча увеличивается.
Compiler свежего manifest уже выдаёт минимум 56/2200 для одного slot.
Временная конкуренция с другими эффектами может подавить отдельный burst.
Один общий nativeEffect admission limit — 256 полных частиц за world tick
по всем источникам. Дополнительно реальные записи публичного Terraria
World_OverPlayers particle renderer учитываются вместе с IFC material/library
частицами в общем live bound 2048; для нового burst проверяются sprite-порции
8/12/8/1. Это read-only backpressure, не владение чужими эффектами: чужие
частицы не удаляются, чужой код может превысить границу своими вызовами,
но IFC при заполнении не добавляет новые. Native ParticlePool(200) — начальная
ёмкость, **не hard cap**, поэтому на неё защита не полагается.
Клиентская плотность частиц ниже 100% выбирает целые burst, не обрезает stock
рецепт; при 0% они отключены.
Весь burst должен поместиться в общий particle budget до вызова. Это не
«один вызов = одна частица» и не дробление stock-рецепта ради бюджета.
Нативные частицы обслуживает Terraria, не IFC detached draw-list; нет обещания
изменять их attachment/layer или досрочно отзывать уже переданные частицы.

Проверено по установленной tModLoader 1.4.4.9, SHA256
`fcc6a9624b12191be4a15d714a3675440911feb8c1d374642ab1fd686f0da0a5`:
выбранные четыре spawn-ветки и Update/Draw используемых native particles не
вызывают gameplay projectile spawn, damage, network или sound. Используется
только client-side `SpawnParticlesDirect`; Broadcast/Request не используются.
BlackLightning загружает texture projectile 916, **не создаёт projectile**.
Native Dust может давать освещение. Native randomness использует Main.rand,
это не slot-seeded собственная симуляция и не обещание изоляции игрового RNG.

Весь enum Orchestra намеренно не открыт: ItemTransfer вызывает
`Chest.AskForChestToEatItem`, некоторые другие рецепты включают звук,
зависят от игрока/его shader или дублируют имеющиеся sparkle-эффекты.
Ни имя предмета, ни DamageClass не выбирают recipe автоматически.
