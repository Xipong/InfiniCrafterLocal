"""Offline reader: exact source recovery and truthful, complete presentation."""
from __future__ import annotations

import base64
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("prompt_audit", ROOT / "tools/diagnostics/prompt_audit.py")
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class Text(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.parts = []
        self.feed(source)

    def handle_data(self, text):
        self.parts.append(text)


def visible(source):
    return " ".join(Text(source).parts)


def raw_from(document):
    match = re.search(r'<script id="original"[^>]*>([^<]*)</script>', document)
    assert match
    return base64.b64decode(match[1])


def test_complete_source_and_decoded_message_values_survive_without_mutation():
    content = {"priorityHeader": "line one\nline two", "unknown": {"a/b~c": [None, False, 0, "", {}, []]},
               "schemaDefinitions": {"$defs": {"foo": {"type": "string"}}}, "ref": {"$ref": "#/$defs/foo"}}
    source = {"schema": "infini.stage-request-messages.v1", "sanitized": True,
              "messages": [{"role": "system", "content": "Use this."},
                           {"role": "user", "content": json.dumps(content, ensure_ascii=False)}]}
    raw = b'\xef\xbb\xbf' + json.dumps(source, ensure_ascii=False, indent=3).encode() + b'\r\n'
    document, markdown, metadata = audit.build_report(raw, "trace.json")
    assert raw_from(document) == raw
    assert json.loads(raw_from(document).decode('utf-8-sig')) == source
    assert "line one\nline two" in visible(document)
    assert "/messages/1/content::/unknown/a~1b~0c/0" in markdown
    assert "#/$defs/foo" in markdown
    assert 'schemaDefinitions' in markdown and 'sanitized' in markdown
    assert metadata["sourceBytes"] == len(raw)
    assert audit.strict_json(raw.decode('utf-8-sig')) == source


@pytest.mark.parametrize("wrapper", ["builder", "chat", "responses", "dossier"])
def test_supported_input_shapes_keep_unknown_fields(wrapper):
    dossier = {"parents": {"A": {"packet": {"name": "Door"}}, "B": {"packet": {"name": "Chain"}}},
               "futureField": {"payload": "unrecognised but retained"}}
    request = {"messages": [{"role": "developer", "content": json.dumps(dossier)}]}
    source = {"builder": {"request": request, "evidence": {"parents": {"X": {"name": "NOT A PARENT"}}}},
              "chat": request,
              "responses": {"instructions": "System", "input": [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(dossier)}]}]},
              "dossier": dossier}[wrapper]
    raw = json.dumps(source).encode()
    document, text, _ = audit.build_report(raw, "input.json")
    assert "unrecognised but retained" in text
    assert "Door" in visible(audit.reading_layer(source))
    assert "NOT A PARENT" not in visible(audit.reading_layer(source))
    assert raw_from(document) == raw


def test_catalog_requiredness_refs_defaults_and_conditions_are_not_guessed():
    catalog = {"authoringSchema": "test", "fieldGuide": {"targetKindSets": {"t": ["item_body"]}}, "capabilities": [
        {"fn": "base", "does": "Original prose", "targetsRef": "t", "params": {
            "requiredNeutral": {"type": "number", "neutral": 0},
            "optional": {"type": "integer", "optional": True, "default": 0, "omissionAllowedOnlyWhen": "guard is off"}}},
        {"fn": "other", "params": {"borrowed": {"paramRef": "base.optional"}, "missing": {"paramRef": "no.such"}}}]}
    text = visible(audit.capability_cards(catalog, "/catalog"))
    assert "Обязателен; тип: number; нейтральное значение: 0" in text
    assert text.count("Необязателен; тип: integer; объявленный default: 0; пропуск допустим только при: guard is off") == 2
    assert "Неразрешённая ссылка: no.such. Требования не выведены." in text
    assert "item_body" in text and "Original prose" in text
    assert 'href="#' + audit.anchor('/catalog/capabilities/0/params/optional') + '"' in audit.capability_cards(catalog, '/catalog')


