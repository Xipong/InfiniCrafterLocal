"""The direct installed-API call needs an explicit tML runtime dependency floor."""
from suite_paths import REPO_ROOT


def test_particle_library_runtime_reference_requires_offscreen_context_api():
    manifest = REPO_ROOT / "mod/InfiniCrafterLocal/build.txt"
    fields = {key.strip(): value.strip() for key, value in
              (line.split("=", 1) for line in manifest.read_text().splitlines() if "=" in line)}
    references = [part.strip() for part in fields["modReferences"].split(",")]
    particle = next(part for part in references if part.split("@", 1)[0] == "ParticleLibrary")
    version = tuple(int(part) for part in particle.split("@", 1)[1].split("."))
    assert 2 <= len(version) <= 4
    assert version + (0,) * (4 - len(version)) >= (3, 2, 1, 0)
