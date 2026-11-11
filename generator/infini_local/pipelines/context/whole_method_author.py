"""Narrow, certificate-bound C#-first view of native parent graphs.

This changes presentation, never extraction: the original full graph is retained
in the capture. Unmatched/parameterized/ambiguous methods keep their graph. A
whole method is not evidence that its branches or opaque hooks actually ran.
"""
from __future__ import annotations

import copy
import json
from typing import Any

from .author_mechanics_policy import _bound_candidates, _definition

_BODY_FIELDS = {'values', 'statements', 'blocks', 'possibleLocalWrites'}
_APPROXIMATE_FIELDS = {'method', 'sourceModuleVersionId', 'sourceMethodSha256', 'metadataToken',
    'identityPruning', 'coverage', 'approximation', 'receiverBinding', 'removedConditionalCount',
    'removedSwitchSectionCount', 'removedUnreachableStatementCount', 'removedEmptyStatementCount',
    'code', 'codeSha256', 'assemblySha256', 'excludedCallOffsets', 'spawnTypeCandidates', 'unresolved', 'graphPaths'}


def _known_graph(graph: Any) -> bool:
    if not isinstance(graph, dict) or 'transportOmissions' in graph:
        return False
    if any(not isinstance(graph.get(k), list) for k in ('nodes', 'members', 'modules', 'edges')):
        return False
    def index(value, rows):
        return type(value) is int and 0 <= value < len(rows)
    if any(not isinstance(m, dict) or not isinstance(m.get('name'), str)
           or not index(m.get('module'), graph['modules']) for m in graph['members']):
        return False
    if any(not isinstance(m, dict) or not isinstance(m.get('mvid'), str) for m in graph['modules']):
        return False
    ids = [n.get('id') for n in graph['nodes'] if isinstance(n, dict)]
    return (len(ids) == len(graph['nodes']) and all(type(i) is int for i in ids) and len(set(ids)) == len(ids)
            and all(index(n.get('method'), graph['members']) for n in graph['nodes'])
            and all(isinstance(e, dict) for e in graph['edges']))
_READING = (
    'bodySource points to the complete unchanged C# method in mechanics.source. '
    'It replaces only this node\'s diagnostic IL body, not its edges, identity or refusals. '
    'Original source gates apply at their actual position, including after hooks; '
    'captured type/aiStyle are not guaranteed to survive opaque calls. '
    'Child types are conditional source candidates, not executed spawns. '
    'Edge argumentBindings copy simple input loads; sourceILValue is a raw-capture coordinate, not a graph reference. '
    'The retained coverage/counts describe the original graph capture, not completeness of runtime behavior.'
)


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')))


def _profiles(item: dict):
    """Only shipped projectile-profile owners, never arbitrary item metadata."""
    from .native_references import known_projectile_references
    pending = [item.get('directProjectileRaw'), item.get('effectiveProjectileRaw')]
    ammo = item.get('ammoRaw')
    if isinstance(ammo, dict):
        for key in ('projectileRaw', 'weaponShootFieldProjectileRaw', 'nativeReplacementProjectileRaw',
                    'playerInventoryProjectileRaw', 'fallbackProjectileRaw'):
            value = ammo.get(key)
            pending.extend(value if isinstance(value, list) else [value])
    seen = set()
    while pending:
        profile = pending.pop()
        if not isinstance(profile, dict) or id(profile) in seen:
            continue
        seen.add(id(profile))
        if isinstance(profile.get('attackReference'), dict) and isinstance(profile.get('mechanicsSource'), dict):
            yield profile
        links = profile.get('referencedProjectiles')
        if known_projectile_references(links):
            pending.extend(row.get('profile') for row in links['references'] if isinstance(row, dict))


def _edge_bindings(graph: dict, node: dict) -> dict[int, Any] | None:
    """Do not drop an edge's value namespace when replacing its method body.

    The first supported case is deliberately small: parameterless instance
    methods with direct receiver loads. Complex argument expressions keep IL.
    Pre-existing omitted-call arguments remain explicitly unavailable.
    """
    result = {}
    values = node.get('values', {})
    for index, edge in enumerate(graph['edges']):
        if edge.get('from') != node['id']:
            continue
        context = edge.get('context')
        if not isinstance(context, list):
            # Only this producer-owned child dispatch context is independent
            # of the caller's values namespace. Unknown contexts can hide refs.
            if (edge.get('kind') == 'certified_native_projectile_source_windows'
                    and isinstance(context, dict) and set(context) == {'projectileId', 'aiStyle', 'entryAndOmittedFlow'}
                    and type(context['projectileId']) is int and type(context['aiStyle']) is int
                    and context['entryAndOmittedFlow'] == 'unresolved'):
                continue
            return None
        bindings = []
        for identifier in edge['context']:
            value = values.get(str(identifier))
            if value is None and edge.get('sourceCoverage') == 'callsite_omitted_from_source_slice' and edge.get('unresolved'):
                bindings.append({'sourceILValue': identifier, 'unresolved': edge['unresolved']})
            elif (isinstance(value, list) and len(value) == 4 and value[:3] == ['ldarg', 0, []]
                  and type(value[1]) is int and node.get('static') is False):
                bindings.append({'sourceILValue': identifier, 'input': 'this',
                                 'identityAfterHooks': 'unknown'})
            else:
                return None
        result[index] = bindings
    return result


