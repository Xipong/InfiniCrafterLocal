# Source reports и сертификаты

`native_*_sources.generated.json` — действующие source reports: их читают generators, проверки и producer native-сертификатов. Они не являются одноразовыми логами тестов и не удаляются при очистке результатов кампаний. Producers и refresh-команды — [generated sources](../../docs/reference/GENERATED_RU.md).

`native_ammo_sources.md` и `native_buff_effect_contract.md` описывают соответствующие source contracts. `parent_source_coverage_audit.md` сохраняет отдельный аудит с указанным baseline, не объявляет текущую игровую приёмку.

## Удалённые устаревшие receipts

Одноразовые проверки версии 0.4.241, orphaned parity/impact/sandbox receipts и старый `SHA256SUMS_SOURCE.txt` удалены из текущей поставки. У них нет действующего producer/consumer; их старые counts, PASS и checksums не описывают нынешний код. Полные исходные данные доступны в [снимке до очистки](https://github.com/Xipong/InfiniCrafterLocal/tree/3d0b437745d90c4bdc6c6f26a67bab1e31d3f99f/contracts/reports).

Актуальные checksums публикуются вместе с конкретным релизом. Пользовательские инструкции — [установка](../../docs/user/START_RU.md); текущие команды проверки — [тестирование](../../docs/development/TESTING_RU.md).
