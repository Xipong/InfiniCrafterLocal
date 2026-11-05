# Восстановление родителей по ключу рецепта

`GeneratedItemRegistryService.LoadLocalCache` сначала читает точные сохранённые
identity из определений, исторических карточек и `atlas_lineage`. Если их нет,
`RecipeParentIdentityProof` может доказать пару родителей по сохранённому ключу.
Это **Fix** технической metadata, не выбор дизайна или игровой механики.

## Доказательство и отображение

- Только принятые полные определения текущего мира и текущие native samples
  участвуют в поиске. Другие миры, reference-only и отклонённые runtime items
  не раскрываются и не становятся кандидатами.
- Имена только сужают поиск. Они не доказывают identity или исторический порядок.
- Нужна единственная неупорядоченная пара с точным сохранённым `recipeKey`:
  SHA-256, усечённый до 24 hex, от отсортированной пары, `world:<id>` и версии
  `recipe_v4_25_no_item_family_routing`, с исходным Python JSON framing.
- При двух потерянных identity пара остаётся несериализуемой Atlas projection
  на существующем `GeneratedItemData`. Атлас показывает согласованные подписи
  и иконки в детерминированном порядке, но старые `ParentA`, `ParentB` и
  `ParentIdentities` не переписываются. Никаких предупреждений про порядок
  пользователю не нужно: рецепт коммутативен.
- Только уже сохранённый exact-slot anchor или одинаковые ингредиенты A=A
  позволяют заполнить позиционные поля. Противоречащее сохранённое свидетельство
  остаётся основанием не изменять metadata.
- Новый реестр и wire/save schema не создаются. Уже существующий ParentMetadata
  переносит тот же transient proof при повторной регистрации той же записи.
  Proof отсутствует в network/local JSON, проверяется по result ID, миру и key.
- Непустые identity, gameplay, visuals и сохранённая generationDepth не меняются.
  Глубину вычисляет граф; циклы, multiplicity и unknown boundaries сохранены.

## Бюджеты и audit

Работа выполняется только при загрузке registry, не в кадре. Индекс содержит
лишь нужные captions. Пределы: 2048 targets, 16 кандидатов/caption, 64 пары/target,
4096 hash checks и 512 receipts на загрузку. Поиск уникальности требует бюджета
на всё множество кандидатов. Receipt capacity резервируется до изменения:

- `fix:restore_recipe_hash_proven_parent_set:<id>` для transient Atlas view;
- `fix:restore_recipe_hash_proven_parent_identity:<id>:<slot>` для exact slot;
- прежние exact-source repairs также не меняют слот без доступного receipt.

Обычная повторная регистрация definition переносит уже принятую exact metadata
из сохранённого snapshot независимо от этого бюджета: это не новое восстановление.
Иначе исчерпанный audit мог бы стереть известную связь при сетевой гидратации.
Проверки того же мира, результата, рецепта и отсутствия конфликтов сохраняются.

Ни частичный поиск, ни первые N совпадений не считаются доказательством.

## Ограничения и проверки

Поддержана ASCII-грамматика identity, где Python/C# JSON побайтно совпадают.
Другая версия, multi-dev key, сменившийся numeric ID, язык или отсутствующий
кандидат могут оставить связь неизвестной. Не выдумываются моды и предки.
Неперсистентная projection не передаётся другому клиенту как историческая истина;
его ранее отсутствовавшие данные по-прежнему могут остаться неизвестными.

Native checks `lineage hash proof` проверяют canonical Python hash, swapped
captions, native icon/caption parity, конфликты, foreign worlds, reload,
re-registration, сохранение network/local JSON, audit exhaustion, циклы и
20 000-record budget. Это CPU/headless проверки, не FPS/GPU/MP игровой матч.
