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
const second = {tagName:'DETAILS',open:false,parentElement:first,scrollIntoView(){}};
function leaf(text,parent){return {textContent:text,parentElement:parent,highlight:false,
 classList:{toggle(_name,value){this.owner.highlight=value;}},scrollIntoView(){this.scrolled=true;}};}
const a=leaf('Alpha /a',second), b=leaf('Beta alpha /b',first);a.classList.owner=a;b.classList.owner=b;
const els={search:{value:''},status:{textContent:''},original:{textContent:'77u/eyJ4IjoxfQ0K'},readable:{textContent:'0KLQtdC60YHRgg=='}};
for(const name of ['search-button','next','expand','collapse','raw-download','text-download'])els[name]={};
els.target=second;
const events={};let blob;
const context={document:{querySelectorAll:s=>s.startsWith('details')?[first,second]:[a,b],getElementById:id=>els[id],
 createElement:()=>({click(){}})},window:{addEventListener:(name,fn)=>events[name]=fn},location:{hash:''},
 Blob:class{constructor(parts){blob=parts[0];}},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
 Uint8Array,atob:s=>Buffer.from(s,'base64').toString('binary'),setTimeout:fn=>fn()};
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
els.collapse.onclick();context.location.hash='#target';events.hashchange();assert(first.open&&second.open);
'''
    program = harness + '\nvm.runInContext(' + json.dumps(script) + ',context);\n' + checks
    file = tmp_path / 'controls.cjs'
    file.write_text(program)
    subprocess.run([node, str(file)], check=True, capture_output=True, text=True, timeout=15)
