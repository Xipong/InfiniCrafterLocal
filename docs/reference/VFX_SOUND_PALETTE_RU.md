# Точная звуковая палитра и явные параметры воспроизведения

## Что восстановлено

Исторический `InfiniSoundLibrary` в `f04ee02` содержал 92 acoustic IDs, соответствующие 71 уникальному `SoundID`. До этого изменения VFX-owned `soundId` уже поддерживал 20 native members: семь пересекались с историческим набором, 13 были новыми. Теперь доступны **84 exact `SoundID`** — объединение обоих наборов; все 64 недостающих исторических members возвращены. [Независимый inventory fixture](../../LocalGenerator/tests/fixtures/vfx_sound_inventory.json) сохраняет исходные таблицы и commits для проверки этого утверждения.

Канонический runtime-facing owner — [`vfx_manifest.py`](../../LocalGenerator/infini_local/core/vfx_manifest.py): `_SOUND_IDS` определяет один finite selector domain, `_sound_schema()` — три playback controls. Director, Repair и persisted wire берут определения отсюда. Gameplay Author не получает звуковых capabilities. Выбор не зависит от названия, класса урона, parent prose, размера visual budget или категории оружия.

Прежние acoustic IDs вроде `bow_release` используются только как историческое свидетельство. Они не входят в новый enum и не запускают routing. Модель передаёт конкретный `SoundID`, например `Item5`, `Item58`, `Item71`, `Item152` или `Item169`.

## Выбор VFX Director

Каждый `soundCue`, включая saved wire, явно выбирает `soundId` и полный объект `sound`. Ниже показан фрагмент slot; остальные общие поля и exact `entityId + event` берутся из обычного VFX-контракта:

```json
{
  "rendererKind": "soundCue",
  "channel": "sound",
  "lane": "cue",
  "soundId": "Item26",
  "sound": {
    "volume": 0.55,
    "pitch": -0.25,
    "pitchVariance": 0.12
  }
}
```

| Поле | Допустимые значения | Исполняемый смысл |
|---|---|---|
| `soundId` | Один из 84 exact members | Native sample asset, variants и playback policies; без free paths и замены неизвестного ID |
| `sound.volume` | Число 0…1 | Финальный `SoundStyle.Volume`; ни common `alpha`, ни native sample Volume не умножают его |
| `sound.pitch` | Число −0.9…0.9 | Центральная высота относительно исходного sample: 0 — обычный тон; шкала −1…1 соответствует одной октаве вниз/вверх |
| `sound.pitchVariance` | Число 0…0.6 | Полная ширина native random pitch interval: `pitch ± pitchVariance/2`; ноль отключает pitch jitter |

Дополнительно весь интервал должен помещаться в native диапазон `[-1,1]`: `abs(pitch) + pitchVariance/2 <= 1`. Например, `pitch=0.9, pitchVariance=0.2` допустимы, а `0.9/0.6` — нет. Это refusal с точной диагностикой, а не скрытый clamp authored variance. Название `pitchVariance` следует API Terraria; величина не является статистической дисперсией.

`volume=0` — явная тишина: slot не вызывает `SoundEngine.PlaySound` и не занимает native sound instance. Пустой `slots` тоже остаётся допустимым решением. Native `Item.UseSound` у generated items по-прежнему отключён: отсутствие audio slot не дополняется звуком. Звук может существовать без particles, trails или PNG.

У `sound` только один владелец громкости — `sound.volume`. Общий `alpha` остаётся в форме VFX slot, но не влияет на аудио. У `pitch` нет дополнительного `phaseOffset`, sample pitch, seed jitter или `Main.musicPitch`. Дистанция до слушателя, пользовательская громкость и native sound settings действуют дальше обычным образом.

## Native projection

[`VfxSoundSpec`](../../ModSources/InfiniCrafterLocal/Common/Models/Presentation/VfxSoundSpec.cs) — строгий DTO с тремя обязательными числовыми полями. [`VfxSlotSpec.ResolveSoundStyle`](../../ModSources/InfiniCrafterLocal/Common/Models/Presentation/VfxManifestSpec.cs) выбирает общий путь для item, projectile и detached events.

Преобразование относится к **Alias Lowering**: конкретный зарегистрированный `soundId` однозначно выбирает native sample; три literal playback fields проецируются без изменения значений. Код не выбирает sample, тон или громкость за модель. Публичный `SoundStyle` constructor получает exact native path/variants/type; затем сохраняются `Identifier`, `MaxInstances`, `SoundLimitBehavior`, `RerollAttempts`, `LimitsArePerVariant`, `PlayOnlyIfFocused`, `PauseBehavior`, `IsLooped` и variant weights. Три authored controls заменяют только соответствующие playback scalars.

Публичная реконструкция имеет конкретную причину. У native `SoundID.Item26` стоит internal `UsesMusicPitch=true`; `SoundPlayer` добавляет `Main.musicPitch` после вызова VFX consumer. Простая конструкция `sample with { Pitch = authoredPitch }` сохранила бы этот скрытый offset. Новый constructor выключает internal instrument policy по штатному native default и оставляет весь публичный playback policy неизменным. Production не использует reflection и не изменяет глобальный `Main.musicPitch`.

Эти native свойства проверены по stable tModLoader source commit `c9545cf27d56c456321e1896274c02adf67d0140`:

- [SoundID.TML.cs](https://github.com/tModLoader/tModLoader/blob/c9545cf27d56c456321e1896274c02adf67d0140/patches/tModLoader/Terraria/ID/SoundID.TML.cs) — реальные sample members и instrument flag;
- [SoundStyle.TML.cs](https://github.com/tModLoader/tModLoader/blob/c9545cf27d56c456321e1896274c02adf67d0140/patches/tModLoader/Terraria/Audio/SoundStyle.TML.cs) — поля, constructor и random pitch calculation;
- [SoundPlayer.cs.patch](https://github.com/tModLoader/tModLoader/blob/c9545cf27d56c456321e1896274c02adf67d0140/patches/tModLoader/Terraria/Audio/SoundPlayer.cs.patch) — применение instrument pitch;
- [SoundStyle API](https://docs.tmodloader.net/docs/stable/struct_sound_style.html) и [SoundID API](https://docs.tmodloader.net/docs/stable/class_sound_i_d.html) — публичные native definitions.

Это восстановление доступных samples и явного управления, а не копирование прежних скрытых volume scales, `max(nativeVariance, authoredVariance)` или keyword fallback. Новые поля имеют описанный выше прямой смысл.

## Admission сохранённых предметов

Director output и persisted wire используют одну conditional schema: каждый `soundCue` обязан содержать оба явных выбора — exact `soundId` и полный `sound={volume,pitch,pitchVariance}`. Отсутствие любого поля отвергается Python validator/cache admission и native manifest normalization. `Item1` остаётся допустимым явным selector, но больше не выбирается при отсутствии `soundId`; alpha/phaseOffset не создают громкость или pitch при отсутствии `sound`.

Нет cache importer, переписывания старых записей или автоматического заполнения controls. Старые записи с пропусками становятся invalid; обычный cache reader quarantines их через существующий storage owner. Присутствующий `sound` не может иметь null, неизвестные поля или неполный набор scalars. Non-sound renderers по-прежнему опускают оба audio fields; foreign payload отвергается. Пустой slots остаётся допустимой тишиной.

Runtime packet identities, event cadence, anchor resolution и существующие occurrence budgets не меняются; native pitch randomness остаётся локальной для каждого слушателя, контракт не обещает одинаковый случайный тон на всех клиентах.

## Repair и compiler receipts

Repair использует обычный frozen-first subtree merge. Неверный `sound.volume` открывает только эту leaf; корректные pitch, variance, sample, entity/event, alpha и остальные slots остаются frozen. Если отсутствует весь `sound`, модель может передать только эту недостающую тройку, сохранив ранее выбранный sample. При нарушении интервала диагностируется `sound.pitchVariance`, чтобы сохранить уже валидный центральный pitch. При невалидном самом pitch это правило не расширяет scope на его валидного соседа.

Canonical VFX structural prefilter теперь снимает numeric bounds до frozen merge. Поэтому typed попытка заменить frozen pitch на `99` игнорируется с audit и не отменяет полезное исправление volume. Числовые типы, объявленные keys и required shape проверяются до merge; все bounds и зависимости — после него. Если сама разрешённая для исправления volume остаётся вне диапазона, итоговый manifest отклоняется. Это изменение общей границы VFX Repair, без отдельного sound-specific repair API.

Неверный audio payload у другого renderer разрешено удалить точно по `deletePaths`, не превращая валидный renderer в soundCue. Удаление valid sound slot, изменение существующей тишины и перезапись sound controls вне scope игнорируются с audit.

Compiler сохраняет `soundId` и controls без числовой normalization. В `debug.vfxSoundReceipts` записываются четыре source-backed identity receipts: sample и три scalars, с exact authored/final paths и literal values. `audit_vfx_sound_projection` сверяет эти receipts, presence, target slot и его entity/event/renderer. Attachment отказывает при потере или подмене выбора. Диагностические receipts не управляют звуком: C# исполняет только принятый VFX wire; cached wire с полными явными controls не требует нового sidecar.

## Проверки и пределы доказательства

Python tests сверяют все 84 selectors с независимым inventory и schema vocabulary; representative numeric/named samples проверяются на item/projectile bindings через настоящий offline Director transport. Дополнительно проверяются full/partial/invalid controls, old-absence refusal, нули, границы, JSON-object/JSON-schema Repair, frozen neighbors, delivery/cache admission и mutation compiler receipts. Независимый historical inventory не строится из production `_SOUND_IDS`. C# source scanner сверяет exact native mapping с canonical owner, DTO surface, общую playback projection, нулевую громкость и сохранение native policies; отдельные mutants ломают каждый из этих путей.

[`EngineRuntimeChecks.SoundSelection.cs`](../../tools/EngineRuntimeChecks.SoundSelection.cs) проверяет явные selections/controls по всем samples и item/projectile periodic/event и detached routes. Отказ старой absence через native readers и playback resolver покрывает [`EngineRuntimeChecks.NativeDtoRetirement.cs`](../../tools/EngineRuntimeChecks.NativeDtoRetirement.cs). SoundSelection наблюдает настоящий `SoundEngine.PlaySound` boundary, JSON roundtrips, interval rejection, явную тишину, native policy copy и `GetRandomPitch`; instrument flag наблюдается только в тесте. Тесты не открывают audio device и не доказывают художественное качество или audibility в игре.

Нативный runner исполняется отдельно от Python tests и требует matching tModLoader/dependency assemblies. Приёмка этого follow-up включает SDK build и headless EngineRuntimeChecks, в том числе sound consumers и отказ old-absence; точные результаты привязаны к финальной source/delivery receipt. Это не SP/MP game/audio smoke: игра, audio device и художественное качество звучания не проверялись.
