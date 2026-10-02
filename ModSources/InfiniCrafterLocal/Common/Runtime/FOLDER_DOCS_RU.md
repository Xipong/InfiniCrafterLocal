# Common/Runtime

Ограниченные deterministic executors принятого low-level wire:

- [RuntimeProgramExecutor.cs](RuntimeProgramExecutor.cs) — binding/event actions.
- [RuntimeDelayedActionScheduler.cs](RuntimeDelayedActionScheduler.cs) — отложенное исполнение с сохранением identity/бюджета.
- [RuntimeHitNpcGeneration.cs](RuntimeHitNpcGeneration.cs), [RuntimeHitPullBridge.cs](RuntimeHitPullBridge.cs) — generation fence и owner-hit/server мост.

Hard bounds принадлежат [InfiniRuntimeLimits.cs](../InfiniRuntimeLimits.cs), authority — [InfiniRuntimeAuthority.cs](../Services/InfiniRuntimeAuthority.cs). Lifecycle/peer details применяет runtime, не модель. Unknown opcode — fail-closed; name/category/tooltip не выбирают механику.
