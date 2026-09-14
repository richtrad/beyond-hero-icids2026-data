"""Recover a bounded supplement from specified local originals. No network or inference.

Run into a new repository; identical files may be reused after interruption.
"""
import ast
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEAM = Path.home() / 'Documents' / 'DataSteam'
DOWNLOADS = Path.home() / 'Downloads'
WHEEL = ROOT.parent / 'grafitctu.github.io' / 'archetype-validator-git'
manifest = []

def sha(data):
    return hashlib.sha256(data).hexdigest()

def put(relative, data):
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    data = data.encode('utf-8') if isinstance(data, str) else data
    if target.exists():
        if target.read_bytes() == data:
            return
        raise FileExistsError('Refusing to overwrite changed file: ' + str(target))
    with target.open('xb') as f:
        f.write(data)

def recover(source, relative, transform=None, note='byte-preserved'):
    raw = source.read_bytes()
    data = transform(raw) if transform else raw
    put(relative, data)
    if isinstance(data, str):
        data = data.encode('utf-8')
    manifest.append(dict(source_name=source.name, path=relative, source_sha256=sha(raw),
                         archived_sha256=sha(data), transformation=note))

def save_json(relative, obj):
    put(relative, json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

scripts = sorted(STEAM.glob('steam_prepare_protagonist_batch_v*.py'))
scripts += [STEAM / 'steam_prepare_rest_parts_v006_54mini.py',
            STEAM / 'steam_make_final_archetype_datasets_12_v001.py']
prompt_index = []
for path in scripts:
    recover(path, 'archive/code/' + path.name)
    text = path.read_text(encoding='utf-8-sig')
    tree = ast.parse(text)
    relevant = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [x.id for x in node.targets if isinstance(x, ast.Name)]
            if 'SYSTEM_PROMPT' in names:
                try:
                    prompt = ast.literal_eval(node.value)
                    status = 'extracted_original_literal'
                    suffix = '.system.txt'
                except (ValueError, TypeError):
                    prompt = ast.get_source_segment(text, node)
                    status = 'original_template_expression_not_evaluated'
                    suffix = '.system-template.py.txt'
                out = 'prompts/' + path.stem + suffix
                put(out, prompt)
                prompt_index.append(dict(path=out, source='archive/code/' + path.name,
                                         source_line=node.lineno, status=status))
            if any('SCHEMA' in n or n.endswith('_CODES') for n in names):
                relevant.append(ast.get_source_segment(text, node))
        if isinstance(node, ast.FunctionDef) and node.name in ['row_to_game','make_user_prompt']:
            relevant.append(ast.get_source_segment(text, node))
    if relevant:
        put('prompts/' + path.stem + '.input-and-schema.py.txt', '\n\n'.join(relevant) + '\n')

for n in ['annotation_agent_spec_v001.md','run_annotation_fast_v003.py',
          'igdb_metadata_agent_annotation_summary_v001.json']:
    recover(DOWNLOADS / n, 'archive/igdb/' + n)

for n in ['steam_v005_top1000_55_input.jsonl','steam_v005_top1000_55_output.jsonl']:
    recover(STEAM / 'steam_bulk_outputs' / n, 'archive/batch/' + n)

summary = STEAM / 'steam_bulk_outputs/final_archetype_datasets_12_v001'
for n in ['README_final_datasets_12_v001.md','steam_dataset_summary_12_v001.json']:
    recover(summary / n, 'archive/steam/' + n)

for path in sorted(WHEEL.iterdir()):
    if path.suffix not in ['.js','.css','.json','.html'] or path.name in ['config.js','google-apps-script.js']:
        continue
    def demo(raw, name=path.name):
        text = raw.decode('utf-8-sig')
        if name.endswith('.js'):
            for key in ['archetype_current_index','archetype_responses_jsonl','archetype_participant_id']:
                text = text.replace(key, 'icids17_demo_' + key)
        if name == 'index.html':
            text = text.replace('<head>', '''<head>
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'">''')
            text = text.replace('<body>', '<body>\n  <p style="padding:12px;text-align:center;background:#fff4d9;color:#382700">Archivní ukázka hodnoticího kola. Odpovědi se ukládají pouze lokálně v tomto prohlížeči.</p>')
        return text
    recover(path, 'annotation-interface/' + path.name, demo,
            'UTF-8 copy; local-storage keys isolated where present; HTML demo notice and same-origin CSP added')
put('annotation-interface/config.js', "window.ARCHETYPE_CONFIG = { GOOGLE_SHEETS_WEB_APP_URL: '', KEEP_LOCAL_BACKUP: true, MAX_SELECTIONS: 3 };\n")

characters = json.loads((WHEEL/'characters.json').read_text(encoding='utf-8-sig'))
queue=[]
for row in characters:
    queue.append({
        'record_id':row.get('id',''), 'game':row.get('game',''),
        'character':row.get('character',''), 'appid':row.get('appid',''),
        'internal_primary':row.get('internal_suggested_primary_archetype',''),
        'internal_secondary':row.get('internal_suggested_secondary_archetype',''),
        'source_lead':row.get('internal_archetype_source_url','') or row.get('source_url',''),
        'source_archetype_original':'', 'citation':'',
        'comparison_status':'source_assignment_not_verified',
        'annotation_origin':'interface_internal_suggestion_model_not_verified'
    })
save_json('comparison/interface_source_queue.json', queue)

codes={'INN':'Innocent','EVE':'Everyman/Orphan','HER':'Hero/Warrior','CAR':'Caregiver/Guardian',
       'EXP':'Explorer/Seeker','REB':'Rebel/Outlaw','LOV':'Lover','CRE':'Creator/Artist',
       'JES':'Jester/Trickster','SAG':'Sage/Investigator','MAG':'Magician/Transformer',
       'RUL':'Ruler/Leader','SHA':'Shadow/Antihero','NA':'Not applicable','UNC':'Uncertain'}
outputs={}
for line in (ROOT/'archive/batch/steam_v005_top1000_55_output.jsonl').read_text(encoding='utf-8-sig').splitlines():
    r=json.loads(line)
    body=r.get('response',{}).get('body',{})
    for o in body.get('output',[]):
        for c in o.get('content',[]):
            if not c.get('text'): continue
            for item in json.loads(c['text']).get('items',[]):
                key=str(item['a'])
                if key in outputs: raise ValueError('Duplicate appid in recorded batch output: '+key)
                outputs[key]={'item':item,'model':body.get('model',''),'custom_id':r['custom_id']}
with (summary/'steam_analysis_ready_12_v001.csv').open(encoding='utf-8-sig',newline='') as f:
    processed={r['appid']:r for r in csv.DictReader(f)}
cases=[('1593500','God of War (2018)','Kratos','Same game; Steam release is a later port.'),
       ('8870','BioShock Infinite','Booker DeWitt','Same game and named character.'),
       ('207610','The Walking Dead (Season 1)','Lee Everett','Recorded pn contains the game title; note names Lee. Preserve the raw pn.'),
       ('1888930','The Last of Us Part I','Joel Miller','Source studies The Last of Us (2013); LLM row covers Part I and codes dual protagonists. Not an exact version/unit match.')]
comparison=[]
for appid,game,character,note in cases:
    raw=outputs[appid]; item=raw['item']; p=processed[appid]
    comparison.append(dict(appid=appid,game=game,character=character,
      llm_protagonist_original=item['pn'],llm_primary_original=codes[item['p']],
      llm_secondary_original=codes[item['s']],llm_tertiary_original=codes[item['t']],
      primary_12=p['primary_archetype_12'],correction=p['archetype_12_correction_method'],
      model=raw['model'],custom_id=raw['custom_id'],
      source_archetype_original='padre circunstancial',
      mapped_archetype_12='Caregiver/Guardian (proposed interpretation)',
      citation='Freire-Sánchez, A., & Vidal-Mestre, M. (2024). La sustitución del arquetipo del mentor/educador por la figura seudopaterna en la narrativa del videojuego. Multidisciplinary Journal of School Education, 13(1(25)), 213–230. doi:10.35765/mjse.2024.1325.11',
      source_locator='Methodology and Table 2 (four father figures); Table 3 (character traits)',
      source_url='https://doi.org/10.35765/mjse.2024.1325.11',
      comparison_status='explicit_source_label_different_taxonomy',scope_note=note,
      source_checked_on='2026-09-14'))
save_json('comparison/game_character_llm_source.json',comparison)
save_json('prompts/index.json',prompt_index)
save_json('provenance/originals.json',manifest)
print(json.dumps({'archived_files':len(manifest),'system_prompts':len(prompt_index),
                  'interface_candidates':len(queue),'cited_comparisons':len(comparison)},indent=2))
