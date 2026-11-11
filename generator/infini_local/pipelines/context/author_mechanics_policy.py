"""Author-only source choice under the producer's explicit identity assumption.

Raw captures retain strict graphs/source. No code is parsed, truncated or executed.
Missing/ambiguous definition certificates or identity-pruning refusals keep both views.
"""
from __future__ import annotations
import copy
import hashlib
import json
from typing import Any
from .csharp_source_view import _records, _certificate, _at_path, _model_source_record, _specialized_record

POLICY = (
    "For coverage=approximate_identity_ast_method or approximate_identity_ast_regions only, certificate-matched producer C# assumes captured type/aiStyle stays stable across opaque calls. "
    "Explicit identity mutation/address escape or unproved receiver binding blocks selection. "
    "Regional entry guards must be reached; enclosing flow is unknown. Strict alternatives remain in raw capture. "
    "Unchanged whole_method keeps original gates, even after hooks, with no identity-stability assumption. "
    "Neither view proves execution or full runtime behavior. Unmatched methods, lifecycle, calls/hooks and extraction failures keep their limits."
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


def strict_source_diagnostics(rows: Any, reference: dict, attack: dict,
                              removed_definitions: list) -> Any:
    """A complete unchanged method can replace its derived diagnostic graph.

    This is independent of approximate identity pruning. Bind the original graph
    and the actually emitted whole method exactly; never use a regional source,
    a same-named method, or a source superseded by the approximate policy.
    """
    from .attack_tables import unpack_attack_tables
    from .csharp_source_view import _known_graph
    if not isinstance(rows, list):
        return rows
    records = _records(reference) or {}
    projected = unpack_attack_tables(attack)
    envelope = projected.get('nativeCSharpSource', {})
    emitted = envelope.get('records', []) if isinstance(envelope, dict) else []
    result = copy.deepcopy(rows)
    for i, row in enumerate(result):
        if not isinstance(row, dict) or not isinstance(row.get('path'), list):
            continue
        program = row.get('selectedProgram')
        if (not isinstance(program, dict) or set(program) - {
                'method', 'observations', 'dependencies', 'predicates', 'symbols',
                'coverage', 'unresolved', 'identitySelection'}):
            continue
        original, selected = _at_path(reference, row['path']), _at_path(projected, row['path'])
        if not original or not selected or not _known_graph(original[2]) or not isinstance(selected[2], dict):
            continue
        definition = _definition(original[2])
        if definition is None or definition in removed_definitions:
            continue
        stricts = [r for r in records.values() if r.get('coverage') == 'whole_method'
                   and _definition(r) == definition and row['path'] in r['graphPaths']]
        if len(stricts) != 1:
            continue
        matches = [r for r in emitted if isinstance(r, dict)
                   and r.get('id') == selected[2].get('nativeCSharpSourceRef')
                   and isinstance(r.get('id'), str)
                   and {k: v for k, v in r.items() if k != 'id'} == _model_source_record(stricts[0])]
        if len(matches) != 1:
            continue
        qualifiers = []
        def retain_qualifiers(value: Any, path: tuple = ()) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {'unresolved', 'coverage', 'scope', 'identitySelection',
                               'identitySelectionUnavailable', 'graphCapture'}:
                        qualifiers.append({'path': list((*path, key)), 'value': copy.deepcopy(child)})
                    else:
                        retain_qualifiers(child, (*path, key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    retain_qualifiers(child, (*path, index))
        retain_qualifiers(program)
        replacement = {k: v for k, v in row.items() if k != 'selectedProgram'}
        replacement.update(selectedSource='unchanged_verified_whole_method',
                           nativeCSharpSourceRef=matches[0]['id'])
        if qualifiers:
            replacement['selectedProgramQualifiers'] = qualifiers
        size = lambda value: len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))
        if size(replacement) < size(row):
            result[i] = replacement
    return result
