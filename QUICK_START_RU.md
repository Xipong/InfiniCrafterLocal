# InfiniCrafterLocal v0.4.237 — quick start

1. Build/install `ModSources/InfiniCrafterLocal` as the tModLoader mod.
2. Start LocalGenerator so `http://127.0.0.1:5055/combine` is reachable for host/singleplayer.
3. In Terraria, craft `InfiniCore`: 20 wood + 1 Fallen Star.
4. Keep `InfiniCore` in inventory and open inventory.
5. Put two explicit input items into the InfiniCraft station A/B slots.
6. Press Craft. The UI shows stabilization/progress; result is granted when LocalGenerator returns a deliverable `GeneratedItemData`.
7. In multiplayer, only the host/server runs generation. Clients send craft intent and then receive server commit + registry/assets.

Helpful commands:
- `/getinfini` — registry/asset catch-up.
- `/infinicache` — runtime sprite/asset cache diagnostics.
- `/infinidump` — inspect item/projectile runtime values.
- `/infinidumppicture` — dump source/runtime texture bundle.

If generated sprites do not show in MP, check host asset base URL and whether clients can reach `/get_asset?file=...`.
