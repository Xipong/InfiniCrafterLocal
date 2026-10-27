# Экспериментальный стенд в настоящем процессе tModLoader

Это отдельный прототип, не замена существующему CPU/графическому стенду. tModLoader загружает переданные `.tmod` и их зависимости обычным способом; `IFCWorkbenchDriver` — отдельный тестовый мод, который задаёт сцену и наблюдает хуки. Он не перечисляет хуки IFC или других модов и не вызывает вручную их обновления. Отсутствующий мод или неподдержанный сценарий не считаются успешным тестом.

**Проверено:** компиляция и упаковка модов, тесты Python-подготовки. **Не проверено:** запуск этого драйвера в игровом процессе, оба сценария fixture и создание клиентской сцены. Поэтому результат сборки не означает, что клиентский или серверный прогон уже работает на данной установке.

## Режимы и границы

- `projectile` запускается на dedicated server. В изолированном мире создаются указанные модовые NPC и снаряд через стандартные API; дальнейший бой выполняется штатными игровыми обновлениями. Владелец снаряда в dedicated server — служебный игрок 255; этот режим не проверяет использование предмета, хуки реального владельца или поведение, требующее живого игрока. Засчитывается только попадание исходного снаряда с проверенными slot/identity/owner, не его потомков.
- `item_use` предназначен для настоящего локального клиента. `ModPlayer.SetControls` задаёт удержание primary или alt, а движение игры и хуки выполняет tModLoader. Предмет разрешается по `ModName/ContentName`; снаряды учитываются только при наблюдаемом источнике от этого предмета или от уже отслеженного снаряда. Автоматический запуск клиента и вход в мир **пока не реализованы**: `--mode client --prepare-only` создаёт конфигурацию для ручного запуска клиента в отдельном каталоге.
- `IFCWorkbenchIFCAdapter` — необязательный дополнительный мод с зависимостью от IFC. Для сгенерированного предмета он вызывает штатный `GeneratedItemData.FromJson` либо `FromLocalCacheJson`, затем зарегистрированный `GeneratedItem.SetData`. Он не регистрирует и не вызывает игровые хуки. JSON предмета передаётся объектом `itemData` в сценарии; сторонние пути и неподходящая привязка к миру не исправляются молча.
- Для ванильных NPC, предметов и снарядов используйте точное имя `Terraria/IDName` или числовой `Terraria/123`. Содержимое сторонних модов задаётся как `ModName/ContentName` и разрешается через `ModContent`; имя не выбирает механики.
- `status=passed` означает только завершение указанных тиков с `hits >= minHits` и `totalDamage >= minDamage`. Это не подтверждает визуал, баланс, сетевую синхронизацию или полное поведение предмета. Проверяйте также trace и независимый отчёт fixture. `failed`, `error` и отсутствие отчёта не являются PASS.

## Сборка трёх тестовых модов

Нужны .NET, совместимый tModLoader, его SDK и ссылки на те же версии зависимостей, с которыми собран IFC. Исходники модов:

```text
tools/item-test-workbench/tmod-driver/IFCWorkbenchDriver
tools/item-test-workbench/tmod-driver/IFCWorkbenchIFCAdapter
tools/item-test-workbench/fixtures/WorkbenchObserverFixture
```

Соберите соответствующие `.csproj`; для адаптера укажите реальную сборку IFC через `INFINI_IFC_DLL` или `-p:InfiniCrafterDll=...`. Затем используйте официальный tML packager с отдельной временной папкой сохранений, для каждого мода подставив его каталог исходников и собранную DLL:

```bash
dotnet build ПУТЬ_К_МОДУ/ИМЯ_МОДА.csproj -c Release -p:TmlBuildMod=false
cd ПУТЬ_К_УСТАНОВКЕ_TMODLOADER
dotnet tModLoader.dll -server -nosteam -tmlsavedirectory ВРЕМЕННЫЙ_КАТАЛОГ \
  -build ПУТЬ_К_МОДУ -eac ПУТЬ_К_СОБРАННОЙ_DLL
```

Для адаптера повторите `dotnet build` с `-p:InfiniCrafterDll=ПУТЬ_К_InfiniCrafterLocal.dll`. Каждый исходный каталог должен иметь своё внутреннее имя: `IFCWorkbenchDriver`, `IFCWorkbenchIFCAdapter`, `WorkbenchObserverFixture`. Пакеты в `ВРЕМЕННЫЙ_КАТАЛОГ/Mods` должны быть из той же версии tML, что и установка для прогона. При тесте IFC также нужны его `.tmod` и все реальные зависимости, в том числе ParticleLibrary и Luminance; launcher не скачивает их и не добавляет их автоматически.

