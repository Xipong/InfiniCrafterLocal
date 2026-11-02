# Собрать мод из исходников

Обычному игроку сборка не нужна: установи готовый `.tmod` по [пользовательской инструкции](../user/START_RU.md#2-установи-мод). Этот документ нужен при изменении C#-кода.

## Что понадобится

- .NET SDK **8.0**. `global.json` выбирает установленную стабильную версию этой линии.
- Stable tModLoader и его сборочные файлы.
- Настоящие **ParticleLibrary.dll** и **Luminance.dll**. Одних названий модов в конфиге недостаточно: компилятору нужны файлы DLL.
- Python **3.11+** с pip на сборочной машине для подготовки встроенной Studio. Игроку отдельный Python не нужен: Windows x64 runtime входит в `.tmod`.

[Проект мода](../../ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj) использует `Tomat.Terraria.ModLoader.Sdk/2.1.1`. Зависимости не лежат в исходном архиве. Сборка без них сообщает, какой файл отсутствует.

## Вариант 1: Build + Reload в tModLoader

Сначала из корня репозитория выполни `python tools/build/build_studio_bundle.py`. Команда подготовит Studio вместе с её Python и зависимостями внутри `ModSources/InfiniCrafterLocal/Studio/`; затем установщик скопирует их вместе с модом. Повтори подготовку после изменений Python-кода, Studio или её ресурсов.

1. Сохрани свою прежнюю папку `ModSources/InfiniCrafterLocal`, если она содержит изменения.
2. Запусти [tools/windows/01_INSTALL_MOD_TO_TMODLOADER.bat](../../tools/windows/01_INSTALL_MOD_TO_TMODLOADER.bat). Он копирует исходники в пользовательский ModSources **с заменой старой одноимённой папки**.
3. В tModLoader открой **Workshop → Develop Mods → Build + Reload** для InfiniCrafterLocal.
4. При ошибке сборки сохрани полный журнал. Дополнительный сборщик журнала: [03_COLLECT_TMODLOADER_BUILD_ERRORS.bat](../../tools/windows/03_COLLECT_TMODLOADER_BUILD_ERRORS.bat).

**Результат:** игра собрала и перезагрузила мод. Это запуск tModLoader; не используй данный вариант как автоматическую фоновую проверку в агентской задаче.

## Вариант 2: сборка через .NET

Для `.tmod` сначала подготовь Studio той же командой. Если нужна только проверка компиляции C#, добавь `/p:TmlBuildMod=false`: она не требует браузерного runtime и не создаёт готовую поставку.

Из корня проекта в PowerShell, подставив пути к своим DLL:

```powershell
dotnet build ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj -c Release `
  /p:InfiniParticleLibraryDll="C:\deps\ParticleLibrary.dll" `
  /p:InfiniLuminanceDll="C:\deps\Luminance.dll"
```

Или задай один корень:

```powershell
dotnet build ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj -c Release `
  /p:InfiniExternalDepsRoot="C:\deps"
```

Во втором варианте должны существовать:

```text
C:\deps\ParticleLibrary\ParticleLibrary.dll
C:\deps\Luminance\bin\Debug\net8.0\Luminance.dll
```

Вместо свойства можно задать переменную окружения `INFINI_TML_DEPS_SRC`. Явные пути отдельных DLL имеют приоритет.

**Результат:** команда завершается с кодом 0 и без ошибок компилятора. Проверь фактический путь DLL/`.tmod` в выводе SDK: он зависит от режима сборки. Проверка компиляции сама по себе не устанавливает мод и не запускает игру.

### Сборка с журналом

[tools/build/build_tml_windows.bat](../../tools/build/build_tml_windows.bat) запускает PowerShell-обёртку. Ей можно передать `-Project`, `-Configuration`, `-LogDir`, `-InfiniExternalDepsRoot`, `-InfiniParticleLibraryDll`, `-InfiniLuminanceDll`. Пример:

```powershell
.\tools\build\build_tml_windows.bat -Configuration Release -InfiniParticleLibraryDll "C:\deps\ParticleLibrary.dll" -InfiniLuminanceDll "C:\deps\Luminance.dll"
```

Код **77** означает отсутствие необходимой сборочной среды (`notRun`), а не успешную сборку. Если сборка действительно запущена и падает, изучи журнал; не скрывай ошибку отсутствием зависимостей.

## Готовая поставка со Studio

После restore и настройки DLL запусти на Windows `./tools/build/package_tmod.ps1`. Тот же путь используется в CI. Он собирает Studio, проверяет её реальный запуск и завершение, вызывает официальный упаковщик tModLoader, затем проверяет собранный `.tmod` и вложенный ZIP. Результат — `artifacts/package/InfiniCrafterLocal.tmod`; дополнительный архив генератора для встроенного запуска не требуется.

Внутри мода лежат `Studio/manifest.json` и `Studio/runtime-win-x64.zip`. ZIP сохраняет PNG/веб-ресурсы без преобразования tModLoader в `.rawimg`. Он содержит код Studio/генератора, контракты, исходные справочники, руководство, изолированный Python и binary wheels зависимостей. Пользовательские `config.env`, токены, кеш, трассы и тестовые данные в него не попадают. Лицензии Python, IFC и установленных зависимостей сохраняются.

Интерпретатор **CPython 3.14.10 Windows x64** скачивается с [официальной страницы Python](https://www.python.org/downloads/release/python-31410/) с проверкой закреплённого SHA-256; версии зависимостей берутся из существующего `requirements-dev.lock`, устанавливаются только runtime-требования из `requirements.txt`. Pip выполняется при сборке. На данный момент встроенная поставка поддерживает Windows x64; внешний запуск из исходников остаётся доступен на других системах.

Для сборки из локальных загрузок можно передать `--python-archive <официальный ZIP>` и `--wheelhouse <папка wheels>` в `build_studio_bundle.py`; SHA-256 интерпретатора всё равно проверяется. `--skip-smoke` позволяет подготовить ZIP на другой ОС, но не используется release-скриптом и не подтверждает работоспособность Windows runtime. Сгенерированные ZIP/manifest не коммитятся. Проверка встроенного Python и HTTP в CI не заменяет игровой smoke кнопки меню.

## Частые ошибки

| Сообщение | Что проверить |
|---|---|
| Не найден .NET SDK | `dotnet --list-sdks`: нужен установленный SDK 8.0, не только runtime |
| ParticleLibrary.dll / Luminance.dll was not found | Существуют ли файлы по переданным путям; указан ли путь к DLL, а не `.tmod` |
| Не найден tModLoader / его targets | Stable установка tModLoader и доступность пакетов выбранного SDK |
| Ошибка C# с файлом и строкой | Исправь исходник; проверь API установленного tModLoader, затем повтори сборку |
| Wrapper вернул 77 | Подготовь отсутствующую среду; этот запуск ничего не скомпилировал |

## Что проверять после сборки

- [Тесты и их уровни](TESTING_RU.md): Python-контракты, headless native checks и игра — разные проверки.
- [Архитектура](architecture/ARCHITECTURE_RU.md) и [границы модулей](MODULES_RU.md): кто владеет данными и действиями.
- [Диагностика игры](../user/DIAGNOSTICS_RU.md) и [команды кеша](../user/COMMANDS_RU.md#догрузка-и-кеш).

PNG созданных предметов хранятся отдельно от встроенных ресурсов мода. Очистка runtime-кеша не должна удалять сохранённые рецепты и PNG. Крафт, отмена и возврат материалов принадлежат существующим серверным владельцам; сборочная правка не даёт права менять эти механики.
