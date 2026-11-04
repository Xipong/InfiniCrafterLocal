"""One-time configuration migration, never legacy runtime routing.

Only this boundary accepts old names. Receipts contain names and hashes, never
setting values. File backups preserve exact input bytes; environment originals
are retained privately in this process, never written to persistent OS settings.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping, MutableMapping

from infini_local.core.env_file import FORMAT_HEADER, config_format, encode_value, parse_env_text

SIMPLE_ALIASES = {
    'INFINI_LLM_REAUTHOR_TEMPERATURE': 'INFINI_LLM_REPAIR_TEMPERATURE',
    'INFINI_LLM_FALLBACK_NETWORK_FAILS': 'INFINI_LLM_NETWORK_ATTEMPTS',
    'INFINI_OPENAI_COMPAT_IMAGE_BASE_URL': 'INFINI_IMAGE_API_BASE_URL',
    'INFINI_OPENAI_COMPAT_IMAGE_API_KEY': 'INFINI_IMAGE_API_KEY',
    'INFINI_OPENAI_COMPAT_IMAGE_MODEL': 'INFINI_IMAGE_API_MODEL',
    'INFINI_OPENAI_COMPAT_IMAGE_SIZE': 'INFINI_IMAGE_API_SIZE',
    **{f'INFINI_PIXEL_{suffix}': f'INFINI_COMFYUI_{suffix}'
       for suffix in ('LORA_NAME', 'LORA_WEIGHT', 'TRIGGER')},
    'INFINI_ITEMS_DUMP': 'INFINI_ITEMS_RUNTIME_DUMP',
    'INFINI_PROJECTILES_DUMP': 'INFINI_PROJECTILES_RUNTIME_DUMP',
}
FALLBACK_SUFFIXES = ('PROVIDER', 'MODEL', 'BASE_URL', 'API_KEY', 'OPENROUTER_PROVIDER')
_PROVIDER_ALIASES = {'or': 'openrouter', 'openai': 'openai_compat', 'api': 'openai_compat',
                     'remote': 'openai_compat', 'lmstudio': 'local', 'lm_studio': 'local', 'ollama': 'local'}
_IMAGE_ALIASES = {'stablediffusioncpp': 'sdcpp', 'stable-diffusion.cpp': 'sdcpp',
                  'stable_diffusion_cpp': 'sdcpp', 'api_image': 'image_api',
                  'openai_image': 'image_api', 'openai_images': 'image_api',
                  'openai_compat_image': 'image_api', 'none': 'off', 'disabled': 'off'}
_MODE_ALIASES = {'response': 'responses', 'chat': 'chat_completions',
                 'chat_completion': 'chat_completions', 'completions': 'chat_completions'}
# Private recovery only: never include this in receipts, diagnostics or dumps.
_ENVIRONMENT_ORIGINALS: list[dict[str, str]] = []
_ENVIRONMENT_RECEIPT: dict = {'changed': False, 'changes': []}


def _change(action: str, source: str, target: str = '', *, review: bool = False) -> dict:
    return {'action': action, 'source': source, 'target': target, 'review': review}


def _provider(value: str) -> str:
    normalized = value.strip().lower().replace('-', '_')
    if normalized in {'local', 'openrouter', 'openai_compat', 'openai_codex'}:
        return normalized
    return _PROVIDER_ALIASES.get(normalized, value)


def _pool_occupied(values: Mapping[str, str]) -> bool:
    prefix = 'INFINI_LLM_POOL_2_'
    if values.get(prefix + 'ENABLED', '').strip().lower() in {'1', 'true', 'yes', 'on', 'y', 't'}:
        return True
    if any(values.get(prefix + suffix, '').strip()
           for suffix in ('MODEL', 'BASE_URL', 'API_KEY', 'OPENROUTER_PROVIDER')):
        return True
    return (values.get(prefix + 'PROVIDER', '').strip().lower() not in {'', 'openai_compat'}
            or values.get(prefix + 'API_MODE', '').strip().lower() not in {'', 'auto'})


def migrate_values(values: Mapping[str, str], *, environment: Mapping[str, str] | None = None) -> tuple[dict[str, str], list[dict]]:
    """Return current settings and value-free changes. Explicit current keys win."""
    current = dict(values)
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in current.items()):
        raise ValueError('Configuration migration requires string keys and values.')
    changes = []
    context = dict(environment or {})
    # A file is migrated before environment overlay. Use canonical process
    # settings only as conflict evidence, never persist their values or secrets.
    image_sources = {key: target for key, target in SIMPLE_ALIASES.items()
                     if key.startswith('INFINI_OPENAI_COMPAT_IMAGE_') and key in current}
    old_image_base = current.get('INFINI_OPENAI_COMPAT_IMAGE_BASE_URL', 'https://api.openai.com/v1').strip().rstrip('/')
    image_conflict = bool(image_sources) and (
        any(key in context for key in ('INFINI_IMAGE_API_BASE_URL', 'INFINI_IMAGE_API_KEY'))
        or ('INFINI_IMAGE_API_BASE_URL' in current
            and current['INFINI_IMAGE_API_BASE_URL'].strip().rstrip('/') != old_image_base)
        or ('INFINI_IMAGE_API_KEY' in current
            and (('INFINI_OPENAI_COMPAT_IMAGE_API_KEY' in current
                  and current['INFINI_IMAGE_API_KEY'] != current['INFINI_OPENAI_COMPAT_IMAGE_API_KEY'])
                 or ('INFINI_OPENAI_COMPAT_IMAGE_BASE_URL' in current
                     and 'INFINI_OPENAI_COMPAT_IMAGE_API_KEY' not in current))))
    if image_conflict:
        for source, target in image_sources.items():
            current.pop(source)
            changes.append(_change('image_profile_conflict_preserved_in_backup', source, target, review=True))
    for source, target in SIMPLE_ALIASES.items():
        if source not in current:
            continue
        old = current.pop(source)
        conflict = target in current and current[target] != old
        if target not in current:
            current[target] = old
        changes.append(_change('canonical_wins' if conflict else 'rename', source, target, review=conflict))

    # Translate only documented historical enum spellings. Unknown values remain
    # available to the current validator, not silently guessed or made valid.
    for key, value in list(current.items()):
        new = value
        if key == 'INFINI_LLM_PROVIDER' or (key.startswith('INFINI_LLM_POOL_') and key.endswith('_PROVIDER')
                                            and not key.endswith('_OPENROUTER_PROVIDER')):
            new = _provider(value)
        elif key == 'INFINI_IMAGE_BACKEND':
            new = _IMAGE_ALIASES.get(value.strip().lower(), value)
        elif key == 'INFINI_LLM_API_MODE' or (key.startswith('INFINI_LLM_POOL_') and key.endswith('_API_MODE')):
            normalized = value.strip().lower().replace('-', '_')
            new = _MODE_ALIASES.get(normalized, normalized if normalized in {'auto', 'responses', 'chat_completions'} else value)
        if new != value:
            current[key] = new
            changes.append(_change('value_alias', key, key))

    fallback = {suffix: current.pop('INFINI_LLM_FALLBACK_' + suffix)
                for suffix in FALLBACK_SUFFIXES if 'INFINI_LLM_FALLBACK_' + suffix in current}
    if fallback:
        prefix = 'INFINI_LLM_POOL_2_'
        provider = _provider(fallback.get('PROVIDER', '').strip() or current.get('INFINI_LLM_PROVIDER', '').strip() or 'local')
        candidates = dict(fallback)
        candidates['PROVIDER'] = provider
        candidates['API_MODE'] = 'responses' if provider == 'openai_codex' else 'chat_completions'
        provider_prefix = {'openrouter': 'INFINI_OPENROUTER_', 'openai_compat': 'INFINI_OPENAI_COMPAT_',
                           'local': 'INFINI_LMSTUDIO_'}.get(provider)
        if provider_prefix:
            base_key = provider_prefix + ('URL' if provider == 'local' else 'BASE_URL')
            if not candidates.get('BASE_URL', '').strip() and base_key in current:
                candidates['BASE_URL'] = current[base_key]
            if provider != 'local' and not candidates.get('API_KEY', '').strip() and provider_prefix + 'API_KEY' in current:
                candidates['API_KEY'] = current[provider_prefix + 'API_KEY']
        # Structural canonical choices, including explicit blanks, own the
        # whole profile. Never mix a retained endpoint/provider/model with an
        # old credential intended for a different or ambiguous destination.
        effective = {**current, **context}
        structural_conflict = any(prefix + suffix in effective and suffix in candidates
                                  and effective[prefix + suffix] != candidates[suffix]
                                  for suffix in ('PROVIDER', 'BASE_URL', 'MODEL'))
        context_owns_pool = any(key.startswith(prefix) for key in context)
        if _pool_occupied(effective) or structural_conflict or context_owns_pool:
            for suffix in fallback:
                changes.append(_change('pool_conflict_preserved_in_backup', 'INFINI_LLM_FALLBACK_' + suffix,
                                       prefix + suffix, review=True))
        else:
            # Keep explicit canonical blanks, too: the backup retains data that
            # cannot be copied without overriding a modern user's setting.
            for suffix, value in candidates.items():
                target = prefix + suffix
                conflict = target in current and current[target] != value
                if target not in current:
                    current[target] = value
                changes.append(_change('canonical_wins' if conflict else 'profile_migration',
                                       'INFINI_LLM_FALLBACK_' + suffix, target, review=conflict))
            current.setdefault(prefix + 'ENABLED', '0')
            changes.append(_change('pool_requires_review_round_robin', 'INFINI_LLM_FALLBACK_MODEL',
                                   prefix + 'ENABLED', review=True))
    return current, changes


def migrate_environment(environ: MutableMapping[str, str]) -> dict:
    """Migrate this process only; preserve displaced values privately in memory."""
    global _ENVIRONMENT_RECEIPT
    before = dict(environ)
    after, changes = migrate_values(before)
    if not changes:
        return {'changed': False, 'changes': []}
    # Retain before applying, so recovery data survives even a custom mapping's
    # failure. os.environ is the production caller; no registry/setx mutation.
    _ENVIRONMENT_ORIGINALS.append({key: value for key, value in before.items() if after.get(key) != value})
    try:
        for key, value in after.items():
            if before.get(key) != value:
                environ[key] = value
        for key in before.keys() - after.keys():
            del environ[key]
    except Exception:
        environ.clear()
        environ.update(before)
        raise
    _ENVIRONMENT_RECEIPT = {'changed': True, 'changes': [*_ENVIRONMENT_RECEIPT['changes'], *changes]}
    return {'changed': True, 'changes': changes}


def environment_migration_status() -> dict:
    return json.loads(json.dumps(_ENVIRONMENT_RECEIPT))


def read_migration_receipt(path: Path) -> dict:
    destination = Path(path).resolve()
    receipt_path = destination.with_name(destination.name + '.migration.json')
    try:
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return {'changed': False, 'changes': []}
    if not isinstance(receipt, dict) or not isinstance(receipt.get('changes'), list):
        return {'changed': False, 'changes': []}
    # A prepared receipt counts as applied only when current bytes match its target.
    if receipt.get('state') == 'prepared':
        try:
            receipt['state'] = ('completed' if _hash(destination.read_bytes()) == receipt.get('target_sha256')
                                else 'not_applied')
        except FileNotFoundError:
            receipt['state'] = 'not_applied'
    return receipt


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def migrate_config_file(path: Path, *, environment: Mapping[str, str] | None = None) -> dict:
    """Back up bytes, prepare a receipt, then atomically publish current format.

    Existing current files are never rewritten. Prepared receipts include the
    target hash, so a failed receipt-finalization write cannot trigger a second
    migration. The next read sees canonical data and is naturally idempotent.
    """
    path = Path(path)
    if not path.exists():
        return {'changed': False, 'changes': []}
    destination = path.resolve(strict=True) if path.is_symlink() else path
    original = destination.read_bytes()
    text = original.decode('utf-8-sig')
    parsed = parse_env_text(text, allow_legacy=True)
    migrated, changes = migrate_values(parsed, environment=environment)
    if config_format(text) == 'legacy' and parsed:
        changes.insert(0, _change('wire_format', 'legacy', 'json-string-v1'))
    if not changes:
        return {'changed': False, 'changes': []}
    # Values and keys are validated before any filesystem mutation.
    for key in migrated:
        if not key or key != key.strip() or any(ch in key for ch in '\r\n=\x00') or key.startswith('#'):
            raise ValueError('Invalid configuration key; migration was not written.')
    target = (FORMAT_HEADER + '\n' + ''.join(f'{key}={encode_value(value)}\n' for key, value in migrated.items())).encode('utf-8')
    parse_env_text(target.decode('utf-8'))
    source_hash, target_hash = _hash(original), _hash(target)
    backup = destination.with_name(destination.name + '.pre-migration-' + source_hash[:16] + '.bak')
    receipt_path = destination.with_name(destination.name + '.migration.json')
    receipt = {'changed': True, 'changes': changes, 'backup_path': str(backup),
               'receipt_path': str(receipt_path), 'source_sha256': source_hash,
               'target_sha256': target_hash, 'state': 'prepared'}
    # Never follow or overwrite an unexpected backup. Exclusive creation retains
    # the first exact source even if an earlier publication attempt was aborted.
    try:
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if backup.is_symlink() or backup.read_bytes() != original:
            raise OSError('Configuration migration backup conflict; original unchanged.') from None
    else:
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            backup.unlink(missing_ok=True)
            raise
    if destination.read_bytes() != original:
        raise OSError('Configuration changed during migration; retry with the new file.')
    _atomic_write(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2).encode('utf-8'))
    # Stage separately so all disk writes/fsync finish before the race check.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.' + destination.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, destination.stat().st_mode & 0o777)
            stream.write(target)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.read_bytes() != original:
            raise OSError('Configuration changed during migration; original not replaced.')
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    receipt['state'] = 'completed'
    try:
        _atomic_write(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2).encode('utf-8'))
    except OSError:
        receipt['state'] = 'completed_receipt_pending'
        # The prepared receipt already contains both hashes and the backup path.
        # Do not report the successful config publication as a failed migration.
    return receipt
