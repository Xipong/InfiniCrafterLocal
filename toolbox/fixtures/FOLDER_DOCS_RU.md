# toolbox/fixtures

`items.jsonl` — побайтовая копия локального Terraria runtime dump (39 записей `sourceMod=Terraria`, SHA-256 `62b64ac70eaad27004e4d4e006c1bfb6ba44775b98a216ad2aaa4afaebb20e06`). Используется только как неизменяемые parent facts для Live20; не запускает Terraria и не выбирает игровые решения за Author. Harness сверяет SHA в campaign manifest. Другой dump передаётся только явным `--runtime-dump`.
