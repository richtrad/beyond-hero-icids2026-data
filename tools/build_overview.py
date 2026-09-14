"""Build the release index, timeline, count reconciliation and plots offline.

Requires pandas and matplotlib. Reads only files already indexed in this repository.
"""
from __future__ import annotations
import csv
import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from plot_archetype_stories import build_stories

ROOT=Path(__file__).resolve().parents[1]

def main():
    records=json.loads((ROOT/'provenance/data-manifest.json').read_text(encoding='utf-8'))
    manifest={r['source']:r for r in records}
    def source(alias):
        return ROOT/manifest[alias]['path']
    def link(alias, prefix='../'):
        return prefix+quote(manifest[alias]['path'])
    def frame(alias):
        return pd.read_csv(source(alias),encoding='utf-8-sig',keep_default_na=False,low_memory=False)
    def write(rel, text):
        p=ROOT/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
    (ROOT/'results/figures').mkdir(parents=True,exist_ok=True)
    (ROOT/'results/tables').mkdir(parents=True,exist_ok=True)
    aliases={
      'Steam catalogue, all downloaded application IDs':'DataSteam/steam_bulk_outputs/steam_catalog_games.csv',
      'SteamSpy all-snapshot':'DataSteam/steam_bulk_outputs/steamspy_all_snapshot.csv',
      'Merged Steam-side catalogue':'DataSteam/steam_bulk_outputs/steam_catalog_merged.csv',
      'Steam broad review-filtered pool':'DataSteam/steam_bulk_outputs/steam_archetype_broad_pool.csv',
      'Steam batch selection and harmonized labels':'DataSteam/steam_bulk_outputs/final_archetype_datasets_12_v001/steam_analysis_ready_12_v001.csv',
      'IGDB raw catalogue, all downloaded years':'DataSteam/igdb_outputs/master_candidates_v001/igdb_master_raw_all_years_v001.csv',
      'IGDB raw catalogue through 2025':'DataSteam/igdb_outputs/master_candidates_v001/igdb_master_raw_analysis_years_v001.csv',
      'IGDB broad candidates through 2025':'DataSteam/igdb_outputs/master_candidates_v001/igdb_master_broad_analysis_years_v001.csv',
      'IGDB annotated master':'Downloads/igdb_master_broad_with_metadata_agent_annotations_v001.csv.gz',
      'Simplified full annotated master':'Downloads/igdb_archetype_annotations_simple_master_v001.csv',
      'Protagonist-only export, original':'Downloads/igdb_archetype_annotations_simple_characters_only_v001.csv',
      'Analytical rows with visibility weights':'Downloads/merged_rows_with_visibility_weights.csv',
    }
    catalog=[]
    for title,alias in aliases.items():
        path=source(alias)
        opener=gzip.open if path.suffix=='.gz' else open
        with opener(path,'rt',encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f); columns=next(reader); n=sum(1 for row in reader if row)
        catalog.append({'dataset':title,'rows':n,'source':alias,'path':manifest[alias]['path'],'columns':columns})
        print(title,n,flush=True)
    write('provenance/dataset-statistics.json',json.dumps(catalog,indent=2,ensure_ascii=False)+'\n')
    cat=['# Data catalogue','', '[Overview](../README.md) · [How the data were created](how-the-evaluation-was-created.md)','',
         'These are complete recovered files, not top-game samples. Counts below were parsed from the archived CSV files. Different stages overlap: do not sum rows across tables. Historical acquisition does not imply complete coverage of either platform.','',
         '| Dataset | Rows | Download |','|---|---:|---|']
    for r in catalog:
        cat.append(f"| {r['dataset']} | {r['rows']:,} | [CSV{' (gzip)' if r['path'].endswith('.gz') else ''}](../{quote(r['path'])}) |")
    cat+=['','## All recovered files','',
          'The [complete file index](recovered-file-index.md) also includes original API-response caches, acquisition scripts, batch requests and outputs, earlier versions, checkpoints, comparison tables and plotting sources. The machine-readable [manifest](../provenance/data-manifest.csv) records every original alias, archived path, size and both SHA-256 hashes. Byte-identical copies share one archive file.','',
          'Gzip compression preserves all rows and original bytes. For example, pandas can open a `.csv.gz` directly with `pd.read_csv(path)`. The archive scripts are historical research code, not automatically executed by the verification command.','',
          '## Column schemas','']
    for r in catalog:
        cat += [f"### {r['dataset']}",'',', '.join('`'+c+'`' for c in r['columns']),'']
    write('docs/data-catalogue.md','\n'.join(cat).rstrip()+'\n')

    # Record job timestamps from status files; no filesystem dates are substituted.
    timeline=[]
    for alias,r in manifest.items():
        if alias.startswith('DataSteam/steam_bulk_outputs/') and alias.endswith('_status.json'):
            obj=json.loads(source(alias).read_text(encoding='utf-8-sig'))
            if not isinstance(obj,dict) or not isinstance(obj.get('created_at'),int):continue
            def utc(key):
                val=obj.get(key)
                return datetime.fromtimestamp(val,timezone.utc).isoformat() if isinstance(val,int) else ''
            timeline.append({'source':alias,'model':obj.get('model',''),'status':obj.get('status',''),
                             'created_utc':utc('created_at'),'completed_utc':utc('completed_at'),
                             'completed_requests':obj.get('request_counts',{}).get('completed','')})
    timeline.sort(key=lambda r:(r['created_utc'],r['source']))
    write('provenance/run-timeline.json',json.dumps(timeline,indent=2)+'\n')
    tl=['# Recorded batch timeline','',
        'Times below are converted from recorded Unix timestamps to UTC. A completion window is not measured runtime. Completed requests can contain multiple games. Missing completion times remain blank. Earlier pilots and failed jobs are retained, not asserted to contribute to the final corpus.','',
        '| Job record | Model snapshot | Status | Created (UTC) | Completed (UTC) | Completed requests |','|---|---|---|---|---|---:|']
    for r in timeline:
        tl.append(f"| [{Path(r['source']).name}]({link(r['source'])}) | `{r['model']}` | {r['status']} | {r['created_utc']} | {r['completed_utc']} | {r['completed_requests']} |")
    tl+=['','IGDB summaries record 22 June 2026 timestamps without timezone offsets; see the [method page](how-the-evaluation-was-created.md). The exact date of the later metadata-only annotation step remains unverified.']
    write('docs/run-timeline.md','\n'.join(tl)+'\n')

    # Reconcile title strings, title-year combinations and protagonist rows.
    original=frame('Downloads/igdb_archetype_annotations_simple_characters_only_v001.csv')
    weighted=frame('Downloads/merged_rows_with_visibility_weights.csv')
    named=original[original['jméno hry'].astype(str).str.strip().ne('')].copy()
    combos=named[['jméno hry','rok vydání']].drop_duplicates().copy()
    combos['year']=pd.to_numeric(combos['rok vydání'],errors='raise').astype(int)
    combos['start']=(combos['year']//5)*5
    counts=combos.groupby('start').size().reset_index(name='title_year_combinations')
    counts['period']=counts['start'].map(lambda x:f'{x}--{x+4}' if x!=2025 else '2025 (partial)')
    counts[['period','title_year_combinations']].to_csv(ROOT/'results/tables/title_year_counts_corrected.csv',index=False)
    assert len(original)==90388 and len(named)==90387 and len(weighted)==90387
    assert len(combos)==90180 and named['jméno hry'].nunique()==89043
    original_keys=set(map(tuple,named[['jméno hry','rok vydání','jméno protagonisty']].astype(str).values))
    weighted_keys=set(map(tuple,weighted[['game','year','protagonist']].astype(str).values))
    assert original_keys==weighted_keys
    reconciliation={'original_protagonist_rows':len(original),'blank_title_rows':len(original)-len(named),
                    'nonempty_title_protagonist_rows':len(named),'distinct_title_strings':named['jméno hry'].nunique(),
                    'distinct_title_year_combinations':len(combos),'visibility_export_rows':len(weighted),
                    'named_identity_tuple_sets_equal':original_keys==weighted_keys}
    write('provenance/corpus-counts.json',json.dumps(reconciliation,indent=2)+'\n')
    cnt=['# Corpus count reconciliation','',
         'The counts refer to different units. Identical names in different years can identify different games, versions or releases. A title string is not a globally unique game identifier.','',
         '| Unit | Count |','|---|---:|', '| Original protagonist-only rows | 90,388 |',
         '| Rows with a non-empty game title | 90,387 |','| Distinct non-empty title strings | 89,043 |',
         '| Distinct non-empty title–year combinations | 90,180 |','',
         'The original half-decade table totals 90,181 and includes one blank-title record from 2020. Excluding that record changes 2020–2024 from 35,653 to **35,652** and the total to **90,180**. The visibility export already excludes the blank-title row. The non-empty `(title, year, protagonist)` identity sets match between these two exports. This check does not establish agreement of every metadata or annotation field.','',
         '| Release period | Title–year combinations |','|---|---:|']
    for r in counts.itertuples():cnt.append(f'| {r.period} | {r.title_year_combinations:,} |')
    cnt+=['| **Total** | **90,180** |','',
          'Reproduce with `python tools/build_overview.py`. The [corrected CSV](../results/tables/title_year_counts_corrected.csv) is generated separately; the [original table]('+link('Downloads/half_decade_game_counts_v2.csv')+') remains unchanged. Existing archived figure exports are preserved, not silently regenerated as if this correction had been part of their original computation.']
    write('docs/corpus-counts.md','\n'.join(cnt)+'\n')

    raw=frame('Downloads/archetype_raw_share_by_half_decade_v2.csv')
    vis=frame('Downloads/archetype_review_weighted_share_by_half_decade_v2.csv')
    periods=[f'{x}--{x+4}' for x in range(1980,2025,5)]
    raw=raw.set_index('period').loc[periods].astype(float)
    vis=vis.set_index('period').loc[periods].astype(float)
    raw.to_csv(ROOT/'results/tables/raw_archetype_shares_1980_2024.csv')
    vis.to_csv(ROOT/'results/tables/visibility_weighted_archetype_shares_1980_2024.csv')
    build_stories()
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,2,figsize=(13,4.8),sharey=True,layout='constrained')
    colors={'Hero/Warrior':'#cb6d22','Explorer/Seeker':'#528336','Everyman/Orphan':'#8059a0'}
    for ax,data,title in zip(axes,[raw,vis],['Corpus composition (raw export)','Visibility-weighted export']):
        for label,color in colors.items():
            ax.plot(range(len(periods)),data[label],label=label.split('/')[0],color=color,lw=2.4,marker='o',ms=4)
        ax.set_title(title,loc='left',fontweight='bold',pad=15)
        ax.set_xticks(range(len(periods)),[p.replace('--','–') for p in periods],rotation=45,ha='right')
        ax.set_ylim(0,46);ax.grid(axis='y',alpha=.2);ax.legend(frameon=False,loc='upper right');ax.set_xlabel('Five-year release period')
    axes[0].set_ylabel('Share of coded archetype weight (%)')
    fig.savefig(ROOT/'results/figures/hero_explorer_overview.png',dpi=160)
    fig.savefig(ROOT/'results/figures/hero_explorer_overview.svg')
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,5.4),layout='constrained')
    values=raw.T.values
    im=ax.imshow(values,aspect='auto',cmap='YlGnBu',vmin=0,vmax=45)
    ax.set_yticks(range(len(raw.columns)),[c.split('/')[0] for c in raw.columns])
    ax.set_xticks(range(len(periods)),[p.replace('--','–') for p in periods],rotation=35,ha='right')
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(j,i,f'{values[i,j]:.1f}',ha='center',va='center',fontsize=8,color='white' if values[i,j]>25 else '#142532')
    ax.set_title('Twelve archetypes across five decades — raw export',loc='left',fontweight='bold',pad=15)
    fig.colorbar(im,ax=ax,label='Share of coded archetype weight (%)',shrink=.8)
    fig.savefig(ROOT/'results/figures/twelve_archetypes_overview.png',dpi=160)
    plt.close(fig)
    rows=[]
    for category in raw.columns:
        first=raw.loc[periods[0],category];last=raw.loc[periods[-1],category]
        rows.append({'archetype':category,'raw_1980_1984_percent':first,'raw_2020_2024_percent':last,'change_percentage_points':last-first})
    pd.DataFrame(rows).to_csv(ROOT/'results/tables/archetype_endpoints.csv',index=False)
    res=['# Findings, figures and tables','', '[Overview](../README.md) · [Methods](how-the-evaluation-was-created.md) · [Complete data](data-catalogue.md)','',
         'The study treats archetypes as operational categories for playable protagonist functions. Its central distinction is between a fictional character and the role made available to the player, including silent avatars, customizable characters, ensembles and implicit systemic roles.','',
         '## Hero and Explorer','',
         'In the archived raw-share series, Hero falls from **40.5%** in 1980–1984 to **22.2%** in 2020–2024, while Explorer rises from **21.7%** to **31.6%**. These are shares of coded archetype weight, not percentages of players, sales, or mutually exclusive game identities. Lower relative share does not establish a lower absolute number of heroic protagonists.','',
         '![Hero, Explorer and Everyman in the raw and visibility-weighted exports](../results/figures/hero_explorer_overview.png)','',
         'The weighted export is shown separately. It does **not** reproduce every raw-share pattern: in 2020–2024 its Hero share is 18.6% and Explorer share is 17.1%. Weighting changes which games contribute most. This distinction is part of the interpretation, not an interchangeable plotting choice.','',
         '## The twelve-category picture','',
         'Everyman grows from 5.4% to 10.5% in the raw export. Other archetypes follow different trajectories. The heatmap keeps all twelve categories visible rather than reducing the corpus to a Hero-versus-Explorer contest.','',
         '![Raw shares of all twelve archetypes](../results/figures/twelve_archetypes_overview.png)','',
         '| Archetype | 1980–1984 | 2020–2024 | Change (percentage points) |','|---|---:|---:|---:|']
    for r in rows:res.append(f"| {r['archetype']} | {r['raw_1980_1984_percent']:.1f}% | {r['raw_2020_2024_percent']:.1f}% | {r['change_percentage_points']:+.1f} |")
    res+=['','## Protagonist form','',
          'The recovered type-profile table distinguishes a typed subset from the full corpus. Fixed-character records emphasize Hero (20.3%) and Explorer (18.0%); silent avatars emphasize Explorer (25.8%); systemic roles emphasize Ruler (33.0%) and Creator (15.6%). These values describe the recovered type-profile export and are not a human validation score.','',
          '| Protagonist type | Records in recovered typed subset | Leading archetypes |','|---|---:|---|',
          '| Fixed character | 18,523 | Hero 20.3%; Explorer 18.0%; Everyman 13.1% |',
          '| Silent avatar | 2,232 | Explorer 25.8%; Hero 15.4%; Everyman 14.1% |',
          '| Systemic role | 1,744 | Ruler 33.0%; Creator 15.6%; Hero 14.4% |',
          '| Customizable | 335 | Explorer 23.0%; Hero 22.3%; Everyman 12.4% |','',
          '[Original type-profile table]('+link('Downloads/table_archetype_profiles_by_type.tex')+'). Related type-share and within-type-change tables, PGFPlots sources, heatmaps, and annual weighting variants are included in the [file index](recovered-file-index.md).','',
          '## Interpretation and limits','',
          '“Heroic exploration” and “exploratory heroism” express the paper\'s interpretation of changing ranked archetypal configurations. The categories are a predefined codebook. Technological, formal and cultural causes are not isolated by this descriptive analysis. Catalogue coverage, metadata quality and computational pre-coding influence the observed distributions.','',
          'Participant comparison evaluates a selected subset and is not full-corpus validation. Broader label overlap does not establish coding validity. The literature examples in [comparison](../comparison/README.md) are explicitly separated from participant responses and computational labels.','',
          '## Reproduce the overview','',
          'Run `python tools/build_overview.py` with pandas and matplotlib installed. The overview figures, including the [additional archetype comparisons](../README.md#investigator-and-magician-knowledge-and-transformation), are **new renderings of archived aggregate CSV values**, restricted to 1980–2024; they do not rerun model inference or claim an independently reconstructed raw-to-figure pipeline. The original aggregate exports and plotting variants remain unchanged. To regenerate only the three additional comparisons, run `python tools/plot_archetype_stories.py`.','',
          '- [Raw source CSV]('+link('Downloads/archetype_raw_share_by_half_decade_v2.csv')+')',
          '- [Visibility-weighted source CSV]('+link('Downloads/archetype_review_weighted_share_by_half_decade_v2.csv')+')',
          '- [Endpoint table](../results/tables/archetype_endpoints.csv)',
          '- [Corrected corpus counts](corpus-counts.md)',
          '- [Full paper status](../paper/README.md)']
    write('docs/results.md','\n'.join(res)+'\n')

    # Index generated artifacts, allowing exact checks without running plotting.
    artifacts=[]
    for p in sorted((ROOT/'results').rglob('*')):
        if p.is_file():artifacts.append({'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    write('provenance/overview-artifacts.json',json.dumps(artifacts,indent=2)+'\n')
    print('Built catalogue, timeline, counts, 9 figure files and result tables.',flush=True)

if __name__=='__main__':main()
