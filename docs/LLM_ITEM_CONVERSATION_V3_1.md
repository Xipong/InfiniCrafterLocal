# LLM Item Conversation V3.1

Status: implemented contract.

## 1. Purpose

V3.1 keeps the useful multipass item-authoring topology without replaying one ever-growing Chat Completions transcript.

The optimization target is not the smallest possible prompt. Every stage receives enough accepted product truth to make its decision correctly. What is removed is competing or irrelevant context:

- the original Planner system prompt;
- the full parent/engine catalog when a bounded stage does not need it;
- rejected Planner drafts;
- a stale full-item JSON after validators or repairs changed the accepted artifact;
- transport state from another provider/profile/item.

Correctness is carried by self-contained stage dossiers. `/responses`, `previous_response_id`, and cached input tokens are optional transport optimizations.

## 2. Item-level routing

A cache miss acquires one `LlmItemLease` before Planner execution.

```text
new item A -> LLM profile 1 -> all normal passes
new item B -> LLM profile 2 -> all normal passes
new item C -> LLM profile 3 -> all normal passes
new item D -> LLM profile 1 -> ...
```

Selection is round-robin across enabled profiles. LLM 1 is the existing provider configuration; LLM 2-4 are optional GUI/config profiles.

Normal rule:

```text
one item lease == one active provider/base URL/API key/model
```

Emergency rule for unstable providers:

1. A transport, auth, quota, server, malformed-envelope, or compatible endpoint failure marks the current profile unhealthy.
2. The same current-stage dossier is retried on the next profile in circular order.
3. `previous_response_id` is cleared because response IDs never cross profiles.
4. The lease is pinned to the successful replacement profile for all remaining stages.
5. The failed profile enters a configurable cooldown and is skipped by new item leases.

This emergency switch is safe because each stage dossier is self-contained. It is not ordinary load balancing inside an item.

## 3. Stage topology

```text
Planner
  -> Promise Truth Gate / Planner re-author when required
  -> strict gameplay/runtime validation
  -> Runtime Repair dossier when required
  -> Name Repair dossier when required
  -> Genome Repair dossier when required
  -> accepted executable item
  -> Visual Director dossier
  -> image generation and visual adoption
  -> VFX Director dossier
  -> VFX validation/repair/adoption
  -> sanitized cache/world/game delivery
```

Planner is the only broad item author. Repairers own narrow validated patches. Visual owns image-facing semantics. VFX owns the finite runtime VFX manifest. C# remains the final bounded execution/rendering authority.

## 4. Common stage envelope

Every normal downstream LLM request uses exactly two explicit Chat roles before transport conversion:

```json
[
  {
    "role": "system",
    "name": "<stage>_contract",
    "content": "stage-specific authority and output contract"
  },
  {
    "role": "user",
    "name": "<stage>_context",
    "content": "{ authoritative stage dossier }"
  }
]
```

The user dossier includes `agentHandoff`:

```json
{
  "schema": "infini.llm-handoff.v1",
  "previousSpeaker": "item_planner",
  "currentSpeaker": "runtime_validator",
  "nextSpeaker": "runtime_repairer",
  "causeBy": "runtime_contract_validation_failed",
  "artifactSource": "currentItem"
}
```

`name` and `agentHandoff` are attribution/trace aids. Correctness does not depend on a provider implementing named participants. Stage system authority, the current dossier, strict validators, and adoption gates are authoritative.

## 5. Dossier sufficiency

### Planner

Planner receives the broad authoring packet:

- both parent cards and mechanical roles;
- recipe identity;
- supported gameplay/runtime vocabulary;
- finite engine-call contract;
- required full-item JSON boundary.

The Planner packet may be large because this stage chooses the item. Prompt-size limits remain test/release usability gates, not runtime craft rejection.

### Runtime Repair

Runtime Repair receives:

- current accepted category/gameplay/runtimePlan/attack;
- exact validator errors, warnings, raw strict errors, and failed call contracts;
- both parent cards;
- engine runtime contract needed to repair executable calls;
- narrow `repairPatch` schema;
- explicit fields it must not re-author.

It never needs the old Planner transcript. It returns only `repairPatch`.

### Name Repair

Name Repair receives:

- current item name, tooltip, concept, category, and tags;
- parent names;
- inferred identity/category evidence;
- forbidden generic/bare-parent outcomes;
- one-field name response contract.

It may change only the name.

### Genome Repair

Genome Repair receives:

- current accepted item identity and combat/gameplay/runtime surface;
- exact genome defects;
- both parent cards;
- finite required genome shape and supported execution vocabulary.

It returns only the combat genome repair surface.

### Visual Director

Visual receives the accepted post-validation item, not the raw Planner draft:

