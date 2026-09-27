# Простое развитие presentation — принятые решения

База: `49d1ead6e6e67a20849bee5a0c31daa508e57441`. Поручение владельца после предыдущего отчёта: **«Сделай по своему усмотрению без переусложнений»**.

Это отдельное согласованное развитие визуального контракта, не попытка назвать новые художественные решения lossless bugfix.

## Границы решения

- Остаётся существующий **Dust/FNA** runtime. Нет нового backend, shader framework, оружейных presets, classifier или дополнительных LLM-проходов.
- Имена существующих VFX получают реальные разные формы: волна, дуга, пульс, орбита и след геометрического кончика. Используются уже существующие параметры и bounded draw budgets. Event-представление — ограниченный по времени снимок/эффект в существующей detached очереди, а не новый самостоятельный движок.
- Для нового оформления Visual Director может явно задать один **effectColor** из существующего конечного runtime vocabulary. Он общий для VFX предмета, projectile и detached effects. Богатая текстовая palette не парсится как цвет. Отсутствие нового поля сохраняет прежние color paths старых предметов; отдельной migration нет.
- Grip задаётся одним атомарным объектом координат, а не двумя созависимыми optional полями. Его отсутствие сохраняет прежнюю совместимость; неверный присутствующий объект не превращается в угаданную точку.
- Броня остаётся single-PNG overlay с правильной привязкой. Аксессуарам доступны явные простые body mounts. Полный armor atlas, skeletal deformation и распознавание типа предмета по картинке не вводятся.
- Item/equipment сохраняют жёсткую pixel alpha; impact/effect изображения сохраняют мягкую прозрачность. PNG остаётся straight RGBA, premultiplication принадлежит уже исправленной runtime-загрузке.
- Техническая processing role отделяется от произвольного entity ID. Поворот asset convention обязан совпадать с реальным renderer; +X canonicalization не включается поверх native +Y rotation вслепую.
- Item hit/crit используют зафиксированную позицию цели в presentation relay. Защита транспорта остаётся ограниченной, но соседние типы событий не гасят друг друга одним cooldown.
- Particle budget: общий per-source per-tick cap; для разового события — дополнительный лимит этого события. Непрерывный periodic не получает бессрочный общий счётчик, который навсегда выключает предмет.
- Runtime geometry для уже выбранных ChannelBeam/whip использует те же точки/ширину, что collision. Это отображение существующей механики, не изменение hitbox/range или выбор механики по названию.

## Итог 0.4.242

- `grip`, `accessoryMount`, `effectColor`: точный контракт, координаты, null/Repair и пути хранения описаны в [VISUAL_PRESENTATION_METADATA.md](VISUAL_PRESENTATION_METADATA.md). Координаты grip передаются в реальный image request как техническая подсказка, без угадывания точки по имени предмета.
- Волна, кольца, орбита, дуга и tip history исполняются реальными FNA primitives. Геометрические размеры и смысл scale/density/duration/repeatEvery передаются в фактические запросы VFX Director/Repair; backend/particle hints больше не обещают неиспользуемый движок.
- Projectile event afterimage фиксирует rotation, flip, gfx offset и `clamp(projectile.scale,0.1,8) * slot.Scale`. Dedicated impact сохраняет прежнюю directional convention. Item event stamp — направленный снимок текстуры, не копия позы игрока.
- Projectile relay v3 передаёт неизменяемые event-time center/tip/forward/owner center и sprite pose. Удаление или перемещение исходного projectile не меняет снимок; отсутствующий owner не заменяется self. Item relay v3 передаёт захваченную hit/crit позицию. Старые v2-пакеты отвергаются, migration нет: все участники должны обновить мод.
- Новые item primitives без `effectColor` используют тот же исторический palette-color, что и сопровождающая Dust. Явный `effectColor` имеет приоритет. Неверные координаты отсеиваются до emission/создания исходящего item packet; мировая точка `(0,0)` остаётся допустимой.
- Item события делят tick-budget, но не гасят соседние use/hit/crit одним cooldown. Положительный total относится к одному событию, а не бессрочной жизни предмета; явный нулевой budget сохраняется.

## Проверено

- Полный Python suite: **1510 passed**; Ruff и Pyright — без ошибок.
- Canonical headless C# runner: **101 passed, 0 failed**, с расширенными FNA vertex/UV, реальными CPU Dust/Lighting, DTO/save/registry и encoder→decoder→detached проверками. Тесты охватывают неизменяемый snapshot после мутации/удаления источника и malformed packets.
- Release DLL: **0 warnings, 0 errors**, реальные tML **2026.6.3.6** / FNA и установленные зависимости.
- Все 12 проверочных команд из итогового прохода успешны, включая 8 CI-control-flow regression tests; отдельно экспортированы и сверены 10 generated contract artifacts.
- Независимые ревью metadata/alpha/roles и event/geometry. Подтверждённые замечания по pose, relay anchors, item legacy-color и finite coordinates закрыты regression checks, а не только исправлением текста.
- Offline preview: 7 renderer kinds × 2 blend modes × 12 кадров. Захватываются реальные FNA CPU vertices/RGBA; Pillow только растеризует их. Цвет задан явным `effectColor`, без подкраски результата. Soft-alpha sheet получен реальным Pillow pipeline из синтетического input.

## Граница доказательств и выпуск

Это не GPU/game-loop или двухклиентный MP smoke: игру и модели не запускали. Физическое совпадение нарисованной нейросетью рукояти с authored grip, художественное качество новых генераций и вид в реальном мире не доказаны. Soft alpha сохраняет существующее покрытие, но не восстанавливает произвольную прозрачность, уже сплющенную на непрозрачный фон.

`.tmod` упаковывается отдельно из exact-head Release DLL с allowlist assets/localization; без source/config/PDB/dependency DLL и без изменения игровой установки/`enabled.json`. Точный commit, hashes, проверка архива и статус GitHub CI фиксируются в release `VERIFICATION.json`. Hosted CI с пропуском отсутствующих tML DLL не считается реальной компиляцией; приведённая выше DLL-сборка локальная.

Полные armor atlases, новый shader/backend, skeletal animation, автоматический выбор механики и дополнительные LLM-проходы не вводились. Обновлять генератор следует из той же версии репозитория, что и мод.
