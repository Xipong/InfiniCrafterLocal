# infini_local/desktop — Infinicraft Studio

Основной пользовательский интерфейс — локальное браузерное приложение `webui/`. `web_studio.py` владеет loopback HTTP, временным ключом сессии, immutable snapshots и очередью действий. HTTP workers не трогают Tk variables. Существующий Tk-контроллер скрыт и обслуживает проверенные callbacks, OAuth/native dialogs и safe Start/Stop; отдельного gameplay/config владельца не создаётся.

## Владельцы

- `webui/index.html`, `studio.css`, `studio.js` — внешний вид, формы, поиск, keyboard navigation, unsaved draft и отображение состояний. Offline, без CDN.
- `web_studio.py` — browser entrypoint и адаптер к прежним owners; token-required read/write API, только loopback, без сторонних Origins. Synthetic defaults-only поля получают `FIELD_HELP` из canonical schema и сохраняются через retained config owner.

- `settings_gui.py` — публичный `SettingsGui`, инициализация состояния и `main()`. Launcher `LocalGenerator/settings_gui.py` остаётся совместимым.
- `settings_gui_ui.py` — только композиция mixins и совместимые импорты; не монолитная форма.
- `settings_gui_shell.py` — sidebar, компактный header, маршруты `PAGE_SPECS`, persistent workspace и профиль настроек. Страницы создаются один раз; навигация не перечитывает конфиг и не сбрасывает ввод.
- `settings_gui_components.py` — нативные поверхности, section rails, кнопки, типографика и ttk-стили.
- `settings_gui_theme.py` — dark forge/copper tokens, пути и выбор системного шрифта. Windows предпочитает Segoe UI; ограниченный X11 Tk использует масштабируемый helvetica вместо fixed 9px.
- `settings_gui_fields.py` — общие поля, скрытие неактивных веток, расширенный режим, маскировка ключей, edit shortcuts и отдельный канал help. Tooltip не стирает результат операции.
- `settings_page_operate.py` — первичная страница запуска/остановки и состояния; русский текст без engine jargon. Показывает только подтверждённое состояние и явно обозначенный последний снимок активности.
- `settings_page_providers.py` — текстовые модели, Codex account/catalog, дополнительные профили параллельного крафта.
- `settings_page_images.py` — backend изображений, локальные пути, LoRA, дополнительные аргументы sd.cpp и диагностика изображений.
- `settings_page_sprites.py` — прозрачность/края, уменьшение/палитра, авторство/эффекты.
- `settings_page_configure.py` — сервер/крафт, multiplayer/Radmin и настройки записи журналов.
- `settings_page_diagnostics.py` — представление журналов; refresh/cancel и файловые операции остаются в state owner.
- `settings_gui_image_args.py` — callbacks LoRA/аргументов, reset resize; совместимые делегирующие UI-builder методы.
- `settings_gui_trace_state.py` — async trace refresh/cancel, collect/save/presets и multiplayer state. Неизвестные настройки сохраняются; пользовательские профили не содержат ключей.
- `settings_gui_server_controls.py` — path pickers, bounded async workers/main-thread apply, health identity/effective-config и безопасный lifecycle сервера. Семантика Start/Stop/Force не меняется при смене UI.
- `settings_schema.py`, `settings_env.py`, `settings_sdcpp_args.py` — canonical GUI defaults/order/help, env persistence и чистые helpers аргументов.
- `settings_defaults.py` — версионное предложение только пересмотренных defaults, сравнение current → recommended и выборочная атомарная запись после согласия; отказ хранится отдельно в `config.env.defaults.json`. Не использует полный `collect/save`, не меняет providers/credentials/paths/неизменённые настройки.
- `settings_widgets.py`, `tk_compat.py` — generic scroll/tooltips и headless import shims.

## Совместимость и проверки

Legacy page indices сохраняются: 0 запуск, 1 текст, 2 параллельный крафт, 3 изображения, 4 спрайты, 5 диагностика; новые 6 multiplayer и 7 профили/сервер. `navigate(key)` — именованная sidebar-навигация. Basic/advanced скрывают неактивные поля, не очищая их значения. Все прежние 129 редактируемых полей покрыты literal inventory в `tests/test_desktop_forge_ui.py`.

Behavioral gates: `test_settings_gui_contract.py`, `test_codex_gui_catalog.py`, `test_full_logging_contract.py`, `test_desktop_forge_ui.py`. Последний содержит реальное создание Tk, переходы по всем страницам, минимальный размер окна, mask/save/unknown/token regression. Tk test требует display (Xvfb); headless common env пропускает только этот тест. Ни один тест UI не запускает игру, LLM/image inference или платный маршрут.

Этот UI не является владельцем gameplay/runtime контрактов. Изменение конфигурации не доказывает применение сервером: health подтверждает только ограниченную non-secret проекцию; secrets и дополнительные pools явно не подтверждаются.
