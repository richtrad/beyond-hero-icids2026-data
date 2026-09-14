#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_archetype_year_matrices_normalized_v002.py

Vytvoří matice rok × archetyp ze zjednodušeného CSV:
    jméno hry, rok vydání, jméno protagonisty, archetyp 1, archetyp 2, archetyp 3, věrohodnost

Počítají se čtyři varianty:
    1) prostý součet primárního, sekundárního a terciálního archetypu
    2) prostý součet násobený věrohodností
    3) pozičně vážený součet: primární=1.0, sekundární=0.6, terciální=0.3
    4) pozičně vážený součet násobený věrohodností

Novinka oproti v001:
    - ukládá i NORMALIZOVANÉ matice; výchozí normalizace je row-share, tj. každý rok
      se vydělí součtem všech archetypových hodnot v daném roce. Výsledkem je podíl
      archetypu na archetypové skladbě daného roku. V CSV *_share.csv jsou hodnoty 0–1,
      v CSV *_share_pct.csv jsou hodnoty 0–100.
    - vykresluje normalizované heatmapy vedle sebe.
    - vykresluje klasické čárové grafy hodnot pro všechny archetypy.
    - ukládá diagnostiku počtu her/protagonistických řádků podle roku.

Použití:
    python make_archetype_year_matrices_normalized_v002.py \
        --input igdb_archetype_annotations_simple_characters_only_v001.csv \
        --output-dir archetype_year_outputs_normalized_v002

Poznámky:
    - Ve výchozím režimu se ignoruje pseudo-archetyp "Uncertain".
    - Věrohodnost se očekává na škále 0–1. Pokud skript najde 0–3 nebo 0–100,
      automaticky ji převede na 0–1.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


GAME_COL = "jméno hry"
YEAR_COL = "rok vydání"
PROTAGONIST_COL = "jméno protagonisty"
ARCHETYPE_COLS = ["archetyp 1", "archetyp 2", "archetyp 3"]
CONFIDENCE_COL = "věrohodnost"

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

MATRIX_TITLES = {
    "01_simple_count": "1) prostý součet",
    "02_confidence_weighted": "2) součet × věrohodnost",
    "03_position_weighted": "3) poziční váhy 1 / 0.6 / 0.3",
    "04_position_confidence_weighted": "4) poziční váhy × věrohodnost",
}


def read_input(path: Path) -> pd.DataFrame:
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

    max_conf = df[CONFIDENCE_COL].max(skipna=True)
    if pd.notna(max_conf) and max_conf > 1.0:
        if max_conf <= 3.0:
            df[CONFIDENCE_COL] = df[CONFIDENCE_COL] / 3.0
        elif max_conf <= 100.0:
            df[CONFIDENCE_COL] = df[CONFIDENCE_COL] / 100.0

    df[CONFIDENCE_COL] = df[CONFIDENCE_COL].fillna(0.0).clip(lower=0.0, upper=1.0)

    for col in [GAME_COL, PROTAGONIST_COL, *ARCHETYPE_COLS]:
        df[col] = df[col].astype("string").str.strip()

    df = df[df[YEAR_COL].notna()].copy()
    df[YEAR_COL] = df[YEAR_COL].astype(int)
    return df


def year_sample_sizes(df: pd.DataFrame) -> pd.DataFrame:
    out = (
        df.groupby(YEAR_COL)
        .agg(
            protagonist_rows=(PROTAGONIST_COL, "size"),
            unique_games=(GAME_COL, "nunique"),
            mean_confidence=(CONFIDENCE_COL, "mean"),
        )
        .reset_index()
        .sort_values(YEAR_COL)
    )
    return out


def make_long_table(df: pd.DataFrame, include_uncertain: bool = False) -> pd.DataFrame:
    parts = []
    for col in ARCHETYPE_COLS:
        part = df[[YEAR_COL, GAME_COL, PROTAGONIST_COL, CONFIDENCE_COL, col]].rename(columns={col: "archetype"}).copy()
        part["source_column"] = col
        part["position_weight"] = POSITION_WEIGHTS[col]
        parts.append(part)

    long_df = pd.concat(parts, ignore_index=True)
    long_df["archetype"] = long_df["archetype"].astype("string").str.strip()
    long_df = long_df[long_df["archetype"].notna()]
    long_df = long_df[long_df["archetype"] != ""]

    if not include_uncertain:
        long_df = long_df[long_df["archetype"] != "Uncertain"]

    return long_df


