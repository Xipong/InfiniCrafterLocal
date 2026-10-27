# Parent source extraction: vanilla and Calamity audit

Audit baseline: IFC `a199c2b715bfd62968378aa5be99bbb882627543` (merged PR #237).
Calamity: official `CalamityTeam/CalamityModPublic`, branch `1.4.4`, commit
`1a8cebd27ec5615316b78f71973446b5528d2b78`, version 2.2.2. Native binary identity
and regeneration instructions are in [the buff contract](native_buff_effect_contract.md).

## Confirmed gaps and disposition

| Path / example | Cause at baseline | Disposition |
|---|---|---|
| Mod item → vanilla buff | `ParentFacts` passed `item.ModItem is null` to the buff reader; `BuffEffectFacts` refused a vanilla buff solely because its carrier was modded | Fixed: select the certified implementation by buff identity and receiver. The graph additionally inspects registered GlobalBuff overrides and field-linked GlobalNPC/ModPlayer consumers as dispatch candidates, without certifying their runtime applicability. |
| ModItem / ModProjectile / attached GlobalItem / GlobalProjectile → NPC.AddBuff | `HitStatusFacts` only admitted native StatusToNPC/StatusNPC catalogs | Added bounded read-only inspection of attached OnHitNPC override bodies. Exact literal or registered generic identity, duration, receiver and source certificate reach the existing parent packet. Unknown identity is not replaced by an ID. |
| Straight-line local copies of a buff identity or duration | Direct call patterns alone miss ordinary locals | Follow the nearest dominating local definition only in a straight-line block without branch entry or address escape. The source graph also retains CFG joins and conditional local definitions; helper arguments/returns have source edges. Address-exposed or over-bound definitions stay explicitly unresolved. |
| Obsidian Skin | An array immunity write made the whole source branch fail the scalar-only matcher | Fixed typed bool-array constant-index writes; flags and the OnFire immunity entry now survive together. |
| Ironskin, Magic Power, Archery, Wrath, Rage | DefenseStat operators, ref getters and StatModifier operations were outside the scalar subset | Fixed recognition of typed field/ref operations. Preserve exact operator calls and operands without inventing final stats. More complex forms such as Sharpened are retained as typed source expressions in the graph, including ref getters with DamageClass arguments; omitted enclosing branches remain explicit. |
| Brimstone Flames and similarly structured mod buffs | Native buff catalog had no mod implementation analysis. Calamity separates registration/data, Update flags and GlobalNPC consumers | Added typed Update writes and exact Type-indexed registration → static field → initializer links, without executing those methods. The graph follows exact fields through registration, static initialization, helper calls and registered consumer hooks. This preserves scaling expressions and conditions, without turning data into final DPS. |
| Daybreak, Oiled, Dryad effects and other conditional vanilla NPC effects | NPC recognizer accepts only a flat prefix of DOT consumers and two defense consumers; projectile counts and interacting state are outside it | The graph links flag-gated native regen/defense source slices, retaining typed field/call/arithmetic expressions, counts, conjunctions and target/world conditions. Oiled and Daybreak have executable source-reader regressions. No unconditional DPS is derived. |
| Brimstone Sword right-click, mod magic/summon weapons | NativeShootReference excludes ModItem. The separate mod shooting-hook inspection is reached through AmmoRaw only when useAmmo > 0 | Shoot, ModifyShootStats, AltFunctionUse, CanUseItem and CanShoot overrides are independent item roots in parentSourceGraph. Ref writes and conditional source flow are retained even with useAmmo=0 or shoot=0. These are source candidates, not a guaranteed attack. |
| Brimstone Sword → Brimblast / BrimstoneSwordExplosion | Default projectile capture follows item.shoot, not NewProjectile calls in OnHitNPC, AI, OnKill or helpers | NewProjectile/NewProjectileDirect requests in hooks and helpers seed registered projectile samples and their AI/hit/kill/spawn hooks. Native type/aiStyle equality windows and bounded Projectile helper bodies supplement mod hooks. Identities are deduplicated; missing samples, dynamic expressions, cycles, unvisited dispatch shapes and source bounds are explicit. |
| Mod equipment, armor sets and placed effects | EquipmentFacts and EnvironmentFacts explicitly reject ModItem; vanilla equipment catalog covers selected GrantArmorBenefits/UpdateArmorSets branches | Actual UpdateEquip/UpdateAccessory/UpdateArmorSet/IsArmorSet and inventory/use overrides are item roots. Placed ModTile and registered GlobalTile hooks have separate roots with placement applicability unresolved; equip flags do not synthesize effects. |
| OnHitPvp / OnHitPlayer / UseItem / ModPlayer hit hooks | Different events and receiver types are not covered by the NPC-hit source reader | Item OnHitPvp, projectile OnHitPlayer, UseItem and registered ModPlayer shooting/hit overrides retain their own event/signature/receiver. NPC.AddBuff and Player.AddBuff requests resolve separately. Registered ModPlayer roots are dispatch candidates, not observed player execution. |
| Immunity, reapplication and loaded-mod changes to vanilla | Native certificates describe original source bytes, not dispatch outcomes or in-memory detours | A separate graph layer reads this buff's current GrantImmunityWith relationship, certified native AddBuff admission/refresh source, and receiver-specific ModBuff/GlobalBuff Update/ReApply source. Field-linked loaded consumers cover changes to vanilla too. Actual target immunity and detoured dispatch remain unknown; AddBuff remains a request. |
| Unsupported native version / no catalog row | Several capture owners return null for either case | nativeCatalogCoverage distinguishes a mod host, an unavailable native certificate, a partial certified record and a missing catalog record. Method, roster, identity, graph and source-slice limits have explicit refusal reasons. Missing coverage never proves absence; certificates are unchanged. |

## Actual native coverage, not a claim about all items

The committed source report proves 74 of 100 direct NPC.AddBuff sites in
Projectile.StatusNPC and 9 of 20 in Player.StatusToNPC. These are call-site
counts inside those two methods, **not percentages of supported projectiles or
items**. Native Player.UpdateBuffs analysis identifies 254 literal branches;
after this change 96 player records contain supported statement fragments (77 before); unsupported literal player branches fall from 177 to 158.
NPC effect records contain 10 numeric-fragment rows and 18 unsupported/flag-only
rows. These counts do not cover every dispatch shape, helper or downstream effect.

## Original Calamity experiment (before the source-graph extension)

The full unmodified source assembly was compiled, then the real BrimstoneSword,
BrimstoneSwordProj and BrimstoneFlames classes were registered in an isolated
CPU fixture. Other relevant projectile identities were registered too. The fixture
uses tML's actual item/projectile defaults and IFC's actual GeneratorClient.Prepare.
It does not load all Calamity globals, textures, a world or the game loop. Assigned
numeric IDs are fixture-local and must not be copied into production mappings.

Before: tooltip name only; neither the item nor projectile delivered hit-status
source facts. After: both deliver the currently registered BrimstoneFlames identity,
NPC receiver and requested durations **300 / 180 ticks**, respectively. Independent
execution of the real OnHitNPC methods recorded those same AddBuff arguments.
The reader itself never invokes OnHitNPC, ModContent.BuffType or buff update hooks.

Actual Prepare → Author request construction retains both observations and their
partial source-semantics status in json_schema and json_object modes. Dossier:
**200,263 Unicode characters**, previously 195,692, below the unchanged 225,000 guard.
There is no loaded-buff registry in the request. This is delivery verification;
no model request, generated item quality claim, game-loop or multiplayer test.

BrimstoneFlames' source data sets EnemyLostRegen=60 and HeatDebuffScaling=1.
CalamityGlobalNPC and DebuffData apply scaling and target-specific changes. These
values now reach the parent packet as explicit initializer writes linked to this
buff's registration. They are not proved effect operations or unconditional 30 DPS.

The same production source reader was also applied to unique OnHitNPC methods
declared by concrete ModItem/ModProjectile types in the compiled Calamity assembly.
Of 1,049 unique methods, 743 contain 839 recognized direct request statements;
30 other direct sites remain unresolved and 2 entire bodies are outside the bound.
These counts do not prove the absence of requests in helper methods. This surveys
source shapes only, not runtime admission or every buff's registered identity.
The mod-buff reader was also checked against BrimstoneFlames, Plague,
GodSlayerInferno and SulphuricPoisoning: each retained its own registration and
initializer writes through the same generic matcher. The original direct-call reader had these remaining examples; the graph now retains their dynamic expressions, conditional alternatives and helper bodies as source, without inventing evaluated values:

- BasicPlagueBee: duration from Projectile.ai[1].
- BlazingStarThatDoesNotHeal: duration returned by CalamityUtils.SecondsToFrames.
- SulphuricAcidBubbleFriendly: duration 150/120 selected by fromArmour, behind a localAI gate.
- SolsticeBeam: Daybreak/Nightwither identity selected by Main.dayTime.
- Large/exception-bearing bodies: retained as unsupported rather than partly guessed.

## Source graph and remaining epistemic limits

`CaptureParentNativeFacts` captures `parentSourceGraph` once for each non-generated
parent. Root/runtimeFacts/fingerprint projections share that observation. Python
copies it literally into the Author dossier in both provider formats, using the
existing exact-value interner. Generated parents do not borrow proxy source.
The native operation catalogs remain unchanged and keep their original certificates.

- `nodes` deduplicate exact compiled methods. `members` and `modules` intern exact
  metadata identities; every method has an IL SHA256. A `values` row is
  `[opcode, operand, input-definition IDs, block offset]`, with `{member:N}` pointing
  to the metadata table. Field storage and method return types remain explicit.
- Local definitions and predecessor-stack joins retain alternatives. The source
  decoder performs stack/data/control dependency analysis, **never execution** of
  arbitrary IL, hooks, operators, constructors, getters or helpers. Helper source
  edges retain caller input IDs; virtual targets remain candidate bodies.
- Block rows are `[offset, successors, branch-value ID, enclosing branch IDs]`.
  A source statement requires control to reach it. External CFG edges, exception
  regions intersecting a slice, address escapes, unresolved locals and omitted
  enclosing conditions are explicit, never converted to a probability or effect.
- Field reads connect written flags/data to registered GlobalNPC/ModPlayer consumer
  overrides, including reads through bounded same-assembly helper chains. This is
  a source dependency, not proof that a target's global or player's state is active.
- The graph is finite: 48 method nodes, 192 edges, helper depth 6, 1,024 inspected
  methods, 262,144 IL bytes per method, and a 16,000-character source budget.
  Method slices, local/control dependencies and native equality windows also have
  bounds. Oversize source keeps a refusal/certificate or unresolved edge. No bound
  is advertised as complete coverage, and no global content registry is delivered.

The old implementation-order items now have one shared capture path. Remaining
unknowns are explicit source-analysis boundaries: unsupported/dynamic dispatch,
actual immunity/admission, runtime detours and the final interacting game state.
The graph does not execute inherited mechanics or prove final DPS. A flag write
still does not define its gameplay meaning. Author chooses the new composition;
no item/mod-name router, generated behavior preset or extra model pass is added.

## Verification

The original Calamity experiment and its numerical coverage counts above belong
to the first PR commit. They were not rerun against a newly loaded Calamity build
for the graph extension and must not be treated as its integration coverage.

The extension compiles all canonical C# sources against the official tModLoader
2026.08.3.0 assembly. Three registered native checks exercise actual source bodies:
non-ammo shooting through helper arguments, child AI/kill/PvP hooks and cycles,
conditional buff identities/durations, equipment/stat-ref operations and armor-set
conditions, field-linked GlobalNPC consumers, ModBuff registration/initializers,
Oiled/Daybreak/Sharpened, and Cluster Grenade's native child-spawn source. Capture
counters prove hooks, helper bodies, static data and constructors are not invoked.
References are checked for closure after graph truncation.

Author transport regressions retain graph IDs, typed zero values, receiver/event
separation, unknowns and multiplicity in both json_schema/json_object modes. A real
Prepare(MiningPotion, SpelunkerPotion) export passes the actual Author builder at
206,911 characters under the unchanged 225,000 guard. The synthetic multi-event
source graph also fits the actual builder, and source packets are never mutated.

Final acceptance: all 6,700 Python cases and all 17 static validation gates pass.
The native parent run has 25 passing checks, including all three new graph
checks. Five existing native parent checks require
MonoMod runtime detours; this container cannot enumerate the CLR JIT library via
/proc, so those executions fail before their assertions. This is an environment
limitation, not a passing native oracle. No game, model, GPU/world or multiplayer
session was run.
