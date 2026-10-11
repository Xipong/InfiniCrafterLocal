# .github/workflows

[ci.yml](ci.yml) — Python/offline checks, static contracts и условная Windows/tModLoader сборка. Отсутствие внешних игровых DLL означает явно пропущенную сборку, не PASS. Это automation, не игровой runtime.

Полный workflow запускается для каждого Pull Request (включая draft и fork),
каждого push в `main` и ручного `workflow_dispatch`. Push в отдельную ветку
не дублирует PR-run; для ветки без PR доступен ручной запуск. Фильтров paths,
сокращённого semantic corpus и пропуска tests по cache hit нет.

Новый run того же PR отменяет устаревший. Разные PR, каждый main commit и каждый
ручной run имеют отдельные concurrency groups; pending main/manual проверки тоже
не вытесняются. Два Python jobs кешируют только pip downloads по
`LocalGenerator/requirements-dev.lock`, установка зависимостей остаётся обязательной.
