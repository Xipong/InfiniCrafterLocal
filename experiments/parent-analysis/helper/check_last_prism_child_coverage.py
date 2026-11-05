"""Diagnostic RED for required native helper-spawn coverage, not a released-contract test.

Uses independently executed native AI_075 terminal spawn observations as the oracle.
The runtime oracle, not this script, supplies expected child IDs. No inference/network.
"""
import json
from pathlib import Path
root=Path(__file__).resolve().parent
capture=root/'capture-v3'
oracle=json.loads((capture/'last-prism-ai-oracle.json').read_text())
parent=json.loads((capture/'LastPrism.packet.json').read_text())['itemA']
assert oracle['error'] is None, oracle['error']
assert len(oracle['spawns'])==6, 'Native witness must be the six-beam first AI tick'
expected={row['type'] for row in oracle['spawns']}
raw=parent['directProjectileRaw']
actual={row['type'] for row in raw.get('referencedProjectiles',{}).get('references',[]) if 'profile' in row}
report={'case':'actual native LastPrism AI helper emits children',
        'oracleMethod':oracle['method'],'nativeSpawnCount':len(oracle['spawns']),
        'expectedChildProfileTypes':sorted(expected),'capturedChildProfileTypes':sorted(actual),
        'missingChildProfileTypes':sorted(expected-actual),
        'result':'RED' if expected-actual else 'GREEN',
        'sourceGraphUnresolved':parent['parentSourceGraph']['unresolved'],
        'classification':'preexisting bounded producer coverage gap, not PR330 regression or corrupt numeric defaults'}
(root/'last-prism-coverage-red.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
assert expected <= actual, f'Native helper child profiles lost: {sorted(expected-actual)}'