def prepare_whole_method_author(item: dict) -> tuple[dict, list[dict]]:
    """Select only unchanged whole bodies tied to one exact parent definition."""
    from .mechanics_context import _author_source_graph, _source
    if item.get('generatedData') or not isinstance(item.get('parentSourceGraph'), dict):
        return item, []
    graph = _author_source_graph(item['parentSourceGraph'])
    if not _known_graph(graph):
        return item, []
    candidates = {}
    refused = set()
    for profile in _profiles(item):
        if _source(profile) is None:
            continue
        for strict, _, readable in _bound_candidates(profile['attackReference'], profile['mechanicsSource'], profile):
            if strict['coverage'] != 'whole_method':
                continue
            key = _definition(strict)
            if set(readable) - _APPROXIMATE_FIELDS:
                refused.add(key)
                continue
            candidates.setdefault(key, []).append((strict, readable))
    choices = []
    for node in graph.get('nodes', []):
        # No lexical signature guessing: only exact zero-parameter members.
        if node.get('static') is not False or node.get('arguments') != [] or not isinstance(node.get('values'), dict) or not node['values']:
            continue
        member = graph['members'][node['method']]
        module = graph['modules'][member['module']]
        matches = [(key, rows) for key, rows in candidates.items()
                   if key not in refused and member['name'] == key[0] + '()'
                   and module['mvid'] == key[1] and node.get('sha256') == key[2]]
        if len(matches) != 1:
            continue
        key, rows = matches[0]
        # Same definition may be captured from several profiles. Conflicting
        # bodies/assembly receipts refuse selection, even when IL hashes match.
        bodies = {(r['code'], r['assemblySha256'], r['codeSha256']) for r, _ in rows}
        if len(bodies) != 1:
            continue
        record = rows[0][0]
        bindings = _edge_bindings(graph, node)
        if bindings is None:
            continue
        if _size({k: node[k] for k in _BODY_FIELDS if k in node}) <= len(record['code']) + 640:
            continue
        choices.append({'node': node['id'], 'definition': key, 'record': copy.deepcopy(record),
                        'bindings': bindings})
    if not choices:
        return item, []
    selected = {tuple(choice['definition']) for choice in choices}
    result = dict(item)
    try:
        for key in ('directProjectileRaw', 'effectiveProjectileRaw', 'ammoRaw'):
            if key in item:
                result[key] = copy.deepcopy(item[key])
    except RecursionError:
        return item, []
    for profile in _profiles(result):
        if _source(profile) is None:
            continue
        reference, mechanics = profile['attackReference'], profile['mechanicsSource']
        bound = [(r, i, a) for r, i, a in _bound_candidates(reference, mechanics, profile)
                 if _definition(r) in selected and not set(a) - _APPROXIMATE_FIELDS]
        if not bound:
            continue
        removed = {i for _, i, _ in bound}
        # Superseded approximate bodies must not remain as a second truth, nor
        # supply excludedCallOffsets/spawnTypeCandidates to child filtering.
        mechanics['records'] = [r for i, r in enumerate(mechanics['records']) if i not in removed]
        for strict, _, approximate in bound:
            for gap in approximate.get('unresolved', []):
                marker = strict['method'] + ':superseded_identity_approximation:' + gap
                if marker not in mechanics['unresolved']:
                    mechanics['unresolved'].append(marker)
            for record in reference['nativeCSharpSource']['records']:
                if _definition(record) == _definition(strict):
                    record.pop('identitySpecialized', None)
    return result, choices


