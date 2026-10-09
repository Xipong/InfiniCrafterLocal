# Вклад в InfiniCrafterLocal / Contributing

**Предпочтительный путь улучшений — Pull Request в
[оригинальный репозиторий](https://github.com/Xipong/InfiniCrafterLocal).**
Рабочий форк для PR разрешён. Предпочтение PR не обязывает публиковать личные
изменения и не обещает принятия предложения.

## Как подготовить PR

1. Для значительного изменения сначала открой issue с задачей и предлагаемой
   границей. Небольшое исправление можно отправить непосредственно PR.
2. Прочитай [AGENTS.md](AGENTS.md) и [архитектуру](PROJECT_ARCHITECTURE_RU.md).
   Gameplay-решения принадлежат модели; не добавляй semantic/name routers,
   weapon presets, скрытые fallback или переавторство сохранённых рецептов.
3. Делай узкий diff: опиши исходную проблему, изменение и реально выполненные
   проверки. Команды — [AGENTS.md](AGENTS.md#обязательный-vertical-slice),
   сборка — [BUILD_QOL_RU.md](BUILD_QOL_RU.md). Не объявляй offline checks
   доказательством world/GPU/MP или live-модели.
4. Не включай личные config.env, OAuth/API credentials, cache, модели и saves.
   Новые сторонние материалы обозначь вместе с оригинальной лицензией.
5. Отправь PR в `main` оригинального репозитория. Авторство сохраняется;
   сознательно отправляемый вклад предоставляется по [LICENSE](LICENSE),
   если не согласованы другие условия.

## Форки, релизы и распространение

Юридически определяющий текст — [LICENSE](LICENSE),
[русский перевод](LICENSE_RU.md). Это source-available, а не open-source лицензия;
она распространяется на все версии оригинального проекта, кроме отдельно
лицензированных материалов, и сохраняет ранее правомерно предоставленные права.

- Пользоваться, изучать, менять для себя и готовить PR можно.
- Оригинальные файлы распространяются через официальный источник: делись
  ссылкой на [Releases](https://github.com/Xipong/InfiniCrafterLocal/releases),
  а не зеркалом, репаком или копией в модпаке.
- Самостоятельные переиздания без существенных функциональных/архитектурных
  изменений запрещены. Переименование, косметика, перевод и перепаковка сами
  по себе не дают разрешения выпустить «свою версию».
- Существенный самостоятельный производный проект разрешён только по разделу 4
  LICENSE: отдельное имя, явная неофициальность, исходный commit/version,
  ссылка на оригинал, конкретное описание изменений, лицензия/авторство и
  соответствующие изменённые исходники.
- Права штатной GitHub-функции Fork сохраняются; рабочий форк не означает
  разрешения создать альтернативный download/release channel.
- Исключения выдаёт Xipong явно и письменно через официальный issue/discussion.

## English summary

The license covers all versions of the original project, except separately
licensed material and permissions already validly granted under other terms.
Pull requests to the upstream `main` branch are preferred. Private modifications
and working forks for contributions are permitted. Link to official downloads
instead of mirroring or repacking original files. Independent distributions with
only trivial/cosmetic changes are prohibited; substantial independent derivatives
must satisfy all of section 4 of LICENSE. Contributions retain their authorship
and are submitted under the repository license unless separately agreed.
