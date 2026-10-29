# Промпты и агентные инструкции: ориентиры 2026 Q4

Для контрибьютора и его ИИ-ассистента при работе над промптами в этой папке. Наследуй [Python AGENTS](../AGENTS.md). Этот файл не отправляется модели, генерирующей предметы.

## Актуальные руководства

Подборка проверена 2026-10-29. Читай подходящий к задаче и модели источник; читать весь список перед каждой правкой не требуется.

- **OpenAI, 2026-10-02:** [A model guide for the GPT-6 family](https://openai.com/index/practical-guide-building-gpt-6/) — постановка задачи, контекст, результат и границы самостоятельной работы.
- **OpenAI, 2026-09-11:** [Rethinking skills and prompts for GPT-6 Astra](https://learn.chatgpt.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) — обновление skills и AGENTS.md; рекомендации для Astra не автоматически подходят Sol и Luna.
- **Anthropic:** [Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) — руководство для актуальных Claude и ссылки на особенности отдельных моделей.
- **Anthropic:** [Prompting Claude Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5) — рекомендации именно для Opus 5.5. Страницы документации обновляются; дата выше означает проверку, не дату публикации.
- **Poteto / pstack:** [Практическое руководство](https://github.com/cursor/plugins/blob/main/pstack/docs/guide/README.md), [пост 2026-10-16](https://x.com/poteto/status/2111133080526495985), [пост 2026-10-24](https://x.com/poteto/status/2114099131845423142) — опыт работы с coding-агентами. Это авторская практика и конкретный harness, а не общий стандарт моделей или требование установить pstack.

## Применение в IFC

Ориентир — возможности современных моделей, а не привычные шаблоны промптинга 2024 года. Формулируй нужный результат и недостающий контекст; уровень детализации выбирай под задачу и модель. Краткость сама по себе не цель.

Смотри на фактический запрос целиком, включая данные и схему ответа. Отличай избыточное объяснение от сведений о частном API IFC. Сокращение пояснений и изменение механики, контракта или назначения полей — разные решения; не подменяй одно другим.