def test_html_injection_template_tokens_and_utf8_are_literal():
    bad = '</script><img src=x onerror="alert(1)">@@RAW@@ & Привет'
    raw = json.dumps({bad: bad}, ensure_ascii=False).encode()
    doc, md, _ = audit.build_report(raw, bad)
    assert '<img src=x' not in doc
    assert '&lt;img' in doc
    assert '@@RAW@@' in doc  # source token is not substituted a second time
    assert raw_from(doc) == raw
    assert bad in md


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'null', b'not json'])
def test_invalid_or_ambiguous_inputs_fail_explicitly(raw):
    with pytest.raises(ValueError):
        audit.build_report(raw, "invalid.json")


def test_duplicate_json_inside_message_is_retained_as_text():
    literal = '{"a":1,"a":2}'
    doc, md, _ = audit.build_report(json.dumps({"content": literal}).encode(), 'x.json')
    assert literal in visible(doc) and literal in md
    assert '/content::' not in md


def test_cli_readonly_outputs_and_refusal_to_overwrite(tmp_path):
    source = tmp_path / "request.json"
    raw = b'{"content":"hello"}\n'
    source.write_bytes(raw)
    output, text = tmp_path / 'audit.html', tmp_path / 'audit.md'
    assert audit.main([str(source), '--out', str(output), '--markdown', str(text)]) == 0
    assert output.exists() and 'hello' in text.read_text()
    original = output.read_bytes()
    assert audit.main([str(source), '--out', str(output)]) == 2
    assert audit.main([str(source), '--out', str(source)]) == 2
    assert audit.main([str(source), '--out', str(tmp_path/'same'), '--markdown', str(tmp_path/'same')]) == 2
    assert output.read_bytes() == original and source.read_bytes() == raw


def test_compact_bounds_and_all_extra_constraints_are_visible():
    card = {"type": "number", "min": -3, "max": 20, "multipleOf": 0.5, "pattern": "^[a-z]$",
            "shape": {"oneOf": [{"required": ["x"]}, {"required": ["y"]}]},
            "reference": {"targetKinds": ["free_projectile"], "allowSelf": False},
            "futureRule": "do not hide this", "consumerConstraint": {"rounding": "ties up"}}
    catalog = {"capabilities": [{"fn": "f", "params": {"p": card}}], "fieldGuide": {}, "authoringSchema": "test"}
    text = visible(audit.capability_cards(catalog, '/catalog'))
    for expected in ('не меньше: -3', 'не больше: 20', 'кратно: 0.5', 'шаблон: ^[a-z]$',
                     'free_projectile', 'allowSelf', 'false', 'oneOf', 'do not hide this', 'ties up'):
        assert expected in text


@pytest.mark.parametrize('capability', [
    {'fn': [], 'params': {}}, {'fn': 'x', 'targetsRef': [], 'params': []},
    {'fn': 'x', 'targetsRef': 'x', 'params': {'p': {'paramRef': 'bad.p'}}},
])
def test_unknown_catalog_shapes_remain_in_source_without_crashing(capability):
    source = {'catalog': {'authoringSchema': 'unknown', 'fieldGuide': {'targetKindSets': []}, 'capabilities': [capability]}}
    raw = json.dumps(source).encode()
    doc, _, _ = audit.build_report(raw, 'future.json')
    assert raw_from(doc) == raw


def test_unique_definition_links_without_inlining_or_guessing():
    source = {'content': json.dumps({'schemaDefinitions': {'$defs': {'Foo': {'type': 'string'}}},
                                    'field': {'$ref': '#/$defs/Foo'}})}
    doc, text, _ = audit.build_report(json.dumps(source).encode(), 'refs.json')
    assert 'href="#' + audit.anchor('/content::/schemaDefinitions/$defs/Foo') + '">Открыть определение</a>' in doc
    assert '#/$defs/Foo' in text


