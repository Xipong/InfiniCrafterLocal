# Content/Items — tModLoader item proxy layer

Generated content is per-instance data carried by proxy item classes, not one class per generated item.

- `InfiniCore.cs` — station key item and ingredient validity guard.
- `GeneratedItem.cs` — main proxy: set/save/load/net generated data, apply DTO, register world data, use/equipment hooks, shoot, runtime sprite drawing; generated tooltip output is forbidden.
- `GeneratedArmorItems.cs` — head/body/legs proxy classes for Terraria armor slots.


Rules:
- `GeneratedItem` applies explicit `GeneratedItemData`; authored/generated tooltip output is forbidden, and gameplay never routes from prose/name/category/tags.
- `Attack.Enabled` does not mean every item must spawn a generated projectile. `RuntimePlanAuthored` and runtime family/delivery decide executor behavior; vanilla hitbox/tool paths can remain vanilla.
- Secondary/child projectile behavior must stay bounded and sanitized.
