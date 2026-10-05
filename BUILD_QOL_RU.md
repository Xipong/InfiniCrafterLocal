# Сборка и runtime QoL InfiniCrafterLocal

Установка и запуск принадлежат [runbook 0.4.247](QUICK_START_RU.md); здесь — зависимости C# и граница runtime cache.

## Сборка

[Проект](ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj): `Tomat.Terraria.ModLoader.Sdk/2.1.1`, `TmlVersion=stable`, `LangVersion=latest`; требуются .NET 8 и реальные compile-time references `ParticleLibrary.dll`/`Luminance.dll`.

Из корня, пример PowerShell с **заменяемыми** путями:

```powershell
dotnet build ModSources/InfiniCrafterLocal/InfiniCrafterLocal.csproj `
  /p:InfiniParticleLibraryDll="C:\deps\ParticleLibrary.dll" `
  /p:InfiniLuminanceDll="C:\deps\Luminance.dll"
```

Вместо отдельных DLL можно задать `/p:InfiniExternalDepsRoot="C:\deps"` или env `INFINI_TML_DEPS_SRC`. Тогда ожидаются `ParticleLibrary/ParticleLibrary.dll` и `Luminance/bin/Debug/net8.0/Luminance.dll`. Без DLL target `InfiniValidateExternalModReferences` намеренно падает до `ResolveReferences`.

`tools/build_tml_windows.bat` оборачивает [PowerShell build/log parser](tools/build_tml_windows.ps1); параметры: `-Project`, `-Configuration`, `-LogDir`, `-InfiniExternalDepsRoot`, `-InfiniParticleLibraryDll`, `-InfiniLuminanceDll`. Wrapper exit `77` — неполная среда/`notRun`, не успешная сборка; `0` — build без найденных ошибок, `1` — ошибка, `2` — проблема среды/скрипта. [Headless/QA границы](docs/TEST_CONTRACT_OWNERS_RU.md#запуск-и-сила-доказательства) не заменяют игровые smoke.

## Runtime QoL

PNG генерируются во время работы, не являются embedded tML assets. `InfiniGameplayQolConfig` ограничивает `RuntimeSpriteCache`; inventory prefetch может прогревать assets. При missing/invalid texture клиент может безопасно показывать placeholder; это **не** разрешение обходить generator delivery gate обязательного PNG.

Cache clear не удаляет disk PNG/JSON/recipes: [команды и paths](command.md#infinicache). MP asset mode теперь default **native**, HTTP требует доступного host endpoint: [настройка MP](QUICK_START_RU.md#multiplayer-и-диагностика), не обязательный HTTP для всех клиентов.

Commit/refund server-authoritative: клиенты не присылают готовый `GeneratedItemData`. Fatal craft failure проходит штатный refund path; transient transport/cache races имеют bounded recovery. При world unload pending inputs обрабатываются refund/save, presentation sync caches очищаются. Prompt/prose/script поля не исполняются как gameplay.