def test_documentation_is_borrowed_only_by_explicit_packet_rules():
    rule = 'configure_armor params without meaning inherit exact meaning from configure_accessory params of the same name; all own bounds and units still apply.'
    catalog = {'fieldGuide': {'armorParamInheritance': rule, 'types': {'window': {'description': 'Phase conditions.'}}},
               'capabilities': [
                   {'fn': 'configure_accessory', 'params': {'power': {'meaning': 'Exact accessory meaning.', 'max': 99}}},
                   {'fn': 'configure_armor', 'params': {'power': {'max': 3, 'optional': True}}},
                   {'fn': 'move', 'params': {'window': {'typeRef': 'window'}}}]}
    doc = audit.capability_cards(catalog, '/catalog')
    text = visible(doc)
    assert text.count('Exact accessory meaning.') == 2
    assert 'не больше: 3' in text and 'Phase conditions.' in text
    assert 'armorParamInheritance' in text
    catalog['fieldGuide']['armorParamInheritance'] = 'different future rule'
    text = visible(audit.capability_cards(catalog, '/catalog'))
    assert text.count('Exact accessory meaning.') == 1
    assert 'Отдельное пояснение смысла отсутствует' in text


def test_structured_explanations_are_not_serialized_json():
    content = {'requires': [{'kind': 'non_neutral_param', 'message': 'Choose a real effect.'}],
               'shape': {'properties': {'x': {'description': 'Time in seconds.', 'type': 'number'}}, 'required': ['x']}}
    rendered = audit.prose(content)
    assert '<dl' in rendered and '<ol' in rendered
    assert 'Choose a real effect.' in visible(rendered) and 'Time in seconds.' in visible(rendered)
    assert '{' not in rendered and '&quot;' not in rendered


