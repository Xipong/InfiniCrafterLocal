"""Find existing workbench dependencies without installing or changing them."""
from __future__ import annotations

import json
import os
from pathlib import Path


def _restored_references(root: Path):
    """Use only the tML package selected by this checkout's NuGet restore."""
    assets = root / 'ModSources/InfiniCrafterLocal/obj/project.assets.json'
    if not assets.is_file():
        return None, None
    try:
        data = json.loads(assets.read_text(encoding='utf-8'))
        libraries = [entry for name, entry in data['libraries'].items()
                     if name.lower().startswith('tmodloader/')]
        if len(libraries) != 1:
            return None, 'project.assets.json must select exactly one tModLoader package'
        relative = libraries[0]['path']
        paths = {(Path(folder) / relative / 'lib/net8.0').resolve()
                 for folder in data['packageFolders']
                 if (Path(folder) / relative / 'lib/net8.0/tModLoader.dll').is_file()}
        if len(paths) > 1:
            return None, 'multiple restored tModLoader references found; set INFINI_TML_REFERENCE_DIR'
        return (next(iter(paths)), None) if paths else (None, None)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, 'cannot inspect project.assets.json: ' + str(exc)


def discover(root: Path, environ=None, home=None):
    """Return an effective child environment and discovery notes, without mutation.

    Explicit environment values always win, even if they are invalid. We only
    auto-select unambiguous conventional locations; native validation remains
    responsible for checking the contents and asset hashes.
    """
    env = dict(os.environ if environ is None else environ)
    home = Path.home() if home is None else Path(home)
    notes = {}

    def choose(name, path, source):
        if name in env:
            notes[name] = 'environment'
        elif path is not None:
            env[name] = str(path)
            notes[name] = source

    reference, error = _restored_references(root)
    choose('INFINI_TML_REFERENCE_DIR', reference, 'restored project.assets.json')
    if error and 'INFINI_TML_REFERENCE_DIR' not in env:
        notes['referenceDiscovery'] = error

    deps = root / 'artifacts/dependencies'
    if (deps / 'ParticleLibrary/ParticleLibrary.dll').is_file() and (deps / 'Luminance/bin/Debug/net8.0/Luminance.dll').is_file():
        choose('INFINI_TML_DEPS_SRC', deps, 'artifacts/dependencies')
    else:
        choose('INFINI_TML_DEPS_SRC', None, '')
    for var, directory, marker in [
        ('INFINI_PLAYER_ASSET_DIR', 'player-assets', 'Images/MagicPixel.png'),
        ('INFINI_PARTICLE_ASSET_DIR', 'particle-assets', 'Assets/Textures/Star.png'),
    ]:
        candidate = deps / directory
        choose(var, candidate if (candidate / marker).is_file() else None, 'artifacts/dependencies/' + directory)

    # An explicit installation root is useful for non-Steam installs. If not
    # provided, only the standard Linux Steam path is considered.
    installation = Path(env['INFINI_TML_DIR']).expanduser() if 'INFINI_TML_DIR' in env else home / '.local/share/Steam/steamapps/common/tModLoader'
    origin = 'INFINI_TML_DIR' if 'INFINI_TML_DIR' in env else 'standard Linux Steam installation'
    native = installation / 'Libraries/Native/Linux'
    content = installation / 'Content'
    choose('INFINI_TML_NATIVE_DIR', native if (native / 'libFNA3D.so.0').is_file() else None, origin)
    choose('INFINI_TML_CONTENT_DIR', content if (content / 'PixelShader.xnb').is_file() else None, origin)
    return env, notes
