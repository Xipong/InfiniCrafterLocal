"""The direct installed-API call needs an explicit tML runtime dependency floor."""
from pathlib import Path


def test_particle_library_runtime_reference_requires_offscreen_context_api():
    manifest = Path(__file__).resolve().parents[2] / "ModSources/InfiniCrafterLocal/build.txt"
    fields = {key.strip(): value.strip() for key, value in
              (line.split("=", 1) for line in manifest.read_text().splitlines() if "=" in line)}
    references = [part.strip() for part in fields["modReferences"].split(",")]
    particle = next(part for part in references if part.split("@", 1)[0] == "ParticleLibrary")
    assert particle == "ParticleLibrary@3.2.1.0"
    assert "Luminance" in references  # Unchanged compatible dependency, not an invented upgrade.
