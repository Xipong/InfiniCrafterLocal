"""Offline real builders/senders; immutable baseline 28621ad, no model calls."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
ART = Path(__file__).resolve().parent
STAGES = ['author', 'repair', 'format', 'visual', 'visual_repair', 'vfx', 'vfx_repair']
MODES = ['json_object', 'json_schema', 'off']
BASE = '28621ad'

def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()

if len(sys.argv) > 1:
    source = Path(sys.argv[1])
    sys.path[:0] = [str(source / 'LocalGenerator'), str(ROOT / 'LocalGenerator/tests')]
    os.environ.update(INFINI_SKIP_CONFIG_FILE='1', INFINI_USE_LLM='0', INFINI_SDCPP_SERVER_AUTOSTART='0')
    socket.socket.connect = lambda *a: (_ for _ in ()).throw(AssertionError('offline network attempted'))
    import pytest
    from test_craft_instruction_segments import stage_packets
    from test_stable_schema_data import PROVIDERS, capture_wire
    from prompt_packet_helpers import request_dossier, dossier_text
    from infini_local.pipelines import llm_transport as transport
    records = []
    for mode in MODES:
        for stage in STAGES:
            with pytest.MonkeyPatch.context() as mp:
                packets = stage_packets(mp, stage, format_mode=mode)
                for case, packet in enumerate(packets):
                    rows = packet['messages']
                    endpoint = packet['_infini_prompt_cache'].get('staticDataMessageIndex', 1)
                    wires = []
                    for provider, base, api, model in PROVIDERS:
                        context = dict(provider=provider, base_url=base, api_mode=api, model=model, api_key='offline')
                        wire = capture_wire(mp, packet, context)
                        wires.append({'provider': provider, 'api': api, 'base': base, 'key': wire['prompt_cache_key'], 'wireSha256': digest(wire)})
                    dossier = request_dossier(packet)
                    schema_key = 'responseSchema' if stage.startswith('visual') else 'outputSchema' if stage.startswith('vfx') else None
                    records.append(dict(mode=mode, stage=stage, case=case, dossier=dossier,
                        dossierText=dossier_text(packet), system=rows[0], options={k:v for k,v in packet.items() if k not in {'messages','_infini_prompt_cache'}},
                        instructionsChars=len(rows[1]['content']), staticSchemaChars=len(rows[2]['content']) if endpoint == 2 else 0,
                        staticSchemaBytes=len(rows[2]['content'].encode()) if endpoint == 2 else 0,
                        dynamicChars=len(rows[endpoint+1]['content']), fullSchemaChars=len(encode(dossier[schema_key])) if schema_key else None,
                        compactSchemaChars=len(encode(json.loads(rows[-1]['content'])[schema_key])) if schema_key else None,
                        staticSha256=digest(rows[:endpoint+1]), totalChars=sum(len(row['content']) for row in rows), wires=wires))
    Path(sys.argv[2]).write_text(json.dumps(records, ensure_ascii=False, indent=2))
else:
    baseline = Path(os.environ['TMPDIR']) / 'stable-director-schema-28621ad'
    if not baseline.exists():
        baseline.mkdir()
        raw = subprocess.check_output(['git', '-C', str(ROOT), 'archive', BASE])
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            archive.extractall(baseline, filter='data')
    outputs = []
    for label, source in [('base', baseline), ('candidate', ROOT)]:
        out = ART / (label + '-offline-packets.json')
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(source), str(out)], capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        outputs.append(json.loads(out.read_bytes()))
    receipts = []
    for base, current in zip(*outputs):
        assert (base['stage'], base['case'], base['mode']) == (current['stage'], current['case'], current['mode'])
        assert encode(base['dossier']) == encode(current['dossier']), (base['stage'], base['mode'])
        assert base['dossierText'] == current['dossierText']
        assert base['system'] == current['system'] and base['options'] == current['options']
        if base['stage'] in {'author','repair','format'}:
            assert base['wires'] == current['wires'], base['stage']
        receipts.append({k:current[k] for k in ['mode','stage','case','instructionsChars','staticSchemaChars','staticSchemaBytes','dynamicChars','fullSchemaChars','compactSchemaChars','totalChars']})
        receipts[-1].update(baseDynamicChars=base['dynamicChars'], baseTotalChars=base['totalChars'], literalDossierParity=True, systemOptionsParity=True)
    for current in outputs[1][::2]:
        other = outputs[1][outputs[1].index(current)+1]
        assert current['staticSha256'] == other['staticSha256']
        assert [w['key'] for w in current['wires']] == [w['key'] for w in other['wires']]
    report = dict(base=BASE, networkAttempts=0, realBuilderPackets=len(receipts), providerWirePackets=sum(len(r['wires']) for r in outputs[1]),
        literalDossierParity=True, systemOptionsParity=True, allAuthorStagesWireAndKeyParity=True, measurements=receipts)
    (ART/'offline-parity.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='measurements'}, indent=2))
    for row in receipts:
        if row['mode']=='json_object' and row['case']==0:
            print(row)
