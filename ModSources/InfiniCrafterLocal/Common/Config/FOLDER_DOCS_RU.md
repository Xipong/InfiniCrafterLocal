# Common/Config

tModLoader `ModConfig` classes.

- `InfiniGameplayQolConfig.cs` — generated melee on-hit toggle, inventory asset prefetch, runtime sprite cache limits.
- `InfiniVfxClientConfig.cs` — client-side VFX presentation toggles/multipliers.

Configs are read defensively; runtime has bounded safe defaults if config access fails.