def test_reader_controls_execute_with_a_minimal_dom(tmp_path):
    """Behavioral JS smoke, not a browser/layout or real DOM compatibility test."""
    import shutil
    import subprocess
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable for optional reader control smoke')
    template = (ROOT / 'tools/diagnostics/prompt_audit_template.html').read_text()
    script = re.search(r'<script>(.*?)</script>', template, re.S)[1]
    harness = r'''
const vm = require('node:vm');
const assert = require('node:assert/strict');
const first = {tagName:'DETAILS',open:false,parentElement:null};
const second = {tagName:'DETAILS',open:false,parentElement:first,scrollIntoView(options){this.scrollBlock=options.block;}};
function leaf(text,parent){return {textContent:text,parentElement:parent,highlight:false,
 classList:{toggle(_name,value){this.owner.highlight=value;}},scrollIntoView(){this.scrolled=true;}};}
const a=leaf('Alpha /a',second), b=leaf('Beta alpha /b',first);a.classList.owner=a;b.classList.owner=b;
const els={search:{value:''},status:{textContent:''},original:{textContent:'77u/eyJ4IjoxfQ0K'},readable:{textContent:'0KLQtdC60YHRgg=='}};
for(const name of ['search-button','next','expand','collapse','raw-download','text-download','copy-reading','select-reading','prose-download','copy-close','copy-fallback'])els[name]={focus(){this.focused=true;}};
els['prose-text']={textContent:Buffer.from('1. Текст: 0 мс; false; пустая строка\n2. Ещё').toString('base64')};
els['copy-value']={value:'',focus(){this.focused=true;},select(){this.selected=true;}};
const copyButton={dataset:{copy:els['prose-text'].textContent},focus(){this.focused=true;}};
els.target=second;
const events={};let blob;
const context={document:{querySelectorAll:s=>s.startsWith('details')?[first,second]:s==='[data-copy]'?[copyButton]:[a,b],getElementById:id=>els[id],
 createElement:()=>({click(){}})},window:{addEventListener:(name,fn)=>events[name]=fn},location:{hash:''},
 Blob:class{constructor(parts){blob=parts[0];}},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
 TextDecoder,Uint8Array,atob:s=>Buffer.from(s,'base64').toString('binary'),setTimeout:fn=>fn()};
vm.createContext(context);
'''
    checks = r'''
els.search.value='alpha';els['search-button'].onclick();assert.equal(els.status.textContent,'1 / 2 значений');
assert.equal(first.open,true);assert.equal(second.open,true);assert(a.highlight&&b.highlight);
els.next.onclick();assert.equal(els.status.textContent,'2 / 2 значений');assert(b.scrolled);
els.collapse.onclick();assert(!first.open&&!second.open);els.expand.onclick();assert(first.open&&second.open);
els.search.value='nothing';els['search-button'].onclick();assert(!a.highlight&&!b.highlight);
assert.equal(els.status.textContent,'0 совпадений в значениях');
els.search.value='';els.search.oninput({target:els.search});assert.equal(els.status.textContent,'Поиск очищен');
els['raw-download'].onclick();assert.equal(Buffer.from(blob).toString('hex'),'efbbbf7b2278223a317d0d0a');
els.collapse.onclick();context.location.hash='#target';events.hashchange();assert(first.open&&second.open);assert.equal(second.scrollBlock,'start');
'''
    checks += r'''
(async()=>{
const expected='1. Текст: 0 мс; false; пустая строка\n2. Ещё';
// Explicit manual copy remains available even if clipboard API lies about success.
els['select-reading'].onclick();assert.equal(els['copy-value'].value,expected);assert.equal(els['copy-fallback'].hidden,false);els['copy-close'].onclick();
// file://-style unavailable clipboard: expose full selectable text, never claim success.
await els['copy-reading'].onclick();assert.equal(els['copy-value'].value,expected);
assert.equal(els['copy-fallback'].hidden,false);assert(els['copy-value'].focused&&els['copy-value'].selected);
assert(!els.status.textContent.includes('Текст скопирован'));
els['copy-close'].onclick();assert(els['copy-fallback'].hidden&&els['copy-reading'].focused);
context.navigator={clipboard:{writeText:async()=>{throw new Error('NotAllowedError');}}};
await copyButton.onclick();assert.equal(els['copy-value'].value,expected);assert(!els['copy-fallback'].hidden);
els['copy-fallback'].onkeydown({key:'Escape'});assert(els['copy-fallback'].hidden&&copyButton.focused);
let copied;context.navigator.clipboard.writeText=async text=>{copied=text;};
await copyButton.onclick();assert.equal(copied,expected);assert.equal(els.status.textContent,'Текст скопирован');
els['prose-download'].onclick();assert.equal(Buffer.from(blob).toString('utf8'),expected);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    program = harness + '\nvm.runInContext(' + json.dumps(script) + ',context);\n' + checks
    file = tmp_path / 'controls.cjs'
    file.write_text(program)
    subprocess.run([node, str(file)], check=True, capture_output=True, text=True, timeout=15)


def test_literal_numbers_and_copy_payload_keep_constraints():
    rules = ["Keep all effects. Never infer hidden behavior.", "Unknown changed instruction."]
    data = {"priorityHeader": rules, "requiredJsonShape": {"root": [0, False, "", "5 ms"]}}
    raw = json.dumps(data).encode()
    document, _, _ = audit.build_report(raw, "test.json")
    assert raw_from(document) == raw
    assert '<span class="literal-number">1. </span>' in document
    copied = base64.b64decode(re.search(r'<script id="prose-text"[^>]*>([^<]*)', document)[1]).decode()
    for token in ["1.", "2.", 'Пустая строка ("")', "0", "false", "5 ms", "Never infer hidden behavior.", "Unknown changed instruction."]:
        assert token in copied
    assert "Готового пояснения этой версии нет" in copied
    assert "Копировать пункт" not in copied
    assert "INSTRUCTION_NOTES" not in copied


def test_original_instruction_copy_keeps_whitespace_exactly():
    rule = "First.  Second.\n\n\nLast. "
    markup = audit.instruction_cards([rule], "/priorityHeader")
    encoded = re.findall(r'data-copy="([^"]+)"', markup)[-1]
    assert base64.b64decode(encoded).decode() == "1. " + rule


def test_copy_preserves_literal_whitespace_and_source_mapping():
    literal = "  opening\n\n\nclosing  "
    markup = audit.prose({"meaning": literal}) + audit.source_link("/a~1b/0", "Source")
    plain = audit.reading_text(markup)
    assert literal in plain
    assert "Source [/a~1b/0]" in plain


def test_empty_default_is_explicit_not_missing():
    text = audit.param_sentence({"default": "", "minimum": 0, "optional": False, "units": "ms"})
    assert 'объявленный default: пустая строка ("")' in text
    assert "Обязателен" in text and "не меньше: 0" in text and "единицы: ms" in text


class ReadablePaths(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.values = []
        self.containers = []
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-reader-path' in attrs:
            self.values.append(attrs['data-reader-path'])
        if 'data-reader-container' in attrs:
            self.containers.append(attrs['data-reader-container'])


def test_complete_readable_layer_has_every_literal_not_only_source_links():
    from collections import Counter
    payload = {
        'priorityHeader': ['Keep every instruction.'],
        'runtimeProgramInvariants': {'ownership': 'exact owner', 'budget': 32},
        'parents': {'A': {'packet': {'name': 'Door', 'raw': {'damage': 36}}}},
        'balanceCorridor': {'parentDamage': [0, 0], 'unknown': [None, False, '', {}, []]},
        'sourceWireUnits': {'rule': 'scope-dependent conversion'},
        'requiredJsonShape': {'concept': {'coreMechanic': 'full documentation'}, 'runtimeProgram': {'calls': []}},
        'future': {'unknown': 'must remain readable'},
    }
    source = {'request': {'messages': [{'role': 'system', 'content': 'FULL SYSTEM'},
                                      {'role': 'developer', 'content': json.dumps(payload)}]},
              'evidence': {'notAnInstruction': 'CAPTURE ONLY'}}
    markup = audit.reading_layer(source)
    expected_values, expected_containers = [], []

    def walk(key, value, path):
        decoded = audit.decode_content(str(key), value)
        if decoded is not None:
            walk(key, decoded, path + '::')
        elif isinstance(value, (dict, list)) and value:
            expected_containers.append(path)
            for k, child in audit.iter_children(value):
                walk(k, child, audit.pointer(path, k))
        else:
            expected_values.append(path)

    for key, value in source['request'].items():
        walk(key, value, audit.pointer('/request', key))
    rendered = ReadablePaths(markup)
    assert Counter(rendered.values) == Counter(expected_values)
    assert Counter(rendered.containers) == Counter(expected_containers)
    text = audit.reading_text(markup)
    for literal in ('FULL SYSTEM', 'exact owner', 'full documentation', 'scope-dependent conversion', 'must remain readable'):
        assert literal in text
    assert 'CAPTURE ONLY' not in text
    assert 'Null означает отсутствие значения' in text


def test_saved_parent_relationships_are_explicit_facts_not_new_design():
    program = {'primaryEntityId': 'held', 'entities': [{'id': 'turret', 'kind': 'stationary_projectile',
                 'targeting': {'shotEntityId': 'bolt'}}],
               'bindings': [{'id': 'alt', 'role': 'secondary', 'input': 'alternate_use',
                 'usePolicy': {'action': {'kind': 'spawn_entity', 'targetId': 'turret'}}}]}
    markup = audit.reading_layer({'parents': {'A': {'packet': {'name': 'Test', 'raw': {'runtimeProgram': program}}}}})
    text = audit.reading_text(markup)
    assert 'альтернативное использование (alternate_use) → действие создать сущность (spawn_entity) → сущность turret' in text
    assert 'turret ссылается на bolt' in text
    assert 'не предложение механики нового предмета' in text
    assert 'Роль сообщения' not in text


def test_catalog_parameter_rules_do_not_leak_to_arbitrary_params():
    markup = audit.reading_layer({'response_format': {'properties': {'params': {'type': 'object'}}}})
    assert 'Параметры capability обязательны' not in audit.reading_text(markup)
    assert 'наличие поля в properties само по себе не делает его обязательным' in audit.reading_text(markup)


@pytest.mark.parametrize('packet', [None, 'unknown', False, [], 0])
def test_nonobject_parent_packets_are_visible_not_crashes(packet):
    source = {'parents': {'A': {'packet': packet}}}
    markup = audit.reading_layer(source)
    assert '/parents/A/packet' in ReadablePaths(markup).values


def test_nested_unknown_instruction_shapes_keep_all_values_and_containers():
    source = {'priorityHeader': [{'unknownRule': {'x': 0, 'empty': []}}, 'ok']}
    rendered = ReadablePaths(audit.reading_layer(source))
    assert rendered.values == ['/priorityHeader/0/unknownRule/x', '/priorityHeader/0/unknownRule/empty', '/priorityHeader/1']
    assert '/priorityHeader/0/unknownRule' in rendered.containers


def test_parent_unit_docs_require_exact_scope_and_selector_and_keep_raw_numbers():
    source = {'catalog': {'authoringSchema': 'test', 'capabilities': [
        {'fn': 'motion', 'params': {'velocity': {'type': 'number', 'meaning': 'Declared velocity'}}}]},
        'parents': {'A': {'packet': {'raw': {'moving': [{'mode': 'per_update', 'speed': 11}, {'mode': 'other', 'speed': 22}], 'elsewhere': {'speed': 33}}}}},
        'sourceWireUnits': {'scopes': [{'source': 'raw.moving[]', 'fn': 'motion', 'when': {'mode': 'per_update'},
            'fields': {'speed': ['velocity', 'source * 60 * updatesPerTick / 16', 'blocks/s']}}]}}
    notes = audit.parent_field_notes(source, '')
    assert list(notes) == ['/parents/A/packet/raw/moving/0/speed']
    markup = audit.reading_layer(source)
    assert 'source * 60 * updatesPerTick / 16' in audit.reading_text(markup)
    assert 'Смысл и ограничения параметра' in markup
    assert source['parents']['A']['packet']['raw']['moving'][0]['speed'] == 11


def test_default_token_and_source_speed_labels_do_not_invent_semantics():
    markup = audit.reading_layer({'fieldGuide': {'damageClass': {'meaningByToken': {'default': 'Unclassed'}}},
                                 'speedPxPerTick': 11})
    assert 'Значение токена · default' in markup
    assert 'Скорость в пикселях за тик' not in markup


def test_provider_text_input_is_not_labeled_as_game_control():
    markup = audit.reading_layer({'input': 'Provider prompt'})
    assert 'Способ активации' not in markup
    assert 'Входные данные' in markup


def test_duplicate_function_names_do_not_choose_arbitrary_parent_doc_link():
    source = {'catalog': {'authoringSchema': 'test', 'capabilities': [
        {'fn': 'f', 'params': {'p': {'meaning': 'first'}}},
        {'fn': 'f', 'params': {'p': {'meaning': 'second'}}}]},
        'parents': {'A': {'packet': {'raw': {'x': 1}}}},
        'sourceWireUnits': {'scopes': [{'source': 'raw', 'fn': 'f', 'fields': {'x': ['p', 'source', 'unit']}}]}}
    notes = audit.parent_field_notes(source, '')
    assert len(notes) == 1
    assert 'Смысл и ограничения параметра' not in str(notes)


@pytest.mark.parametrize('payload', [None, 'future request', [], {}])
def test_unrecognised_or_empty_request_payload_is_auditable(payload):
    source = {'request': payload}
    document, _, _ = audit.build_report(json.dumps(source).encode(), 'future.json')
    assert raw_from(document) == json.dumps(source).encode()
    assert ReadablePaths(audit.reading_layer(source)).values == ['/request']


def test_complete_reader_resolves_only_explicit_parameter_documentation():
    rule = 'configure_armor params without meaning inherit exact meaning from configure_accessory params of the same name; all own bounds and units still apply.'
    catalog = {'authoringSchema': 'test', 'fieldGuide': {'armorParamInheritance': rule,
                'types': {'window': {'description': 'Phase conditions.'}}}, 'capabilities': [
        {'fn': 'configure_accessory', 'params': {'power': {'meaning': 'Exact accessory meaning.', 'max': 99}}},
        {'fn': 'configure_armor', 'params': {'power': {'max': 3, 'optional': True}}},
        {'fn': 'move', 'params': {'window': {'typeRef': 'window'}}}]}
    text = audit.reading_text(audit.reading_layer({'catalog': catalog}))
    assert text.count('Exact accessory meaning.') == 2
    assert text.count('Phase conditions.') == 2
    assert 'Необязателен; не больше: 3.' in text
    catalog['fieldGuide']['armorParamInheritance'] = 'different future rule'
    text = audit.reading_text(audit.reading_layer({'catalog': catalog}))
    assert text.count('Exact accessory meaning.') == 1


def test_export_table_of_contents_has_readable_separate_lines():
    text = audit.reading_text(audit.reading_layer({'model': 'test', 'messages': []}))
    assert 'Содержание полного аудита\n\nМодель в сохранённом запросе\n\n' in text
