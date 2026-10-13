# Сердце кузни — оформление 0.4.252

## Что изменено

- Оригинальная Calamity-like иконка: раскалённый кристалл в тёмной кованой оправе, золотые рёбра и корона-наковальня, холодные блики. Рисунок получен через Codex OAuth, не скопирован из Calamity assets.
- `Assets/InfiniCore.png`: RGBA atlas 48×1200, 24 различные фазы. Каждая ячейка 48×50 содержит 48×48 artwork и две пустые нижние строки: installed `DrawAnimationVertical.GetFrame` вычитает их из высоты кадра.
- `InfiniCore.SetStaticDefaults`: штатный `DrawAnimationVertical(5, 24)` плюс `AnimatesAsSoul`. Цикл иконки 120 ticks (2 секунды при 60/с), инвентарь и лежащий предмет.
- `InfiniCore.ModifyTooltips`: только `Terraria/ItemName` получает gradient color snippets, оттенки янтарь → золото → ледяной голубой, 4-секундный цикл по native UI clock `GlobalTimeWrappedHourly`.

## Неизменные границы

Plain локализованное имя Item/save/net, остальные tooltip-строки, рецепт, цена, редкость, hitbox, гравитация, расходование и игровые механики не меняются. Границы графем сохраняют Unicode/combining marks. Готовая foreign markup-строка не вкладывается в новые теги. Generated-предметы и их принятые названия/PNG не переавториваются. Нет нового shader/render pass или зависимости на Calamity.

LocalGenerator 0.4.252 содержит только обновлённую идентификацию версии относительно 0.4.251; генерация и настройки не менялись. Поставка парная; уже используемый генератор 0.4.251 совместим с этим cosmetic update. Сохрани личный config, profiles, cache, recipes/PNG и данные миров при обновлении.

## Проверка

`tools/EngineRuntimeChecks.ForgeHeart.cs` зарегистрирован в runner и explicit Compile roster. Native RED→GREEN подтверждены отдельно: отсутствующая atlas animation и отсутствующие name color tags. Принятая интеграция: 261 CPU/headless checks passed, 0 failed; normal Windows SDK build 0 warnings / 0 errors; package прочитан installed TmodFile и все 8 PNG→rawimg conversions совпали с canonical resources. Перед публикацией новой версии DLL/package пересобираются и bind к текущим release bytes; CI проверяет exact commit.

Нативный tooltip путь `ModifyTooltips → ChatManager.GetStringSize/DrawColorCodedStringWithShadow → ParseMessage` понимает RGB tags; сохранены RU/EN, графемы, описание, foreign-name controls и фазы 0/1/4. Atlas и decoded GIF имеют 24 уникальных кадра, неизменную alpha-маску/pivot и пустой padding. Независимые reviews обеих презентационных интеграций прошли.

Игра/world, GPU/font/layout и живой multiplayer не запускались. Представительное превью использует реальные native цвета, но другой шрифт; оно не является снимком Terraria.
