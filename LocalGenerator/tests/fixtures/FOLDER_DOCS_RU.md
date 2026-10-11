# LocalGenerator/tests/fixtures

Static test fixtures for combine payloads, author plans, raw LLM output and replay/debug cases.

Fixtures are examples/regression inputs, not the live architecture. Keep them small and representative; do not infer implemented features from fixture prose alone.

`projectile_lifetime_initial_author.json` is the byte-exact initial saved Author answer
from `artifacts/live10-luna6-high-post-pr52-20261011/final-quality/authors/ichor_spider_queen-initial.json`.
Its frozen SHA-256 is checked by the existing captured-replay owner; offline replay
must retain the authored 36000-tick sentry without invoking Gameplay Repair.
This is initial gameplay evidence, not a later accepted Visual/VFX/image result.
