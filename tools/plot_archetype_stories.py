"""Render additional archetype comparisons from the preserved overview tables.

Run standalone, or as part of build_overview.py. No inference or network calls.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STORIES = [
    ('investigator_magician', 'Knowledge and transformation',
     {'Sage/Investigator': '#246b99', 'Magician/Transformer': '#9454a0'}, 18),
    ('outlaw_ruler', 'Transgression and control',
     {'Rebel/Outlaw': '#ba4a38', 'Ruler/Leader': '#386a88'}, 15),
    ('creator_caregiver', 'Creation and care',
     {'Creator/Artist': '#a66b13', 'Caregiver/Guardian': '#32816b'}, 8),
]


def build_stories():
    periods = [f'{year}--{year + 4}' for year in range(1980, 2025, 5)]
    raw, weighted = [
        pd.read_csv(ROOT / 'results/tables' / filename, index_col='period').loc[periods]
        for filename in ('raw_archetype_shares_1980_2024.csv',
                         'visibility_weighted_archetype_shares_1980_2024.csv')
    ]
    paths = []
    with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 11,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'svg.hashsalt': 'beyond-hero-stories'}):
        for slug, title, colors, upper in STORIES:
            fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharey=True,
                                     layout='constrained')
            fig.suptitle(title, fontsize=17, fontweight='bold')
            for ax, data, panel in zip(axes, [raw, weighted],
                                      ['Corpus composition (raw export)',
                                       'Visibility-weighted export']):
                for label, color in colors.items():
                    ax.plot(range(len(periods)), data[label], label=label,
                            color=color, lw=2.4, marker='o', ms=4)
                ax.set_title(panel, loc='left', fontsize=12, pad=12)
                ax.set_xticks(range(len(periods)),
                              [period.replace('--', '–') for period in periods],
                              rotation=45, ha='right')
                ax.set_ylim(0, upper)
                ax.grid(axis='y', alpha=.2)
                ax.legend(frameon=False, loc='upper right', fontsize=10)
                ax.set_xlabel('Five-year release period')
            axes[0].set_ylabel('Share of coded archetype weight (%)')
            for extension in ('png', 'svg'):
                path = ROOT / 'results/figures' / f'{slug}_overview.{extension}'
                path.parent.mkdir(parents=True, exist_ok=True)
                options = {'metadata': {'Date': None}} if extension == 'svg' else {}
                fig.savefig(path, dpi=160, **options)
                paths.append(path)
            plt.close(fig)
    return paths


def main():
    paths = build_stories()
    manifest_path = ROOT / 'provenance/overview-artifacts.json'
    records = json.loads(manifest_path.read_text(encoding='utf-8'))
    indexed = {record['path']: record for record in records}
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        indexed[relative] = {'path': relative,
                             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps([indexed[key] for key in sorted(indexed)],
                                        indent=2) + '\n', encoding='utf-8')
    print(f'Built {len(paths)} additional figure files; updated their checksums.')


if __name__ == '__main__':
    main()
