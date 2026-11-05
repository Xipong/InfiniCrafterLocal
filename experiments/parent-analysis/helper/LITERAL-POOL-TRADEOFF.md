# Hypothetical literal sharing: exact size tradeoff

No production changes, new wire version, network or inference. Default Author admission remains RED:325,379 characters versus300,000. Baseline is the exact merged packed final Author dossier from request-context-helper-final-diagnostic/json_object.author.builder.json, using the production compact JSON serialization (325,379 characters /325,394 UTF-8 bytes).

Two purely diagnostic pool encodings were measured. Both preserve JSON types, array order/multiplicity and every mechanic. Each resulting dossier includes its pool and an explicit recursive decoding rule. Literal tooltip/generated-parent fields are excluded. All tested scenarios reconstruct the original dossier exactly via a deterministic decoder. This proves lossless computer decoding, NOT model understanding or production compatibility.

## Best measured results (rule and pool overhead included)

Native source scope only (parents + nativeSourceFacts):
- Descriptive {sourceLiteral:N}, strings only: saves8,535 characters.
- Descriptive references, lists only: saves4,311.
- Descriptive references, strings + lists: saves12,168; result313,211 characters,116 pool entries. Still13,211 over limit.
- Short {$v:N}, strings only: saves14,086.
- Short references, lists only: saves8,529.
- Short references, strings + lists: saves20,576; result304,803 characters /304,818 bytes,183 entries. Still4,803 over limit.

Whole dossier scope, including static capability contract and required output-shape instructions:
- Descriptive references, strings + lists: saves21,847; result303,532. Still too large.
- Short references, strings only: saves25,369; result300,010. Still10 over limit.
- Short references, strings + lists: saves35,167; result290,212 characters /290,227 bytes,345 entries.9,788 characters of headroom.

The minimum saving to reach exactly300,000 is25,379 characters;25,380 gets below it. Native-only simple pooling does NOT reach either target in these tested strategies. Broader whole-dossier pooling can, at significant added decoding scope. These are measured constructions, not a proof of globally optimal compression or an assertion that every possible native-only scheme fails.

## Where repetition remains

Examples in final native source context:
- A100-character address-exposed-local limitation string repeats38 times.
- A125-character ai[0] increment expression repeats8 times.
- A106-character source shoot-speed/scale expression repeats8 times.
- requiredPredicates list["b12594","b12868","b12884","b12954"] is37 characters and repeats14 times.
- Many short field expressions and source-kind names repeat enough for short references, but descriptive reference overhead erases much of their savings.

The production cards.py already has exact sourceSameAs/nativeSourceFacts sharing for sufficiently long values (>=128 encoded characters), including strings/lists, before this measurement. Therefore the measured remaining opportunity is chiefly shorter literals or residual repeated packed values, not an untouched pool of all long expressions. attack_tables itself does not gain a generic-value encoding from this diagnostic.

## Decoding and maintenance cost

Native-only pooling adds another reference namespace and nested expansion on top of current sourceSameAs, sameAs and attack table decoding. Whole-dossier sharing crosses beyond native evidence into capability descriptions and output-shape examples and would require disciplined handling of static/developer versus dynamic/user prompt rows. The prompt's expected literal strings/lists become reference objects until decoded. A correct JSON roundtrip does not prove an LLM will follow345 lookups reliably or avoid emitting reference objects as authored runtime values.

Rule overhead measured:306 characters for descriptive references or295 for short references. These are minimal diagnostic rules, not a fully documented/tested production contract. Additional schema/version instructions, malformed-reference behavior, telemetry and model evaluations would reduce headroom and add engineering work. Existing output limits and actual provider response-format schemas were not changed or measured as compressed.

Tradeoff: native-only sharing is a modest optional savings, insufficient by itself. Whole-dossier short references mechanically clear the limit but introduce a broader model-facing protocol with only9,788 characters of measured headroom. Do not silently adopt it merely to make this pair pass. Removing conditional601 profile data is a different lossy strategy and was not done.

## Reproduction / exact evidence

Root:/workspace/scratch/a1b4e2e032eb/ifc-magic-audit-20261105/
- measure_literal_pool.py and measure_literal_shortref_pool.py: isolated read-only experiments.
- literal-pool-opportunity.json and literal-shortref-opportunity.json: all120 configurations (2 encodings ×2 scopes ×3 type selections ×10 length thresholds), exact chars/bytes, entry counts, roundtrip status and example paths.
- literal-pool-hypothetical-dossier.json and literal-shortref-hypothetical-dossier.json: best native-scope hypothetical dossiers, expressly NOT production wire formats.
