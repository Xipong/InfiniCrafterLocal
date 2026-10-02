# Content/Items

Per-instance generated data исполняется общими tModLoader proxy-классами, а не новым C# классом на каждый предмет.

- [InfiniCore.cs](InfiniCore.cs) — station key и ingredient guard.
- [GeneratedItem.cs](GeneratedItem.cs) и partials — DTO application, save/net, binding/use/equipment hooks, runtime sprite drawing.
- [GeneratedArmorItems.cs](GeneratedArmorItems.cs) — head/body/legs proxy types.

Use policy задаёт явные action, stackCost и contactDamage. Наличие projectile в программе не означает обязательный projectile-use и не выбирает primary owner: действует принятый `runtimeProgram`/binding. `AttackSpec`, `RuntimePlanAuthored` и family/delivery routers не являются текущим контрактом. Generated tooltip output и gameplay routing по prose/name/category запрещены; secondary/child actions остаются bounded.
