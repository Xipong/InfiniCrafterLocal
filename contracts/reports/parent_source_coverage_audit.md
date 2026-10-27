# Parent source extraction: vanilla and Calamity audit

Audit baseline: IFC `a199c2b715bfd62968378aa5be99bbb882627543` (merged PR #237).
Calamity: official `CalamityTeam/CalamityModPublic`, branch `1.4.4`, commit
`1a8cebd27ec5615316b78f71973446b5528d2b78`, version 2.2.2. Native binary identity
and regeneration instructions are in [the buff contract](native_buff_effect_contract.md).

## Confirmed gaps and disposition

| Path / example | Cause at baseline | Disposition |
|---|---|---|
| Mod item → vanilla buff | `ParentFacts` passed `item.ModItem is null` to the buff reader; `BuffEffectFacts` refused a vanilla buff solely because its carrier was modded | Fixed: select the certified implementation by buff identity and receiver. This still describes vanilla source fragments, not changes made by GlobalBuff/ModPlayer/GlobalNPC. |
| ModItem / ModProjectile / attached GlobalItem / GlobalProjectile → NPC.AddBuff | `HitStatusFacts` only admitted native StatusToNPC/StatusNPC catalogs | Added bounded read-only inspection of attached OnHitNPC override bodies. Exact literal or registered generic identity, duration, receiver and source certificate reach the existing parent packet. Unknown identity is not replaced by an ID. |
| Straight-line local copies of a buff identity or duration | Direct call patterns alone miss ordinary locals | Follow the nearest dominating local definition only in a straight-line block without branch entry or address escape. Conditional definitions remain unresolved. |
| Obsidian Skin | An array immunity write made the whole source branch fail the scalar-only matcher | Fixed typed bool-array constant-index writes; flags and the OnFire immunity entry now survive together. |
| Ironskin, Magic Power, Archery, Wrath, Rage | DefenseStat operators, ref getters and StatModifier operations were outside the scalar subset | Fixed recognition of typed field/ref operations. Preserve exact operator calls and operands without inventing final stats. More complex forms such as Sharpened remain open. |
| Brimstone Flames and similarly structured mod buffs | Native buff catalog had no mod implementation analysis. Calamity separates registration/data, Update flags and GlobalNPC consumers | Added typed Update writes and exact Type-indexed registration → static field → initializer links, without executing those methods. Downstream consumer/scaling interpretation remains open; source data is not final DPS. |
| Daybreak, Oiled, Dryad effects and other conditional vanilla NPC effects | NPC recognizer accepts only a flat prefix of DOT consumers and two defense consumers; projectile counts and interacting state are outside it | Still open. Preserve counts, conjunctions, world/target conditions and contribution units. Do not report a single unconditional DPS. |
| Brimstone Sword right-click, mod magic/summon weapons | NativeShootReference excludes ModItem. The separate mod shooting-hook inspection is reached through AmmoRaw only when useAmmo > 0 | Still open. Shooting source inspection needs an entry independent of ammo use, including alt-use gates and type rewrites. The shoot field alone is not the attack. |
| Brimstone Sword → Brimblast / BrimstoneSwordExplosion | Default projectile capture follows item.shoot, not NewProjectile calls in OnHitNPC, AI, OnKill or helpers | Still open. Build a bounded, deduplicated reachable source graph rooted in the parent, with explicit edge conditions and truncation. |
| Mod equipment, armor sets and placed effects | EquipmentFacts and EnvironmentFacts explicitly reject ModItem; vanilla equipment catalog covers selected GrantArmorBenefits/UpdateArmorSets branches | Still open. Analyze actual equip/update/set/place hook ownership; an accessory flag or base defense does not describe its effects. |
| OnHitPvp / OnHitPlayer / UseItem / ModPlayer hit hooks | Different events and receiver types are not covered by the NPC-hit source reader | Still open. Keep event/receiver separate. BrimstoneSword has a distinct player-target OnHitPvp implementation. |
| Immunity, reapplication and loaded-mod changes to vanilla | Native certificates describe original source bytes, not dispatch outcomes or in-memory detours | Still open as a separate coverage layer. Calamity SulphuricPoisoning registers GrantImmunityWith relationships; AddBuff is only a request. |
| Unsupported native version / no catalog row | Several capture owners return null for either case | Still open: compact coverage reasons should distinguish unavailable analysis from proved absence. Removing certificate checks would not fix coverage. |

## Actual native coverage, not a claim about all items

The committed source report proves 74 of 100 direct NPC.AddBuff sites in
Projectile.StatusNPC and 9 of 20 in Player.StatusToNPC. These are call-site
counts inside those two methods, **not percentages of supported projectiles or
items**. Native Player.UpdateBuffs analysis identifies 254 literal branches;
after this change 96 player records contain supported statement fragments (77 before); unsupported literal player branches fall from 177 to 158.
NPC effect records contain 10 numeric-fragment rows and 18 unsupported/flag-only
rows. These counts do not cover every dispatch shape, helper or downstream effect.

## Calamity experiment

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
initializer writes through the same generic matcher. Concrete remaining examples:

- BasicPlagueBee: duration from Projectile.ai[1].
- BlazingStarThatDoesNotHeal: duration returned by CalamityUtils.SecondsToFrames.
- SulphuricAcidBubbleFriendly: duration 150/120 selected by fromArmour, behind a localAI gate.
- SolsticeBeam: Daybreak/Nightwither identity selected by Main.dayTime.
- Large/exception-bearing bodies: retained as unsupported rather than partly guessed.

## Next implementation order

1. Extend the typed stat/ref and local-copy recognizers with bounded helper and
   conditional-expression analysis; retain alternatives instead of choosing an arm.
2. Parent-reachable projectile, buff and consumer graph, including mod data tables
   and modifications of vanilla effects. Scope and completeness belong to each
   observation; a flag write alone does not prove its gameplay meaning.
3. Shooting without ammo, equipment/use/PvP/ModPlayer event roots and immunity/
   refresh dispatch. Record unresolved edges explicitly.

Use one source node per identical observation with references, not repeated source
prose or a global content catalog. Never select runtime primitives or generated
behavior from item names. The Author still owns the new item's composition.

## Verification

Canonical-source C# build and 27 parent native CPU checks pass. The complete
Python shard run passed (6,695 cases); the affected source/transport suites were
rerun after the final analyzer additions (43 cases). All 17 static validation
gates pass. The Calamity experiment above uses the actual compiled source and
actual Prepare/Author builders; it does not replace the production reader.
