#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_archetype_year_matrices.py

Vstup:
    CSV se sloupci:
    - jméno hry
    - rok vydání
    - jméno protagonisty
    - archetyp 1
    - archetyp 2
    - archetyp 3
    - věrohodnost

Výstup:
    Čtyři matice rok × archetyp:
    1) prostý součet primárního, sekundárního a terciálního archetypu
    2) prostý součet násobený věrohodností
    3) pozičně vážený součet: primární=1.0, sekundární=0.6, terciální=0.3
    4) pozičně vážený součet násobený věrohodností

    Plus jeden srovnávací heatmap obrázek se čtyřmi panely vedle sebe.

Použití:
    python make_archetype_year_matrices.py \
        --input igdb_archetype_annotations_simple_characters_only_v001.csv \
        --output-dir archetype_year_outputs

Poznámky:
    - Ve výchozím režimu se ignoruje archetyp "Uncertain", protože není jedním z 12 archetypů.
    - Věrohodnost se očekává na škále 0–1. Pokud skript najde škálu 0–3 nebo 0–100,
      pokusí se ji automaticky převést na 0–1.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


GAME_COL = "jméno hry"
YEAR_COL = "rok vydání"
PROTAGONIST_COL = "jméno protagonisty"
ARCHETYPE_COLS = ["archetyp 1", "archetyp 2", "archetyp 3"]
CONFIDENCE_COL = "věrohodnost"

# Pevné pořadí 12 archetypů používané v anotacích.
ARCHETYPE_ORDER = [
    "Innocent",
    "Everyman/Orphan",
    "Hero/Warrior",
    "Caregiver/Guardian",
    "Explorer/Seeker",
    "Rebel/Outlaw",
    "Lover",
    "Creator/Artist",
    "Jester/Trickster",
    "Sage/Investigator",
    "Magician/Transformer",
    "Ruler/Leader",
]

POSITION_WEIGHTS = {
    "archetyp 1": 1.0,
    "archetyp 2": 0.6,
    "archetyp 3": 0.3,
}


def read_input(path: Path) -> pd.DataFrame:
    """Načte CSV a zkontroluje povinné sloupce."""
    df = pd.read_csv(path)
    required = [GAME_COL, YEAR_COL, PROTAGONIST_COL, *ARCHETYPE_COLS, CONFIDENCE_COL]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            "Vstupní CSV nemá očekávané sloupce: "
            + ", ".join(missing)
            + f"\nDostupné sloupce: {list(df.columns)}"
        )

    df = df.copy()
    df[YEAR_COL] = pd.to_numeric(df[YEAR_COL], errors="coerce").astype("Int64")
    df[CONFIDENCE_COL] = pd.to_numeric(df[CONFIDENCE_COL], errors="coerce")

    # Automatická normalizace věrohodnosti na 0–1, pokud by vstup byl 0–3 nebo 0–100.
    max_conf = df[CONFIDENCE_COL].max(skipna=True)
    if pd.notna(max_conf) and max_conf > 1.0:
        if max_conf <= 3.0:
            df[CONFIDENCE_COL] = df[CONFIDENCE_COL] / 3.0
        elif max_conf <= 100.0:
            df[CONFIDENCE_COL] = df[CONFIDENCE_COL] / 100.0

    df[CONFIDENCE_COL] = df[CONFIDENCE_COL].fillna(0.0).clip(lower=0.0, upper=1.0)

    for col in ARCHETYPE_COLS:
        df[col] = df[col].astype("string").str.strip()

    # Roky mimo numerický rozsah ignorujeme.
    df = df[df[YEAR_COL].notna()].copy()
    df[YEAR_COL] = df[YEAR_COL].astype(int)

    return df


def make_long_table(df: pd.DataFrame, include_uncertain: bool = False) -> pd.DataFrame:
    """Převede široké archetypové sloupce na dlouhý formát: jeden řádek = jedna archetypová položka."""
    parts = []
    for col in ARCHETYPE_COLS:
        part = df[[YEAR_COL, CONFIDENCE_COL, col]].rename(columns={col: "archetype"}).copy()
        part["source_column"] = col
        part["position_weight"] = POSITION_WEIGHTS[col]
        parts.append(part)

    long_df = pd.concat(parts, ignore_index=True)
    long_df["archetype"] = long_df["archetype"].astype("string").str.strip()

    # Zahodíme prázdné hodnoty a standardní nejistý pseudo-archetyp.
    long_df = long_df[long_df["archetype"].notna()]
    long_df = long_df[long_df["archetype"] != ""]
    if not include_uncertain:
        long_df = long_df[long_df["archetype"] != "Uncertain"]

    return long_df


def pivot_matrix(long_df: pd.DataFrame, value_col: str, years: Iterable[int], archetypes: List[str]) -> pd.DataFrame:
    """Vytvoří matici rok × archetyp a doplní chybějící roky/sloupce nulami."""
    matrix = (
        long_df.pivot_table(
            index=YEAR_COL,
            columns="archetype",
            values=value_col,
            aggfunc="sum",
            fill_value=0.0,
        )
        .reindex(index=list(years), columns=archetypes, fill_value=0.0)
        .sort_index()
    )

    # Pro čistý prostý součet ponecháme integer, pro vážené varianty float.
    if np.allclose(matrix.to_numpy(), np.rint(matrix.to_numpy())):
        matrix = matrix.round(0).astype(int)

    return matrix