def _compact_graph_tables(graph: dict) -> bool:
    """Normalization: discard unused lookup rows, not graph facts or sources.

    Match BuildExport's member/module namespace and preserve row order. This is
    only for the known rootless graph after whole-body substitution. Any hidden
    table reference, unfamiliar row field, or invalid index keeps the original tables.
    """
    from .mechanics_context import _GRAPH_FIELDS, _GRAPH_ROW_FIELDS
    if (not _known_graph(graph) or graph.get('source') != 'parent_reachable_compiled_source_graph'
            or type(graph.get('version')) is not int or graph['version'] != 1
            or graph.get('roots') != [] or set(graph) - _GRAPH_FIELDS
            or not any('bodySource' in n for n in graph['nodes'])
            or any('fragments' in n for n in graph['nodes'])):
        return False
    for key in ('nodes', 'members', 'modules', 'edges'):
        fields = _GRAPH_ROW_FIELDS[key] | ({'bodySource'} if key == 'nodes' else set())
        if any(set(row) - fields for row in graph[key]):
            return False
    members, modules = graph['members'], graph['modules']
    if (any(not isinstance(value, str) for row in members for key, value in row.items() if key != 'module')
            or any(not isinstance(value, str) for row in modules for value in row.values())):
        return False
    refs: list[tuple[dict, str]] = []
    for node in graph['nodes']:
        refs.extend((node, key) for key in ('method', 'receiverType', 'originReceiverType') if key in node)
        values = node.get('values', {})
        if not isinstance(values, dict):
            return False
        for value in values.values():
            if not isinstance(value, list) or len(value) != 4:
                return False
            operand = value[1]
            if isinstance(operand, dict):
                if set(operand) != {'member'}:
                    return False
                refs.append((operand, 'member'))
    if any(type(row[key]) is not int or not 0 <= row[key] < len(members) for row, key in refs):
        return False
    # Refuse table-shaped fields anywhere else, including future block/edge
    # metadata. Do not mistake an unrecognized reference for an unused member.
    known = {(id(row), key) for row, key in refs} | {(id(row), 'module') for row in members}
    def hidden(value):
        if isinstance(value, dict):
            return any((key in {'member', 'method', 'receiverType', 'originReceiverType', 'module'}
                        and (id(value), key) not in known) or hidden(child) for key, child in value.items())
        return isinstance(value, list) and any(hidden(child) for child in value)
    if hidden(graph):
        return False
    used = sorted({row[key] for row, key in refs})
    used_modules = sorted({members[index]['module'] for index in used})
    if len(used) == len(members) and len(used_modules) == len(modules):
        return False
    member_ids = {old: new for new, old in enumerate(used)}
    module_ids = {old: new for new, old in enumerate(used_modules)}
    for row, key in refs:
        row[key] = member_ids[row[key]]
    graph['members'] = [members[index] for index in used]
    for row in graph['members']:
        row['module'] = module_ids[row['module']]
    graph['modules'] = [modules[index] for index in used_modules]
    return True


def apply_whole_method_author(raw: dict, choices: list[dict]) -> bool:
    """Bind to the actual emitted source, then replace only its graph body."""
    graph = raw.get('item', {}).get('parentSourceGraph')
    sources = raw.get('mechanics', {}).get('source')
    if not choices or not _known_graph(graph) or not isinstance(sources, list):
        return False
    replacements = []
    for choice in choices:
        record = choice['record']
        matches = [i for i, source in enumerate(sources) if source.get('method') == record['method']
                   and source.get('coverage') == 'whole_method' and source.get('code') == record['code']
                   and source.get('unresolved') == record['unresolved'] and not source.get('identitySpecialization')]
        nodes = [node for node in graph['nodes'] if node['id'] == choice['node']]
        if len(matches) != 1 or len(nodes) != 1:
            return False
        node = nodes[0]
        member = graph['members'][node['method']]
        definition = tuple(choice['definition'])
        if (member['name'] != definition[0] + '()' or node.get('sha256') != definition[2]
                or graph['modules'][member['module']]['mvid'] != definition[1]
                or _edge_bindings(graph, node) != choice['bindings']):
            return False
        replacements.append((node, matches[0], choice))
    for node, index, choice in replacements:
        for key in _BODY_FIELDS:
            node.pop(key, None)
        node['bodySource'] = {'mechanicsSourceIndex': index, 'representation': 'unchanged_verified_whole_method',
                              'metadataToken': choice['record']['metadataToken']}
        for edge_index, bindings in choice['bindings'].items():
            graph['edges'][edge_index]['context'] = {'argumentBindings': copy.deepcopy(bindings)}
    _compact_graph_tables(graph)
    raw['item']['parentSourceGraphReading'] = _READING + ' ' + raw['item'].get('parentSourceGraphReading', '')
    return True
