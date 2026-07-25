# Common/Runtime

Здесь находятся ограниченные deterministic executors нового low-level runtime.

- `RuntimeProgramExecutor.cs` исполняет только явно authored event actions из `RuntimeProgramSpec`.
- `InfiniRuntimeLimits.cs` задаёт hard bounds для entities, child depth, spawn count и event rate.
- `InfiniRuntimeAuthority.cs` централизует owner/server authority и сетевую синхронизацию.

Код этой папки не вправе выбирать weapon family, movement, attachment, delivery или lifecycle из имени, категории, tooltip и прочего prose. Неизвестный opcode обязан быть inert/fail-closed.
