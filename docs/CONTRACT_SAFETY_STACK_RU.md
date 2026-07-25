# Contract safety stack — runtimeProgram v5

## Источник истины

`capability_registry.py` объявляет grammar и 52 capability. Из него выводятся provider schema, prompt catalog, machine inventory, compiler ownership и docs.

## Gates

```bash
PYTHONPATH=LocalGenerator python tools/generate_low_level_runtime_docs.py --check
PYTHONPATH=LocalGenerator python tools/audit_capability_library.py
PYTHONPATH=LocalGenerator python tools/check_delivery_contract.py
PYTHONPATH=LocalGenerator python tools/contract_parity.py
PYTHONPATH=LocalGenerator python tools/mutation_contract_gate.py
python tools/check_csharp_contracts.py
```

Они проверяют:

- registry/schema/prompt parity;
- typed refs, kinds, inputs/actions/events;
- exact wire paths и compiler receipts;
- Python callable + конкретные C# method symbols;
- authored ranges не шире C# clamps;
- strict unknown-field rejection;
- 52 author→wire vertical witnesses;
- восемь non-archetypal programs;
- отсутствие old weapon macro/family route;
- четыре mutation cases.

## Mutation cases

1. capability без C# executor;
2. второй writer существующего component slot;
3. technical lowerer с недекларированным output;
4. новое final-wire field без DTO vertical slice.

## Runtime safety

C# проверяет versions, target kinds, input/action pairs, required components, position driver, event producer, cycles, child depth, spawn count/rate/lifetime и unknown opcodes. Gameplay authority остаётся owner/server bounded по effect; client-only capabilities не наносят gameplay effect.

## Ограничение доказательства

Static scanner и Python witnesses не заменяют `dotnet build` и tModLoader singleplayer/host-client smoke. Если toolchain/dependencies отсутствуют, verification обязан записать `notRun`.
