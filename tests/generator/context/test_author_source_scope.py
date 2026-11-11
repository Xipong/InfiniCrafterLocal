"""Source choice scopes remain explicit in the emitted mixed Author view."""
import copy
import hashlib

import pytest

from infini_local.pipelines.context.mechanics_context import mechanics_context
from infini_local.pipelines.context.parents import compact_projectile_profile
from tests.generator.context.test_author_mechanics_policy import CODE, fixture


@pytest.mark.parametrize("include_whole_method", [False, True])
def test_identity_assumption_is_named_for_approximate_coverage_only(include_whole_method):
    profile = fixture()
    whole_code = "void OtherAI() { Hook(this); if (type == 2 && active) Emit(928); }"
    if include_whole_method:
        reference = profile["attackReference"]
        program = copy.deepcopy(reference["motion"]["programs"][0])
        program.update(method="Fixture.OtherAI", sourceMethodSha256="d" * 64,
                       metadataToken=0x06000002)
        reference["motion"]["programs"].append(program)
        record = copy.deepcopy(reference["nativeCSharpSource"]["records"][0])
        record.update(method=program["method"], sourceMethodSha256=program["sourceMethodSha256"],
                      metadataToken=program["metadataToken"], id="fixture-whole-source",
                      graphPaths=[["motion", "programs", 1]], code=whole_code,
                      codeSha256=hashlib.sha256(whole_code.encode()).hexdigest(), locations=[],
                      unresolved=["opaque_hook_effects_not_evaluated"])
        reference["nativeCSharpSource"]["records"].append(record)
    before = copy.deepcopy(profile)
    result = mechanics_context({"directProjectile": compact_projectile_profile(profile)})
    assert profile == before
    sources = result["mechanics"]["source"]
    approximate = next(row for row in sources if row["method"] == "Fixture.NativeAI")
    assert approximate["coverage"] == "approximate_identity_ast_method"
    assert approximate["code"] == CODE
    assert approximate["approximation"] == before["mechanicsSource"]["records"][0]["approximation"]
    policies = [row["value"] for row in result["mechanics"]["uncertainty"]["sourceFacts"]
                if row.get("sourcePath") == "directProjectile.authorSourcePolicy"]
    assert len(policies) == 1
    # Public coverage names must delimit the source-choice rule in the actual
    # emitted context. This is not a model-comprehension or prose snapshot test.
    for coverage in ("approximate_identity_ast_method", "approximate_identity_ast_regions", "whole_method"):
        assert coverage in policies[0]
    if include_whole_method:
        whole = next(row for row in sources if row["method"] == "Fixture.OtherAI")
        assert whole["coverage"] == "whole_method"
        assert whole["code"] == whole_code
        assert whole["unresolved"] == ["opaque_hook_effects_not_evaluated"]
        assert "approximation" not in whole and "identitySpecialization" not in whole
