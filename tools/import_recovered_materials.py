"""Archive recovered game-data files without fetching APIs or executing old code.

Usage: python tools/import_recovered_materials.py --source-root PATH --downloads PATH
Large text files use deterministic gzip; SHA-256 records both original and archive.
Identical files share one archived copy, with every source alias retained.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
TEXT = {'.csv', '.json', '.jsonl', '.txt', '.md', '.py', '.tex', '.tmp'}
EXTRA = {
    'annotation_agent_spec_v001.md', 'run_annotation_fast_v003.py',
    'enrich_steam_master_archetypes_v1.py', 'archetypal_game_protagonists_corpus.xlsx',
    'merged_rows_with_visibility_weights.csv', 'half_decade_game_counts_v2.csv',
    'half_decade_counts_table_v2.tex', 'make_archetype_year_matrices_normalized_v002.py',
    'make_archetype_year_matrices_v001.py', 'archetype_visibility_weight_scenarios.py',
    'archetype_visibility_weight_outputs_v001.zip',
    'archetype_year_matrices_and_heatmaps_v001.zip',
    'archetype_year_outputs_normalized_v002.zip',
}
REPORT_PREFIX = ('archetype_raw_share_', 'archetype_review_weighted_share_',
                 'archetype_year_heatmaps_', 'archetype_year_linecharts_',
                 'decade_archetype_shares_', 'fiveyear_archetype_shares_',
                 'year_archetype_shares_', 'fig_all12_archetypes_',
                 'fig_archetype_', 'fig_everyman_caregiver_', 'fig_hero_explorer_',
                 'fig_protagonist_', 'fig_rebel_sage_', 'table_archetype_',
                 'table_protagonist_', 'table1_revised_protagonist_')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def scan_credentials(path):
    # Report only paths, never the matched credential. Corpus files contain public
    # game metadata; participant workbooks are deliberately outside the allowlist.
    if path.suffix.lower() not in TEXT:
        return
    patterns = [rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}',
                rb'\bgh[pousr]_[A-Za-z0-9]{30,}',
                rb'github_pat_[A-Za-z0-9_]{30,}',
                rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'"(?:access_token|client_secret|api_key)"\s*:\s*"[A-Za-z0-9_-]{24,}"']
    tail = b''
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            text = tail + chunk
            if any(re.search(p, text) for p in patterns):
                raise RuntimeError('Possible credential; inspect before archiving: ' + path.name)
            tail = chunk[-256:]

def candidates(source, downloads):
    for p in sorted(source.rglob('*')):
        if p.is_file() and p.suffix.lower() in TEXT | {'.gz', '.png', '.xlsx'}:
            yield p, 'DataSteam/' + p.relative_to(source).as_posix()
    for p in sorted(downloads.iterdir()):
        if not p.is_file():
            continue
        # Old numbered downloads are retained as aliases if byte-identical.
        if (p.name.startswith(('igdb_', 'steam_')) and p.suffix.lower() in TEXT | {'.gz', '.xlsx'}) or p.name in EXTRA or p.name.startswith(REPORT_PREFIX):
            yield p, 'Downloads/' + p.name
    p = downloads / 'steam_cache/app_list.tmp'
    if p.exists():
        yield p, 'Downloads/steam_cache/app_list.tmp'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--downloads', type=Path, required=True)
    args = parser.parse_args()
    prior = json.loads((ROOT / 'provenance/originals.json').read_text(encoding='utf-8'))
    by_hash = {r['archived_sha256']: {'path': r['path'], 'encoding': 'original',
               'archived_sha256': r['archived_sha256'], 'archive_bytes': (ROOT/r['path']).stat().st_size}
               for r in prior if r['source_sha256'] == r['archived_sha256']}
    rows = []
    for i, (src, alias) in enumerate(candidates(args.source_root, args.downloads), 1):
        scan_credentials(src)
        sha = digest(src)
        if sha not in by_hash:
            rel = Path('data/recovered') / alias
            compress = src.suffix.lower() in TEXT and src.stat().st_size > 1_000_000
            if compress:
                rel = Path(str(rel) + '.gz')
            dest = ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                if compress:
                    with src.open('rb') as inp, dest.open('wb') as raw:
                        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as out:
                            shutil.copyfileobj(inp, out, 1024 * 1024)
                else:
                    shutil.copyfile(src, dest)
            if dest.stat().st_size > 95 * 1024 * 1024:
                raise RuntimeError('Archive file exceeds 95 MiB: ' + str(rel))
            # Never accept an existing file merely because its filename matches.
            opener = gzip.open if compress else open
            h = hashlib.sha256()
            with opener(dest, 'rb') as f:
                for block in iter(lambda: f.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != sha:
                raise RuntimeError('Archive round-trip mismatch: ' + str(rel))
            by_hash[sha] = {'path': rel.as_posix(), 'encoding': 'gzip' if compress else 'original',
                            'archived_sha256': digest(dest), 'archive_bytes': dest.stat().st_size}
        rows.append({'source': alias, 'original_sha256': sha,
                     'original_bytes': src.stat().st_size, **by_hash[sha]})
        if i % 30 == 0:
            print(f'Archived and verified {i} source files', flush=True)
    rows.sort(key=lambda r: r['source'])
    target = ROOT / 'provenance/data-manifest.json'
    target.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    with (ROOT/'provenance/data-manifest.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# Complete recovered-file index', '',
             'Every source alias maps to an archived file. Identical downloads share one copy.',
             'Gzip files preserve the complete original bytes on decompression; they are not samples.', '',
             '| Recovered source | Archive | Original bytes | Storage |', '|---|---|---:|---|']
    for r in rows:
        lines.append(f"| `{r['source']}` | [file](../{quote(r['path'])}) | {r['original_bytes']:,} | {r['encoding']} |")
    (ROOT/'docs/recovered-file-index.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    unique = {r['path']: r for r in rows}
    summary = {'source_files': len(rows), 'unique_archived_files': len(unique),
               'source_bytes_including_duplicates': sum(r['original_bytes'] for r in rows),
               'unique_original_bytes': sum(r['original_bytes'] for r in unique.values()),
               'archive_bytes': sum(r['archive_bytes'] for r in unique.values())}
    (ROOT/'provenance/import-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)

if __name__ == '__main__':
    main()
