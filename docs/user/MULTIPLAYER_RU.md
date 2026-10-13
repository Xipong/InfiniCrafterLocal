# Игра с друзьями — 0.5.00

## Обычный вариант: native

1. Хозяин устанавливает **мод и LocalGenerator** и проходит [первый запуск](START_RU.md).
2. Друзья устанавливают совместимую версию мода и игровых зависимостей. Их собственный генератор/ключи для этой сессии не нужны.
3. Оставь `INFINI_MP_ASSET_TRANSPORT=native` — это default. Generated PNG передаются пакетами Terraria, отдельный публичный HTTP для клиентов не требуется.
4. Запусти обычную Terraria/tModLoader host/server сессию и подключи друзей своим сетевым способом.

Только host/server генерирует, коммитит результат и владеет refund. Клиент отправляет intent/parent references, а не готовый authoritative JSON. Native transport не означает открытый доступ к prompts/LLM.

## HTTP assets: только если ты выбрал этот режим

В разделе **«Совместная игра»** выбери `http`, задай достижимый для друзей `INFINI_ASSET_PUBLIC_BASE_URL` и bind `INFINI_HOST=0.0.0.0`. Разрешай generator port в firewall **только доверенным LAN/Radmin peers**; не публикуй сервер в интернет без отдельного анализа безопасности.

- `/get_asset?file=...` проверяет descriptor/bytes.
- `INFINI_PORT` обычно **5055**, Terraria port — обычно **7777**; это разные службы.
- Radmin `26.x.x.x` — пример, не готовый твой адрес. Auto-guess предпочитает Radmin `26.x`, но достижимость нужно проверить с клиента.
- SinglePlayer/server использует настроенный generator endpoint; advertised public URL предназначен друзьям. Смена порта генератора требует согласовать endpoint мода.

[Эксплуатация](OPERATIONS_RU.md#multiplayer-и-диагностика) · [Ошибки и cache](DIAGNOSTICS_RU.md) · [Команды](COMMANDS_RU.md)

Offline/native role-mode проверки не равны фактическому peer delivery или успешному MP-матчу. Не отключай сервер посреди craft только потому, что GUI уже ответил.
