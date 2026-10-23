# Craft refund recovery (#180)

`/ifcrefunds` lists the real retained local refund queue, including exact generated definition IDs, quantities and prefixes. Numeric pages show eight rows. `/ifcrefunds pause` persists a player preference to retain future refunds until explicitly claimed; `/ifcrefunds auto` restores the original automatic inventory/world delivery policy.

`/ifcrefunds claim [row]` uses the existing exact native stacking owner, delivers only into inventory, retains partial remainders, and never allocates world drops. Claiming all rows repeatedly cannot duplicate materials. Existing save/load and world-scoping rules remain authoritative; server escrow is never synthesized into a local claim.

Native `QoL RefundStacks` covers exact generated stack merging, paused retention, partial inventory claims, immutable snapshots, full-inventory refusal and final removal. No game or multiplayer session was run.
