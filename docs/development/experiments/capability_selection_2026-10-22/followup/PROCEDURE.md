# Процедура агентных запусков

Модель всех selector/Author trials: `gpt-6-luna`, reasoning `high`, `fork_turns=none`. Каждый Author — свежая сессия. Нейтральный ID из protocol.json скрывает arm в назначении; содержимое полного и сокращённого пакетов, разумеется, различается. Это не полное ослепление модели относительно размера каталога.

Ниже нормализованный шаблон задания, а не заявление о побайтово одинаковой служебной обвязке всех сессий. Пакеты читались через tools; модель инструктировали прочитать весь файл без усечения и рассуждать перед записью. В ранних заданиях требование отсутствия усечения было текстовым; позднее также явно указывался output limit 100000. Промежуточные reasoning/tool tokens не измерялись.

## Author

```text
You are the Gameplay Author for one blind trial. Read ONLY the assigned JSON
packet at <absolute author_packets/ID.json>, in full without truncation.
Use tools only to read that packet and save the answer. Do not inspect the
repository, other trials, fixtures, expected outputs, validators or internet.
Use the packet's source context, experimentBrief, instructions and
requiredJsonShape. Preserve the requested primary and secondary functions.
Reason normally before saving. Write exactly one first-answer JSON document
to <absolute outputs/ID.json>. No validator feedback, repairs, further
capability retrieval or consultation with other agents. Do not edit it after
saving. Report the saved path.
```

## Selector

Одна свежая сессия на mode/repeat, внутри три packet files (wand, musket, tool). Каждый файл содержит selector instructions, полный discovery index и response schema. Модель читает каждый полностью и сохраняет единственное решение по указанной schema в соответствующий selections/mode/case_rN.json. Нельзя читать baseline answers, код, чужие selections или результаты валидации. Это четыре независимых selector-сессии с 12 решениями, не 12 изолированных selector trials.

## Оценивание и ревью

После заморозки всех ответов применяются канонические validator/compiler и явно описанная рубрика. Отдельная Luna-сессия имеет доступ к коду, frozen outputs и результатам для методологического/функционального ревью; она не генерирует исправленные Author outputs. Проверки рубрики уточнялись по замечаниям и контрпримерам; эти изменения раскрыты в README и покрыты тестами. Это не полностью preregistered независимая оценка: требования зафиксированы заранее, реализация scorer проверялась и исправлялась во время анализа.