def build_matrices(df: pd.DataFrame, include_uncertain: bool = False) -> Dict[str, pd.DataFrame]:
    """Vypočítá čtyři požadované matice."""
    long_df = make_long_table(df, include_uncertain=include_uncertain)

    if include_uncertain:
        extra = sorted(set(long_df["archetype"].dropna()) - set(ARCHETYPE_ORDER))
        archetypes = ARCHETYPE_ORDER + extra
    else:
        archetypes = ARCHETYPE_ORDER

    min_year = int(df[YEAR_COL].min())
    max_year = int(df[YEAR_COL].max())
    years = range(min_year, max_year + 1)

    long_df = long_df.copy()
    long_df["simple_count"] = 1.0
    long_df["confidence_weighted"] = long_df[CONFIDENCE_COL]
    long_df["position_weighted"] = long_df["position_weight"]
    long_df["position_confidence_weighted"] = long_df["position_weight"] * long_df[CONFIDENCE_COL]

    matrices = {
        "01_simple_count": pivot_matrix(long_df, "simple_count", years, archetypes),
        "02_confidence_weighted": pivot_matrix(long_df, "confidence_weighted", years, archetypes),
        "03_position_weighted": pivot_matrix(long_df, "position_weighted", years, archetypes),
        "04_position_confidence_weighted": pivot_matrix(long_df, "position_confidence_weighted", years, archetypes),
    }
    return matrices


def save_matrices(matrices: Dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, matrix in matrices.items():
        matrix.to_csv(output_dir / f"{name}.csv", encoding="utf-8-sig", index_label=YEAR_COL)


def plot_heatmaps(matrices: Dict[str, pd.DataFrame], output_dir: Path, shared_scale: bool = False) -> Path:
    """Vykreslí čtyři matice vedle sebe jako heatmapy."""
    output_dir.mkdir(parents=True, exist_ok=True)

    titles = {
        "01_simple_count": "1) prostý součet",
        "02_confidence_weighted": "2) součet × věrohodnost",
        "03_position_weighted": "3) poziční váhy 1 / 0.6 / 0.3",
        "04_position_confidence_weighted": "4) poziční váhy × věrohodnost",
    }

    keys = list(matrices.keys())

    if shared_scale:
        vmax = max(float(np.nanmax(matrices[k].to_numpy(dtype=float))) for k in keys)
        vmin = 0.0
    else:
        vmin = vmax = None

    fig, axes = plt.subplots(1, 4, figsize=(28, 10), constrained_layout=True)

    for ax, key in zip(axes, keys):
        matrix = matrices[key]
        data = matrix.to_numpy(dtype=float)

        im = ax.imshow(data, aspect="auto", vmin=vmin, vmax=vmax)

        ax.set_title(titles.get(key, key), fontsize=12)
        ax.set_xlabel("archetyp")
        ax.set_ylabel("rok vydání")

        ax.set_xticks(np.arange(len(matrix.columns)))
        ax.set_xticklabels(matrix.columns, rotation=60, ha="right", fontsize=8)

        years = list(matrix.index)
        # Aby osa let nebyla nečitelná: popisek cca každých 5 let.
        step = max(1, round(len(years) / 12))
        yticks = np.arange(0, len(years), step)
        ax.set_yticks(yticks)
        ax.set_yticklabels([years[i] for i in yticks], fontsize=8)

        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    suffix = "_shared_scale" if shared_scale else ""
    out_path = output_dir / f"archetype_year_heatmaps_1x4{suffix}.png"
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Vytvoří rok × archetyp matice a heatmapy.")
    parser.add_argument("--input", required=True, type=Path, help="Vstupní CSV se zjednodušenými anotacemi.")
    parser.add_argument("--output-dir", default=Path("archetype_year_outputs"), type=Path, help="Složka pro výstupy.")
    parser.add_argument(
        "--include-uncertain",
        action="store_true",
        help='Zahrnout i pseudo-archetyp "Uncertain". Ve výchozím režimu se ignoruje.',
    )
    parser.add_argument(
        "--shared-scale",
        action="store_true",
        help="Použít stejnou barevnou škálu pro všechny čtyři heatmapy.",
    )
    args = parser.parse_args()

    df = read_input(args.input)
    matrices = build_matrices(df, include_uncertain=args.include_uncertain)
    save_matrices(matrices, args.output_dir)
    plot_path = plot_heatmaps(matrices, args.output_dir, shared_scale=args.shared_scale)

    print(f"Načteno řádků: {len(df):,}")
    print(f"Výstupní složka: {args.output_dir.resolve()}")
    print(f"Heatmapa: {plot_path.resolve()}")
    for name, matrix in matrices.items():
        print(f"{name}: {matrix.shape[0]} roků × {matrix.shape[1]} archetypů")


if __name__ == "__main__":
    main()