- compact parent identity/mechanical cards;
- accepted child identity, category, concept, tags, gameplay and attack topology;
- visual intent and runtime presentation evidence;
- item/projectile/effect sprite requirements;
- no-invention constraints and required visual JSON shape.

Visual never receives `_llmHistory`, debug blobs, world cache data, or the entire Planner engine catalog.

### VFX Director

VFX receives the accepted post-Visual/post-runtime item through `vfxInputPacket`:

- compact parents;
- child item identity and executable attack/runtime topology;
- accepted visual/VFX intent and palette/material evidence;
- finite allowed VFX surface, slot budget, and required manifest shape;
- explicit prohibition on inventing gameplay.

VFX repair appends only the invalid VFX artifact plus exact validator feedback. If bounded VFX repair fails, procedural VFX is a cosmetic safety net; it never takes over gameplay ownership.

## 6. Planner provenance and malformed history

`_llmHistory` still exists transiently for three reasons:

- prove that a live Planner artifact really existed;
- keep replay/debug fixtures attributable;
- fail closed if live provenance is malformed or unexpectedly lost.

It is not serialized into downstream model requests and is stripped before persistence/delivery.

Policy:

```text
valid transient Planner provenance
  -> authoritative V3.1 stage dossier

history entirely absent on genuine legacy/non-live data
  -> explicit legacy self-contained dossier

live Planner marker + absent/malformed history
  -> fail closed for required stages; never silently downgrade
```

## 7. Responses API and cache behavior

Each profile has an API mode:

- `auto`: probe `/responses`; remember capability; fall back to `/chat/completions` on incompatibility;
- `responses`: prefer `/responses`, still fall back to Chat for correctness;
- `chat_completions`: skip Responses probing.

The transport maps the common stage envelope to Responses input:

- system content -> `instructions`;
- non-system messages -> `input`;
- `max_tokens` -> `max_output_tokens`;
- JSON response format -> `text.format` when representable;
- supported reasoning effort -> `reasoning.effort`.

A successful Responses result is normalized back to the existing Chat Completions envelope so stage code has one response parser.

`previous_response_id` rules:

1. scoped to one `LlmItemLease`;
2. scoped to one exact profile/provider/base/model;
3. sent only for clean two-message stage dossiers;
4. never sent for Planner re-author or VFX repair requests that already contain their own assistant/validator turns;
5. cleared on Responses incompatibility or profile failover;
6. never required for correctness.

Usage trace normalizes both APIs to:

- input tokens;
- output tokens;
- cached input tokens;
- API mode;
- response ID / previous response ID when present;
- profile ID.

A returned response ID is not treated as proof of caching or discounted billing. Those are provider telemetry/economics, not product correctness.

## 8. Configuration and GUI

Existing single-provider settings remain LLM 1 and require no migration.

Primary transport:

```text
INFINI_LLM_API_MODE=auto|responses|chat_completions
```

Optional profiles:

```text
INFINI_LLM_POOL_2_ENABLED
INFINI_LLM_POOL_2_PROVIDER
INFINI_LLM_POOL_2_BASE_URL
INFINI_LLM_POOL_2_API_KEY
INFINI_LLM_POOL_2_MODEL
INFINI_LLM_POOL_2_API_MODE
```

The same fields exist for LLM 3 and LLM 4.

Failure handling:

```text
INFINI_LLM_POOL_FAILURE_COOLDOWN_SECONDS=45
```

The GUI LLM tab is vertically scrollable by scrollbar, Windows/macOS wheel, Linux Button-4/Button-5, and wheel events over child Entry/Combobox widgets. Wheel routing is restricted to the visible `ScrollFrame` under the pointer so another hidden tab cannot consume scrolling.

## 9. Observability

Transport events include:

- `LLM item lease acquired/released`;
- selected profile, provider, base URL, model and API mode without exposing keys;
- `LLM usage` with normalized cached-input telemetry;
- Responses compatibility fallback;
- profile failure cooldown;
- item-lease profile switch and reason.

Stage traces include `messageMode=authoritative_stage_dossier_v31` and message summaries. Full secrets never enter trace.

`/health` exposes a non-secret pool snapshot and learned Responses capability per endpoint/model.

## 10. Required invariants

1. A normal item never changes profile between stages.
2. A provider failure may switch the current stage only through the lease owner, then pins the replacement profile.
3. A response ID never crosses profile or item boundaries.
4. Every downstream request remains correct with Responses disabled and no server-side state.
5. No downstream dossier contains `_llmHistory` or rejected Planner drafts.
6. Runtime/Name/Genome repair cannot re-author unrelated item fields.
7. Visual/VFX consume accepted current truth after preceding validation/adoption.
8. Malformed live provenance never silently becomes a legacy standalone path.
9. Cache and provider state affect cost/latency only, never acceptance semantics.
10. Final sanitized data must still pass Python contracts, C# build/contracts, and real delivery/rendering gates.
