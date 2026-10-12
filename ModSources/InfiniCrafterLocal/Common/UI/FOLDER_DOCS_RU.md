# Common/UI

Client UI systems.

- `InfiniCraftStationUISystem.cs` draws one normal or 2–3 command-unlocked craft cards. Every card has its own explicit A/B slots, Craft control, craft-timer bar and status; each lane stays usable while another lane is running.
- Readiness is owned by `InfiniCraftPlayer.MultiDev.cs`: one reason distinguishes unavailable station authority, a closed/busy hearth, pending item-transfer confirmation and missing inputs. Admission still refreshes authority at its existing owner; drawing and hover only observe it, never park/restore material claims or cancel work.
- Hover a hearth, its status or Forge control for complete accepted parent/input names, current stage, actual elapsed craft ticks and the explicit timer disclaimer. Native `Main.instance.MouseText` is reused; no model percentage or ETA is inferred.
- `StationPanelBounds` removes fixed minimum margins and narrows the panel (minimum 280 px) without moving the fixed input/button columns. `StationLaneBounds` supplies identical draw/hit-test rectangles. CPU checks cover 1280×480, 800×480, 400×720 and exact panel-sized viewports. Heights below the panel, widths below 280 px, UI-scale transformations and GPU/native inventory drawing remain separate acceptance; no paging/redesign is introduced.

UI only manipulates `InfiniCraftPlayer` state. It does not run generation directly and has no hidden inventory item selection.
