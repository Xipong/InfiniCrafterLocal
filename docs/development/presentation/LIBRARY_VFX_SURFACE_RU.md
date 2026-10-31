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
`texture: {"source":"library", "assetId":"shineFlare"}` — те же семь ID.
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