## Изолированная подготовка и серверный прогон

Из корня репозитория, подставив абсолютные пути:

```bash
python tools/item-test-workbench/tmod-driver/runner.py \
  --tml-dir /path/to/tModLoader \
  --scenario tools/item-test-workbench/fixtures/WorkbenchObserverFixture/projectile-scene.json \
  --mod IFCWorkbenchDriver=/path/to/IFCWorkbenchDriver.tmod \
  --mod WorkbenchObserverFixture=/path/to/WorkbenchObserverFixture.tmod \
  --extra-output IFC_WORKBENCH_OBSERVER_OUTPUT=observer.json \
  --prepare-only
```

`--prepare-only` не запускает игру. Для настоящего серверного прогона вместо него явно укажите `--run`. Launcher создаёт новый случайный каталог, копирует в него только перечисленные пакеты, задаёт отдельные save/mod/world/workshop пути, loopback и отключение UPnP, ждёт результат и останавливает процесс. Пути sandbox, отчёта и лога выводятся при подготовке. Установка tModLoader и исходные `.tmod` не изменяются launcher'ом.

Чтобы сохранить `worldId` для предмета, созданного в существующем мире, можно явно добавить `--world-source /path/to/source.wld`. Требуются оба исходных файла `.wld` и `.twld`; launcher только читает их, копирует как `workbench.wld`/`workbench.twld` в новый sandbox и записывает хеши в `world-source-receipt.json`. Игровой процесс работает исключительно с копиями. Без указанного источника сервер создаёт новый мир; предметы, привязанные к другому миру, адаптер отклонит.

Для предмета, привязанного к существующему миру, `--world-source /path/world.wld` копирует `.wld` и обязательный парный `.twld` в sandbox и записывает SHA-256 источников и копий в `world-source-receipt.json`. Исходный мир не загружается и не изменяется. Если копия мира не предоставлена, ID нового мира может не совпасть с `worldId` предмета.

Все `.tmod` исполняют собственный код: проверяйте происхождение и зависимости тех модов, которые выбираете для прогона. Отдельная папка сохранений не является контейнером безопасности для стороннего кода.

## Подготовка клиентского сценария

```bash
python tools/item-test-workbench/tmod-driver/runner.py \
  --mode client --prepare-only --tml-dir /path/to/tModLoader \
  --scenario tools/item-test-workbench/fixtures/WorkbenchObserverFixture/item-scene.json \
  --mod IFCWorkbenchDriver=/path/to/IFCWorkbenchDriver.tmod \
  --mod WorkbenchObserverFixture=/path/to/WorkbenchObserverFixture.tmod \
  --extra-output IFC_WORKBENCH_OBSERVER_OUTPUT=observer.json
```

В созданном `client-launch.json` записаны команда, окружение и необходимые ручные шаги. Создайте в этом отдельном каталоге нового локального персонажа и мир `workbench`, затем войдите в него. До действий драйвер сверяет opt-in, одноразовый токен, marker, расположение save/world/scenario/output и локального персонажа; облачные файлы и переходы через ссылки отклоняются. `--mode client --run` намеренно не поддерживается.

Для IFC вместо `item` укажите `adapter: "IFCWorkbenchIFCAdapter"`, полный объект `itemData` и `itemBoundary: "fresh"` или `"local_cache"`; добавьте `.tmod` адаптера, IFC и его зависимости через отдельные `--mod`. Ненулевые `damage`, `speed`, `knockback` в `item_use` запрещены: используются фактические значения предмета. Адаптер не меняет `worldId` и отказывает при несовпадении или неудачной регистрации.

Для каждого непустого пути изображения, который использует игровой runtime, передайте отдельный параметр `--asset 'ОРИГИНАЛЬНЫЙ_ПУТЬ=/path/to/local.png'`. Launcher проверит соответствие исходной ссылке, скопирует PNG в sandbox и заменит только путь в тестовой копии сценария. `asset-staging-receipt.json` содержит исходный и новый SHA-256 сценария, точные изменённые поля и хеши файлов; оригинальный JSON не меняется. Неуказанные пути и конфликтующие имена вызывают отказ. Адаптер допускает только абсолютные пути к существующим файлам внутри sandbox без символических ссылок. `assetTransport: "http"` отклоняется, однако production IFC может обращаться к настроенному локальному asset backend: launcher не изолирует сеть. Получение ассетов и запуск клиента ещё не проверены.

Сцены задают координаты **в пикселях**. Модовая цель, расстояние, поверхность и препятствия влияют на результат. Подробный пример ожидаемых хуков и формат независимого `observer.json` — в `../fixtures/WorkbenchObserverFixture/README.md`.
