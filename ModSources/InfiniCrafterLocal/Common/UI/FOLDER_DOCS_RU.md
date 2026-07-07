# Common/UI

Client UI systems.

- `InfiniCraftStationUISystem.cs` draws the inventory InfiniCraft station: two explicit input slots, Craft button, Clear inputs, progress/status bar.

UI only manipulates `InfiniCraftPlayer` state. It does not run generation directly and has no hidden inventory item selection.