def pivot_matrix(long_df: pd.DataFrame, value_col: str, years: Iterable[int], archetypes: List[str]) -> pd.DataFrame:
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
    return matrix


def build_raw_matrices(df: pd.DataFrame, include_uncertain: bool = False) -> Dict[str, pd.DataFrame]:
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


def normalize_row_share(matrix: pd.DataFrame) -> pd.DataFrame:
    """Normalizace uvnitř roku: řádek se vydělí součtem daného roku. Řádek pak sumuje na 1."""
    row_sums = matrix.sum(axis=1).replace(0, np.nan)
    return matrix.div(row_sums, axis=0).fillna(0.0)


def normalize_matrices(raw_matrices: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    return {name: normalize_row_share(matrix) for name, matrix in raw_matrices.items()}


def save_matrices(raw_matrices: Dict[str, pd.DataFrame], normalized: Dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, matrix in raw_matrices.items():
        matrix.to_csv(output_dir / f"raw_{name}.csv", encoding="utf-8-sig", index_label=YEAR_COL)

    for name, matrix in normalized.items():
        matrix.to_csv(output_dir / f"normalized_{name}_share.csv", encoding="utf-8-sig", index_label=YEAR_COL)
        (matrix * 100.0).round(4).to_csv(
            output_dir / f"normalized_{name}_share_pct.csv",
            encoding="utf-8-sig",
            index_label=YEAR_COL,
        )


def plot_heatmaps(normalized: Dict[str, pd.DataFrame], output_dir: Path, shared_scale: bool = True) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    keys = list(normalized.keys())

    pct_matrices = {name: matrix * 100.0 for name, matrix in normalized.items()}
    if shared_scale:
        vmax = max(float(np.nanmax(pct_matrices[k].to_numpy(dtype=float))) for k in keys)
        vmin = 0.0
    else:
        vmin = vmax = None

    fig, axes = plt.subplots(1, 4, figsize=(30, 10), constrained_layout=True)

    for ax, key in zip(axes, keys):
        matrix = pct_matrices[key]
        data = matrix.to_numpy(dtype=float)
        im = ax.imshow(data, aspect="auto", vmin=vmin, vmax=vmax)

        ax.set_title(MATRIX_TITLES.get(key, key), fontsize=12)
        ax.set_xlabel("archetyp")
        ax.set_ylabel("rok vydání")
        ax.set_xticks(np.arange(len(matrix.columns)))
        ax.set_xticklabels(matrix.columns, rotation=60, ha="right", fontsize=8)

        years = list(matrix.index)
        step = max(1, round(len(years) / 12))
        yticks = np.arange(0, len(years), step)
        ax.set_yticks(yticks)
        ax.set_yticklabels([years[i] for i in yticks], fontsize=8)

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("podíl v daném roce (%)", fontsize=8)

    suffix = "_shared_scale" if shared_scale else ""
    out_path = output_dir / f"archetype_year_heatmaps_normalized_1x4{suffix}.png"
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_linecharts(normalized: Dict[str, pd.DataFrame], output_dir: Path, rolling_window: int = 1) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    keys = list(normalized.keys())

    # Záměrně nepoužíváme constrained_layout: společná legenda pod grafy by jinak
    # měla tendenci zasahovat do spodních panelů.
    fig, axes = plt.subplots(2, 2, figsize=(26, 16), sharex=True, sharey=True)
    axes_flat = axes.ravel()
    fig.subplots_adjust(left=0.06, right=0.99, top=0.94, bottom=0.18, hspace=0.28, wspace=0.10)

    for ax, key in zip(axes_flat, keys):
        matrix = normalized[key] * 100.0
        if rolling_window and rolling_window > 1:
            matrix = matrix.rolling(window=rolling_window, min_periods=1, center=True).mean()

        for archetype in matrix.columns:
            ax.plot(matrix.index, matrix[archetype], linewidth=1.25, label=archetype)

        ax.set_title(MATRIX_TITLES.get(key, key), fontsize=13)
        ax.set_xlabel("rok vydání")
        ax.set_ylabel("podíl v daném roce (%)")
        ax.grid(True, linewidth=0.4, alpha=0.35)

    # Jedna společná legenda pro všechny panely, aby se neopakovala čtyřikrát.
    handles, labels = axes_flat[0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.035),
        ncol=4,
        fontsize=10,
        frameon=False,
    )

    suffix = f"_{rolling_window}yr_rolling" if rolling_window and rolling_window > 1 else ""
    out_path = output_dir / f"archetype_year_linecharts_normalized_2x2{suffix}.png"
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out_path


def plot_sample_size(sample_sizes: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    ax.plot(sample_sizes[YEAR_COL], sample_sizes["protagonist_rows"], linewidth=1.8, label="řádky protagonistů")
    ax.plot(sample_sizes[YEAR_COL], sample_sizes["unique_games"], linewidth=1.8, label="unikátní hry")
    ax.set_title("Velikost vzorku podle roku")
    ax.set_xlabel("rok vydání")
    ax.set_ylabel("počet")
    ax.grid(True, linewidth=0.4, alpha=0.35)
    ax.legend(frameon=False)
    out_path = output_dir / "year_sample_sizes_linechart.png"
    fig.savefig(out_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Vytvoří raw i normalizované rok × archetyp matice a grafy.")
    parser.add_argument("--input", required=True, type=Path, help="Vstupní CSV se zjednodušenými anotacemi.")
    parser.add_argument("--output-dir", default=Path("archetype_year_outputs_normalized_v002"), type=Path, help="Složka pro výstupy.")
    parser.add_argument(
        "--include-uncertain",
        action="store_true",
        help='Zahrnout i pseudo-archetyp "Uncertain". Ve výchozím režimu se ignoruje.',
    )
    parser.add_argument(
        "--rolling-window",
        type=int,
        default=5,
        help="Šířka centrovaného klouzavého průměru pro dodatečný čárový graf. 1 = negenerovat vyhlazenou variantu.",
    )
    args = parser.parse_args()

    df = read_input(args.input)
    raw_matrices = build_raw_matrices(df, include_uncertain=args.include_uncertain)
    normalized = normalize_matrices(raw_matrices)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_matrices(raw_matrices, normalized, args.output_dir)

    sample_sizes = year_sample_sizes(df)
    sample_sizes.to_csv(args.output_dir / "00_year_sample_sizes.csv", encoding="utf-8-sig", index=False)

    heatmap_path = plot_heatmaps(normalized, args.output_dir, shared_scale=True)
    linechart_path = plot_linecharts(normalized, args.output_dir, rolling_window=1)
    sample_path = plot_sample_size(sample_sizes, args.output_dir)

    rolling_path = None
    if args.rolling_window and args.rolling_window > 1:
        rolling_path = plot_linecharts(normalized, args.output_dir, rolling_window=args.rolling_window)

    print(f"Načteno řádků: {len(df):,}")
    print(f"Roky: {df[YEAR_COL].min()}–{df[YEAR_COL].max()}")
    print(f"Výstupní složka: {args.output_dir.resolve()}")
    print(f"Normalizace: row-share, tj. každý rok sumuje na 100 %")
    print(f"Heatmapa: {heatmap_path.resolve()}")
    print(f"Čárový graf: {linechart_path.resolve()}")
    if rolling_path:
        print(f"Vyhlazený čárový graf: {rolling_path.resolve()}")
    print(f"Velikost vzorku: {sample_path.resolve()}")
    for name, matrix in normalized.items():
        row_sums = matrix.sum(axis=1)
        nonzero = row_sums[row_sums > 0]
        print(
            f"{name}: {matrix.shape[0]} roků × {matrix.shape[1]} archetypů; "
            f"normalizované řádky min/max sum: {nonzero.min():.4f}/{nonzero.max():.4f}"
        )


if __name__ == "__main__":
    main()
