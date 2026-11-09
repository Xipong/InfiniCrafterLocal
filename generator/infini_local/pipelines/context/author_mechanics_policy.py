"""Author-only source choice under the producer's explicit identity assumption.

Raw captures retain strict graphs/source. No code is parsed, truncated or executed.
Missing/ambiguous definition certificates or identity-pruning refusals keep both views.
"""
from __future__ import annotations
import copy
import hashlib
from typing import Any
from .csharp_source_view import _records, _certificate, _at_path, _model_source_record, _specialized_record

POLICY = (
    "For certificate-matched whole methods or exactly matched guarded source regions, this Author view uses the producer's readable C# "
    "under its stated assumption that captured type/aiStyle stays stable across opaque calls. "
    "Explicit identity mutation/address escapes or unproved receiver binding prevent selection. "
    "Entry guards of conditional regions still have to be reached; enclosing dispatcher flow remains unknown. Strict alternative source and graphs remain in the raw capture, not this request. "
    "This is an approximate gameplay view, not a proof of complete runtime behavior. "
    "Unmatched methods, lifecycle, calls/hooks and extraction failures retain their existing limits."
)

def _definition(value: Any) -> tuple | None:
    cert = _certificate(value)
    token = value.get('metadataToken') if isinstance(value, dict) else None
    if cert is None or type(token) is not int or token & 0xff000000 != 0x06000000 or not token & 0xffffff:
        return None
    return (*cert, token)

def _bound_candidates(reference: dict, mechanics: Any, profile: dict) -> list:
    records = _records(reference)
    if (not records or not isinstance(mechanics, dict)
            or type(profile.get('type')) is not int or type(profile.get('aiStyle')) is not int
            or not isinstance(reference.get('identityPredicates'), dict)
            or set(reference['identityPredicates']) != {'Projectile.type', 'Projectile.aiStyle'}
            or any(type(reference['identityPredicates'].get(key)) is not int for key in ('Projectile.type', 'Projectile.aiStyle'))
            or reference['identityPredicates'] != {'Projectile.type':profile['type'],'Projectile.aiStyle':profile['aiStyle']}
            or not isinstance(mechanics.get('identity'), dict)
            or any(type(mechanics['identity'].get(key)) is not int for key in ('type', 'aiStyle'))
            or mechanics.get('source') != 'native_mechanics_source' or type(mechanics.get('version')) is not int
            or mechanics['version'] != 1 or mechanics.get('identity') != {'type':profile.get('type'),'aiStyle':profile.get('aiStyle')}
            or not isinstance(mechanics.get('records'), list)):
        return []
    bound = []
    for strict in records.values():
        definition = _definition(strict)
        coverage = {'whole_method':'approximate_identity_ast_method',
                    'conditional_ast_regions':'approximate_identity_ast_regions'}.get(strict.get('coverage'))
        if definition is None or coverage is None:
            continue
        candidates = [(i,r) for i,r in enumerate(mechanics['records']) if isinstance(r,dict)
                      and _definition(r) == definition]
        if len(candidates) != 1:
            continue
        index, readable = candidates[0]
        if (readable.get('coverage') != coverage
                or readable.get('receiverBinding') != 'captured_actor_source_binding'
                or readable.get('identityPruning') != {'allowed':True,'refusal':None}
                or readable.get('assemblySha256') != strict.get('assemblySha256')
                or not isinstance(readable.get('code'),str) or not readable['code'].strip()
                or hashlib.sha256(readable['code'].encode()).hexdigest() != readable.get('codeSha256')
                or readable.get('graphPaths') != strict.get('graphPaths')
                or not isinstance(readable.get('unresolved'),list)
                or any(not isinstance(v,str)for v in readable['unresolved'])):
            continue
        if strict['coverage'] == 'conditional_ast_regions' and (
                not strict.get('entryGuards') or readable.get('entryGuards') != strict['entryGuards']):
            continue
        if any((found := _at_path(reference,path)) is None or _definition(found[2]) != definition
               for path in strict['graphPaths']):
            continue
        bound.append((strict,index,readable))
    return bound


def preferred_guarded_records(reference: dict, mechanics: Any, profile: dict) -> list[str]:
    """Prefer source only; the canonical owner still validates all covered windows."""
    return [strict['id'] for strict,_,_ in _bound_candidates(reference,mechanics,profile)
            if strict['coverage'] == 'conditional_ast_regions']


def select_author_mechanics(reference: dict, mechanics: Any, attack: dict, profile: dict) -> dict:
    """Return internal aliases only after binding raw and emitted representations."""
    from .attack_tables import unpack_attack_tables
    projected = unpack_attack_tables(attack).get('nativeCSharpSource', {})
    emitted = projected.get('records', []) if isinstance(projected, dict) else []
    aliases, paths, certificates = {}, [], []
    for strict,index,readable in _bound_candidates(reference,mechanics,profile):
        variants = [strict]
        specialized = _specialized_record(reference, strict)
        if specialized is not None: variants.append(specialized)
        matches = [r for r in emitted if isinstance(r,dict) and isinstance(r.get('id'),str)
                   and any({k:v for k,v in r.items()if k!='id'} == _model_source_record(v) for v in variants)]
        if len(matches) != 1 or matches[0]['id'] in aliases:
            continue
        aliases[matches[0]['id']] = index
        paths.extend(copy.deepcopy(strict['graphPaths']))
        certificates.append(_definition(strict))
    return {'aliases':aliases,'paths':paths,'certificates':certificates}


def selected_diagnostics(rows: Any, paths: list) -> Any:
    """Keep every refusal/scope; move only the matched redundant program body."""
    if not isinstance(rows,list):return rows
    result=copy.deepcopy(rows)
    for row in result:
        if isinstance(row,dict) and row.get('path') in paths and 'selectedProgram'in row:
            program=row.pop('selectedProgram')
            row['selectedSource']='producer_readable_source_under_identity_assumption'
            if isinstance(program,dict):
                row['sourceCoverage']={k:copy.deepcopy(program[k])for k in ('coverage','unresolved','identitySelection')if k in program}
    return result
