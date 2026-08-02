# Common/UI

Client UI systems.

- `InfiniCraftStationUISystem.cs` draws one normal or 2–3 command-unlocked craft cards. Every card has its own explicit A/B slots, Craft control, progress and status; each lane stays usable while another lane is running.

UI only manipulates `InfiniCraftPlayer` state. It does not run generation directly and has no hidden inventory item selection.
