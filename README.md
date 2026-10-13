# Infinicraft

Соедини два предмета Terraria в **«Кузне чудес»** и получи новый предмет со своей механикой, описанием и рисунком. Мод работает в tModLoader; отдельный **LocalGenerator** обращается к выбранным тобой нейросетям.

## С чего начать

- **[START_HERE.html](START_HERE.html)** — руководство целиком. Открывается двойным щелчком в браузере, без установки программ и запуска сервера.
- **[OPEN_INFINICRAFT.bat](OPEN_INFINICRAFT.bat)** — приложение настроек и управления генератором для Windows.
- Читаешь на GitHub? Начни с **[установки и первого крафта](docs/user/START_RU.md)**.

Для игры скачай готовый **`InfiniCrafterLocal.tmod`** и архив **`Source_and_LocalGenerator.zip`** одного релиза из [официальных загрузок](https://github.com/Xipong/InfiniCrafterLocal/releases). Собрать мод из исходников не требуется. Текущая поставка — **[0.5.03](https://github.com/Xipong/InfiniCrafterLocal/releases/tag/v0.5.03)**; в tModLoader её номер может отображаться как `0.5.3`. Архив `InfiniCrafterLocal_0.5.03_Source_and_LocalGenerator.zip` включает Studio, `START_HERE.html` и всю документацию. Обновляй мод и генератор вместе: патч согласует имена до 80 Unicode-символов, расширяет описательные поля без скрытой обрезки и выделяет постоянную грамматику Visual/VFX в cacheable prefix. Реальный прирост cache hit/скорости после изменения ещё не измерен.

Игроку в одиночной игре или хозяину мира нужны stable tModLoader, ParticleLibrary, Luminance, Python 3.11+ с Tcl/Tk и выбранные сервисы текста и изображений. Другу, подключающемуся к хозяину, нужны только мод и игровые зависимости. Модели и аккаунты в поставку не входят; облачные запросы используют твои квоты или оплачиваются твоим провайдером.

## Нужен конкретный ответ

[Выбрать нейросети](docs/user/PROVIDERS_RU.md) · [Настройки и спрайты](docs/user/SETTINGS_RU.md) · [Ежедневный запуск](docs/user/OPERATIONS_RU.md) · [Игра с друзьями](docs/user/MULTIPLAYER_RU.md) · [Обновление](docs/user/UPDATING_RU.md) · [Решение проблем](docs/user/DIAGNOSTICS_RU.md) · [Команды чата](docs/user/COMMANDS_RU.md)

Меняешь код? [Сборка](docs/development/BUILD_RU.md), [правила проекта](AGENTS.md) и [участие в разработке](CONTRIBUTING.md). Пользовательская инструкция не требует проходить технические тесты.

**Лицензия:** [Source-Available License 1.0](LICENSE), [русский перевод](LICENSE_RU.md). Это не open-source лицензия. Вместо зеркала или репака делись ссылкой на оригинальные загрузки. Автор и сопровождающий — [Xipong](https://github.com/Xipong).