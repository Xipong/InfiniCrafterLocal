"""Read-only campaign admission. No runtime bootstrap, credentials output or I/O side effects."""
from __future__ import annotations

from argparse import Namespace
import hashlib
import math
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

from toolbox.infini_toolbox import discover_project, read_config_env
from toolbox.live.panels import PANEL_PROVENANCE, load_selection


def read_environment(project: Path, config: Path | None) -> dict[str, str]:
    path = config.expanduser().resolve() if config else project / 'LocalGenerator/config.env'
    if config and not path.is_file():
        raise ValueError('explicit --config file is missing')
    env = dict(os.environ)
    skip_default = env.get("INFINI_SKIP_CONFIG_FILE", "").strip().lower() in {"1", "true", "yes", "on"}
    if config or (not skip_default and path.exists()):
        for key, value in read_config_env(path).items():
            env.setdefault(key, value)
    return env


def validate_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('base URL must be HTTP(S), without credentials, query or fragment')
    return value.rstrip('/') + '/'


def prepare(args: Namespace) -> tuple[dict, dict[str, str]]:
    if args.run and args.preflight_only:
        raise ValueError('--run and --preflight-only are mutually exclusive')
    for value, low, high, flag in (
        (args.parallel_crafts, 1, 8, 'parallel-crafts'),
        (args.transport_retries, 0, 100, 'transport-retries'),
        (args.transport_retry_delay_seconds, 60, 3600, 'transport-retry-delay-seconds'),
    ):
        if not low <= value <= high:
            raise ValueError(f'--{flag} must be within {low}..{high}')
    for key in ('expected_temperature', 'expected_vfx_temperature', 'expected_repair_temperature'):
        value = getattr(args, key)
        if value is not None and (not math.isfinite(value) or not 0 <= value <= 2):
            raise ValueError(f'--{key.replace("_", "-")} must be finite within 0..2')
    for key in ('expected_max_tokens', 'expected_visual_max_tokens', 'expected_vfx_max_tokens'):
        value = getattr(args, key)
        if value is not None and value <= 0:
            raise ValueError(f'--{key.replace("_", "-")} must be positive')
    if args.run:
        if args.output is not None:
            args.output = args.output.expanduser().resolve()
        required = ('output', 'expected_head', 'expected_provider', 'expected_model', 'expected_base_url',
                    'expected_api_mode', 'expected_response_format', 'expected_temperature',
                    'expected_vfx_temperature', 'expected_repair_temperature', 'expected_max_tokens',
                    'expected_visual_max_tokens', 'expected_vfx_max_tokens')
        missing = ['--' + key.replace('_', '-') for key in required if getattr(args, key) is None]
        if missing:
            raise ValueError('--run requires ' + ', '.join(missing))
        if args.expected_provider != 'openai_compat':
            raise ValueError('this HTTP-accounted harness supports --run only for openai_compat (not OAuth/native adapters)')
        if args.expected_api_mode not in ('chat_completions', 'responses') or args.expected_response_format not in ('json_object', 'json_schema'):
            raise ValueError('--run requires explicit API mode and response format, not auto')
        if args.output is not None and args.output.exists() and any(args.output.iterdir()):
            raise ValueError('--output must be a new or empty directory; existing evidence is never overwritten')
    project = discover_project(args.project)
    env = read_environment(project, args.config)
    configured = {
        'provider': env.get('INFINI_LLM_PROVIDER', '').strip(),
        'model': env.get('INFINI_OPENAI_COMPAT_MODEL', '').strip(),
        'apiMode': env.get('INFINI_LLM_API_MODE', 'auto').strip().lower(),
        'responseFormat': env.get('INFINI_LLM_RESPONSE_FORMAT', 'auto').strip().lower(),
    }
    for key, expected in (
        ('provider', args.expected_provider), ('model', args.expected_model),
        ('apiMode', args.expected_api_mode), ('responseFormat', args.expected_response_format),
    ):
        if expected is not None and configured[key] != expected:
            raise ValueError(f'configured {key} does not match --expected setting')
    endpoint = env.get('INFINI_OPENAI_COMPAT_BASE_URL', '').strip()
    if endpoint:
        endpoint = validate_endpoint(endpoint)
    if args.expected_base_url is not None and endpoint != validate_endpoint(args.expected_base_url):
        raise ValueError('configured base URL does not match --expected-base-url')
    llm_enabled = env.get('INFINI_USE_LLM', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    if args.run and not llm_enabled:
        raise ValueError('--run requires INFINI_USE_LLM=1 in the private environment')
    fallback = any(env.get(key, '').strip() for key in (
        'INFINI_LLM_FALLBACK_PROVIDER', 'INFINI_LLM_FALLBACK_MODEL', 'INFINI_LLM_REAUTHOR_MODEL',
    )) or any(env.get(f'INFINI_LLM_POOL_{i}_ENABLED', '0').strip() == '1' for i in (2, 3, 4))
    if (args.run or args.require_no_fallback) and fallback:
        raise ValueError('fallback/model hopping is configured')
    head = ''
    clean = None
    if (project / '.git').exists():
        head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        clean = not bool(subprocess.check_output(['git', '-C', str(project), 'status', '--porcelain'], text=True).strip())
    if args.expected_head:
        if head != args.expected_head:
            raise ValueError('project HEAD does not match --expected-head')
        if not clean:
            raise ValueError('--expected-head requires a clean project worktree')
    dump, routes, _, _, _ = load_selection(args)
    return {
        'preflightOnly': not args.run, 'realImageGeneration': False,
        'project': str(project), 'panel': args.panel, 'panelProvenance': PANEL_PROVENANCE,
        'caseCount': len(routes), 'cases': [dict(case=c, itemA=a, itemB=b) for c, a, b in routes],
        'runtimeDumpSha256': hashlib.sha256(dump.read_bytes()).hexdigest(),
        'ok': True, 'configured': configured, 'endpointConfigured': bool(endpoint), 'fallbackConfigured': fallback,
        'llmEnabled': llm_enabled,
        'gitHead': head, 'gitClean': clean,
        'requestSettingsVerified': False,
        'note': 'Offline admission only; actual stage sampling/reasoning/token settings are checked at request dispatch.',
    }, env
