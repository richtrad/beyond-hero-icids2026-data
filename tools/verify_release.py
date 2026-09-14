"""Offline archive, overview and documentation checks. No network access.

Use --full to verify original bytes after gzip decompression as well.
"""
import argparse
import csv
import gzip
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1]

def sha(path, decompress=False):
    h=hashlib.sha256()
    opener=gzip.open if decompress else open
    with opener(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--full',action='store_true');args=p.parse_args()
    rows=json.loads((ROOT/'provenance/data-manifest.json').read_text(encoding='utf-8'))
    assert len({r['source'] for r in rows})==len(rows)
    seen={}
    for r in rows:
        path=(ROOT/r['path']).resolve()
        assert path.is_relative_to(ROOT.resolve()),r['path']
        if r['path'] not in seen:
            assert path.stat().st_size==r['archive_bytes'],r['path']
            assert path.stat().st_size < 95*1024*1024,r['path']
            assert sha(path)==r['archived_sha256'],r['path']
            if args.full:assert sha(path,r['encoding']=='gzip')==r['original_sha256'],r['path']
            seen[r['path']]=r
        else:
            assert seen[r['path']]['original_sha256']==r['original_sha256'],r['path']
    for r in json.loads((ROOT/'provenance/overview-artifacts.json').read_text()):
        assert sha(ROOT/r['path'])==r['sha256'],r['path']
    with (ROOT/'results/tables/title_year_counts_corrected.csv').open() as f:
        counts=list(csv.DictReader(f))
    assert sum(int(r['title_year_combinations']) for r in counts)==90180
    assert next(int(r['title_year_combinations']) for r in counts if r['period']=='2020--2024')==35652
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    bib=(ROOT/'CITATION.bib').read_text(encoding='utf-8').strip()
    assert bib in readme and 'kindly ask you to cite' in readme.split('##')[0]
    assert '10.' not in bib and 'forthcoming' in bib
    docs=[ROOT/'README.md',*sorted((ROOT/'docs').glob('*.md')),*sorted((ROOT/'paper').glob('*.md'))]
    missing=[]
    for doc in docs:
        txt=doc.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)',txt):
            if target.startswith(('http:','https:','mailto:','#')):continue
            target=unquote(target.split('#')[0])
            if not (doc.parent/target).exists():missing.append((str(doc.relative_to(ROOT)),target))
    assert not missing,missing
    assert not any('Archetypes (' in r['source'] or r['source'].endswith('Archetypes.xlsx') for r in rows)
    print(f'PASS: {len(rows)} source aliases; {len(seen)} unique archive hashes; '
          f'overview hashes, corrected counts, citation and {len(docs)} documentation link checks; '
          f'original-byte checks={args.full}',flush=True)

if __name__=='__main__':main()
