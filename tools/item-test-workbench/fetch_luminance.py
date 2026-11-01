"""Install pinned Luminance reference and original particle textures for the workbench."""
from __future__ import annotations

from pathlib import Path

from fetch_vfx_assets import download, install_file

# DLL was used in the verified native CI run; textures are pinned to the
# upstream Git tree. Their object IDs cover the exact Git blob bytes.
COMMIT = "5b4095a5d59e901ac171208f67a1d1e934c69373"
DLL_URL = "https://github.com/LucilleKarma/Luminance/releases/download/v1.0.12/Luminance.dll"
DLL_SHA256 = "a0d91baa68bc7ae50404c5a0ab550d5e267a6e9b0a685643d6e7233e7c74a73e"
DLL_BYTES = 188416
FILES = {
    "Assets/GreyscaleTextures/BloomCircleSmall.png": (7607, "a1c0bd7510d6bdcd3090202a9af1fe4b96f1a815"),
    "Assets/GreyscaleTextures/BloomFlare.png": (134051, "c92cf061d2363052c3803c64d8b4d534ebae4053"),
    "Assets/GreyscaleTextures/BloomLine.png": (1775, "8c9928084ae91e461a74c296664152fae1af33ad"),
    "Assets/GreyscaleTextures/ChromaticBurst.png": (449243, "8813b35100c34270de5ecab7df9ff0c380f27675"),
    "Assets/GreyscaleTextures/ShineFlare.png": (54435, "5e8c572de26604dbfded6a31d0501fcda5b7811a"),
    "Assets/Noise/DendriticNoiseZoomedOut.png": (117168, "41d5fd5d44a63735f357c319dee807b1fa049d2e"),
    "Assets/Noise/TurbulentNoise.png": (254495, "56453cf3becf33265d3d7b0c9a7ad197a3be9f7d"),
    "Assets/Noise/WavyBlotchNoise.png": (126621, "71df21c2eff82130ca496321c255674230ab886f"),
    "LICENSE": (1064, "1095ed6f10eb4a3b070a1d7baf8f47acd5a15687"),
}


def setup_luminance(deps_root: Path, fetch=download) -> dict:
    root = deps_root.absolute()
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError("Dependency root must be a directory, not a symlink")
    dll = {"path": "Luminance/bin/Debug/net8.0/Luminance.dll", "sourceURL": DLL_URL,
           "bytes": DLL_BYTES, "sha256": DLL_SHA256}
    installed = int(install_file(root, dll, fetch))
    assets = root / "luminance-assets"
    for path, (size, blob) in FILES.items():
        entry = {"path": path, "bytes": size, "gitBlobSha1": blob,
                 "sourceURL": f"https://raw.githubusercontent.com/LucilleKarma/Luminance/{COMMIT}/{path}"}
        installed += int(install_file(assets, entry, fetch))
    return {"status": "verified", "package": "Luminance", "version": "1.0.12",
            "resourceCommit": COMMIT, "downloaded": installed, "verifiedFiles": len(FILES) + 1,
            "environment": {"INFINI_TML_DEPS_SRC": str(root), "INFINI_LUMINANCE_ASSET_DIR": str(assets)},
            "runtimeReady": False, "note": "Original resources verified; native initialization is a separate check."}
