# Live home destination and recall lifecycle (#183)

A held recall binding shows whether it will return to a valid bed or current world spawn, explains a missing/removed bed, reports destination coordinates and distance, and shows the shared movement lockout. The same live native bed check supplies both inspection and execution. World-boundary/whole-body validation refuses invalid destinations without starting cooldown.

Successful recall records a read-only journey receipt, preserves native Teleport's hook cleanup and primary fall reset, stops previous velocity and resets the secondary fall sample. Inspection cannot teleport, reserve cooldown or cache a stale bed/spawn. Journey presentation is cleared on world entry.

Native blink/recall integration checks exercise actual Player.Teleport, missing-bed fallback, matching preview/arrival, changing world spawn, both fall samples and zero arrival momentum. Live-world and multiplayer smoke remain unrun.
