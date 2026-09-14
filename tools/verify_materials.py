"""Offline integrity and provenance checks; no model inference."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root/'provenance/originals.json').read_text(encoding='utf-8'))
for row in manifest:
    data=(root/row['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==row['archived_sha256'], row['path']
for p in root.rglob('*.json'):
    if '.git' not in p.parts: json.loads(p.read_text(encoding='utf-8-sig'))
outputs={}
for line in (root/'archive/batch/steam_v005_top1000_55_output.jsonl').read_text(encoding='utf-8-sig').splitlines():
    r=json.loads(line)
    for o in r.get('response',{}).get('body',{}).get('output',[]):
        for c in o.get('content',[]):
            if c.get('text'):
                for item in json.loads(c['text']).get('items',[]):
                    outputs[(r['custom_id'],str(item['a']))]=item
cases=json.loads((root/'comparison/game_character_llm_source.json').read_text(encoding='utf-8'))
for c in cases:
    raw=outputs[(c['custom_id'],c['appid'])]
    assert raw['pn']==c['llm_protagonist_original']
    assert c['source_archetype_original']=='padre circunstancial'
    assert 'proposed interpretation' in c['mapped_archetype_12']
config=(root/'annotation-interface/config.js').read_text(encoding='utf-8')
assert "GOOGLE_SHEETS_WEB_APP_URL: ''" in config
assert 'connect-src \'self\'' in (root/'annotation-interface/index.html').read_text(encoding='utf-8')
print(f'PASS: {len(manifest)} archived hashes, JSON syntax, {len(cases)} recorded-output links, demo endpoint disabled')
