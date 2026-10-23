# Completion notification centre (#181)

Final outcomes from all three craft lanes enter one local queue. The HUD keeps the oldest unread result until clicked, with an unread count; hidden UI and combat time never discard it. `/ifcnotices` shows every retained outcome and material disposition, and `/ifcnotices clear` acknowledges the queue. The queue retains 32 outcomes and reports overflow explicitly. Duplicate identical outcome delivery does not replay sound or create another notice. Acknowledgements identify exact monotonic sequence numbers, so stale clicks cannot remove the next result.

This is a session notification queue, separate from persistent craft history. Entering a world clears notifications. Only the local client creates presentation and success audio; server completion and material authority remain unchanged.

Native `Expansion CraftNotifications` checks dedupe, detached snapshots, exact/stale acknowledgement, capacity, overflow and host isolation. GPU and live multiplayer remain unrun.

Hovered notification bounds reserve both mouse buttons before native inventory, then restore the original input for acknowledgement and consume its release edges. The notification reserves before the station input layer and restores after its draw, so overlapping panels cannot steal the acknowledgement. World/mod teardown restores any outstanding reservation. Station modals and the recipe journal temporarily hide the retained banner. Outcome labels and command summaries use English/Russian localization rather than raw enums.

The native check also exercises real ItemSlot left/right handlers while input is reserved, outside-bound and ignored-interface behavior, nested layer ordering, teardown, and actual HJSON/Language lookups in both languages.
