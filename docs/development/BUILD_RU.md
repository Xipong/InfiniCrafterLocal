# Собрать мод из исходников

Обычному игроку сборка не нужна: установи готовый `.tmod` по [пользовательской инструкции](../user/START_RU.md#2-установи-мод). Этот документ нужен при изменении C#-кода.

## Что понадобится

- .NET SDK **8.0**. `global.json` выбирает установленную стабильную версию этой линии.
- Stable tModLoader и его сборочные файлы.
- Настоящие **ParticleLibrary.dll** и **Luminance.dll**. Одних названий модов в конфиге недостаточно: компилятору нужны файлы DLL.

[Проект мода](../../ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj) использует `Tomat.Terraria.ModLoader.Sdk/2.1.1`. Зависимости не лежат в исходном архиве. Сборка без них сообщает, какой файл отсутствует.

## Вариант 1: Build + Reload в tModLoader

1. Сохрани свою прежнюю папку `ModSources/InfiniCrafterLocal`, если она содержит изменения.
2. Запусти [tools/windows/01_INSTALL_MOD_TO_TMODLOADER.bat](../../tools/windows/01_INSTALL_MOD_TO_TMODLOADER.bat). Он копирует исходники в пользовательский ModSources **с заменой старой одноимённой папки**.
3. В tModLoader открой **Workshop → Develop Mods → Build + Reload** для InfiniCrafterLocal.
4. При ошибке сборки сохрани полный журнал. Дополнительный сборщик журнала: [03_COLLECT_TMODLOADER_BUILD_ERRORS.bat](../../tools/windows/03_COLLECT_TMODLOADER_BUILD_ERRORS.bat).

**Результат:** игра собрала и перезагрузила мод. Это запуск tModLoader; не используй данный вариант как автоматическую фоновую проверку в агентской задаче.

## Вариант 2: сборка через .NET

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
