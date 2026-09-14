#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archetype diachronic analysis with alternative visibility / player-reach weights.

Reads a simple protagonist-archetype CSV and, optionally, an IGDB/Steam master
CSV with Steam review counts. Produces per-year and per-decade archetype shares
under several weighting schemes:

  equal               each game/protagonist row has weight 1
  raw_reviews         raw Steam review count (very aggressive)
  raw_cap_p99         raw review count capped at 99th percentile
  sqrt_reviews        sqrt(review count), a middle-strength weighting
  log_reviews         log1p(review count), damped visibility weighting
  log_cap_p99         log1p(review count) capped at 99th percentile
  blend_equal_log     50% equal weight + 50% normalized log weight
  tiered_reviews      coarse log10-based tiers

Default archetype scoring uses position weights and confidence:
  primary = 1.0, secondary = 0.6, tertiary = 0.3, multiplied by confidence.

Outputs:
  - CSV files with year/archetype/scheme shares
  - decade summaries
  - coverage diagnostics
  - PNG line charts and heatmaps

Example:
  python archetype_visibility_weight_scenarios.py \
    --annotations "igdb_archetype_annotations_simple_characters_only_v001 (1).csv" \
    --metadata "igdb_master_broad_with_steam_llm_overlap_v001.csv" \
    --outdir archetype_visibility_weight_outputs_v001
"""
from __future__ import annotations

import argparse
import math
import os
import re
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


DEFAULT_ARCHETYPE_ORDER = [
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

ARCHETYPE_ALIASES = {
    "everyman": "Everyman/Orphan",
    "everyman/orphan": "Everyman/Orphan",
    "orphan": "Everyman/Orphan",
    "hero": "Hero/Warrior",
    "hero/warrior": "Hero/Warrior",
    "warrior": "Hero/Warrior",
    "caregiver": "Caregiver/Guardian",
    "caregiver/guardian": "Caregiver/Guardian",
    "guardian": "Caregiver/Guardian",
    "explorer": "Explorer/Seeker",
    "explorer/seeker": "Explorer/Seeker",
    "seeker": "Explorer/Seeker",
    "rebel": "Rebel/Outlaw",
    "rebel/outlaw": "Rebel/Outlaw",
    "outlaw": "Rebel/Outlaw",
    "creator": "Creator/Artist",
    "creator/artist": "Creator/Artist",
    "artist": "Creator/Artist",
    "jester": "Jester/Trickster",
    "jester/trickster": "Jester/Trickster",
    "trickster": "Jester/Trickster",
    "sage": "Sage/Investigator",
    "sage/investigator": "Sage/Investigator",
    "investigator": "Sage/Investigator",
    "magician": "Magician/Transformer",
    "magician/transformer": "Magician/Transformer",
    "transformer": "Magician/Transformer",
    "ruler": "Ruler/Leader",
    "ruler/leader": "Ruler/Leader",
    "leader": "Ruler/Leader",
    "innocent": "Innocent",
    "lover": "Lover",
}


def norm_title(x: object) -> str:
    """Conservative title normalization for matching annotation rows to metadata."""
    if pd.isna(x):
        return ""
    s = str(x).lower().strip()
    s = re.sub(r"&", " and ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\b(the|a|an)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def canon_arch(x: object) -> Optional[str]:
    if pd.isna(x):
        return None
    s = str(x).strip()
    if not s or s.lower() in {"nan", "none", "null", "-"}:
        return None
    key = s.lower().strip()
    return ARCHETYPE_ALIASES.get(key, s)


def confidence_to_0_1(s: pd.Series) -> pd.Series:
    v = pd.to_numeric(s, errors="coerce").fillna(1.0)
    mx = float(v.max()) if len(v) else 1.0
    if mx <= 1.0:
        return v.clip(0, 1)
    if mx <= 3.0:
        return (v / 3.0).clip(0, 1)
    if mx <= 5.0:
        return (v / 5.0).clip(0, 1)
    return (v / 100.0).clip(0, 1)


def parse_steamspy_owners_midpoint(x: object) -> float:
    """Parse SteamSpy interval like '50,000 .. 100,000' to midpoint."""
    if pd.isna(x):
        return np.nan
    s = str(x)
    nums = re.findall(r"[0-9][0-9,]*", s)
    if not nums:
        return np.nan
    vals = [float(n.replace(",", "")) for n in nums]
    if len(vals) == 1:
        return vals[0]
    return float(sum(vals[:2]) / 2.0)


def read_annotations(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    rename_map = {
        "jméno hry": "game",
        "jmeno hry": "game",
        "rok vydání": "year",
        "rok vydani": "year",
        "jméno protagonisty": "protagonist",
        "jmeno protagonisty": "protagonist",
        "archetyp 1": "arch1",
        "archetyp 2": "arch2",
        "archetyp 3": "arch3",
        "věrohodnost": "confidence",
        "verohodnost": "confidence",
    }
    df = df.rename(columns={c: rename_map.get(c, c) for c in df.columns})
    required = ["game", "year", "arch1", "arch2", "arch3"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Annotation CSV is missing required columns: {missing}")
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["game", "year"]).copy()
    df["year"] = df["year"].astype(int)
    for c in ["arch1", "arch2", "arch3"]:
        df[c] = df[c].map(canon_arch)
    if "confidence" not in df.columns:
        df["confidence"] = 1.0
    df["confidence_0_1"] = confidence_to_0_1(df["confidence"])
    df["title_norm"] = df["game"].map(norm_title)
    df["row_id"] = np.arange(len(df))
    return df


def read_metadata(path: Path) -> pd.DataFrame:
    # Read only columns that are useful; tolerate missing columns.
    header = pd.read_csv(path, nrows=0).columns.tolist()
    wanted = [
        "name", "original_release_year", "original_release_year_num", "game",
        "total_ratings_pos_neg", "rating_count", "total_rating_count", "visibility_count_score",
        "steamspy_owners", "appid", "steam_appid_from_external", "external_steam_matched",
        "already_has_any_steam_llm_annotation", "match_method",
    ]
    usecols = [c for c in wanted if c in header]
    md = pd.read_csv(path, usecols=usecols, low_memory=False)
    # Choose title.
    if "name" in md.columns:
        md["meta_title"] = md["name"]
    elif "game" in md.columns:
        md["meta_title"] = md["game"]
    else:
        raise ValueError("Metadata CSV needs a 'name' or 'game' column.")
    # Choose year.
    if "original_release_year_num" in md.columns:
        md["meta_year"] = pd.to_numeric(md["original_release_year_num"], errors="coerce")
    elif "original_release_year" in md.columns:
        md["meta_year"] = pd.to_numeric(md["original_release_year"], errors="coerce")
    else:
        md["meta_year"] = np.nan
    md["meta_year"] = md["meta_year"].astype("Int64")
    md["title_norm"] = md["meta_title"].map(norm_title)

    # Numeric visibility columns.
    for c in ["total_ratings_pos_neg", "rating_count", "total_rating_count", "visibility_count_score"]:
        if c in md.columns:
            md[c] = pd.to_numeric(md[c], errors="coerce")
    if "steamspy_owners" in md.columns:
        md["steamspy_owners_mid"] = md["steamspy_owners"].map(parse_steamspy_owners_midpoint)
    else:
        md["steamspy_owners_mid"] = np.nan

    # Aggregate by title+year and by title-only using max review count / visibility.
    vis_cols = [c for c in ["total_ratings_pos_neg", "rating_count", "total_rating_count", "visibility_count_score", "steamspy_owners_mid"] if c in md.columns]
    md["metadata_has_row"] = 1
    agg_dict = {c: "max" for c in vis_cols}
    agg_dict.update({"metadata_has_row": "max"})
    if "appid" in md.columns:
        agg_dict["appid"] = "first"
    if "steam_appid_from_external" in md.columns:
        agg_dict["steam_appid_from_external"] = "first"

    by_title_year = (
        md.dropna(subset=["title_norm", "meta_year"])
        .groupby(["title_norm", "meta_year"], as_index=False)
        .agg(agg_dict)
        .rename(columns={"meta_year": "year"})
    )
    by_title = (
        md.dropna(subset=["title_norm"])
        .groupby(["title_norm"], as_index=False)
        .agg(agg_dict)
    )
    return by_title_year, by_title


def attach_visibility(ann: pd.DataFrame, metadata_path: Optional[Path]) -> pd.DataFrame:
    df = ann.copy()
    if metadata_path is None:
        df["visibility_source"] = "none"
        df["matched_visibility"] = False
        df["reviews"] = np.nan
        return df

    by_ty, by_t = read_metadata(metadata_path)
    df = df.merge(by_ty, on=["title_norm", "year"], how="left", suffixes=("", "_meta_year"))
    exact_has = df.get("metadata_has_row", pd.Series(np.nan, index=df.index)).notna()

    # Fill unmatched exact title+year using title-only aggregation.
    unmatched = ~exact_has
    if unmatched.any():
        fill = df.loc[unmatched, ["row_id", "title_norm"]].merge(by_t, on="title_norm", how="left", suffixes=("", "_title"))
        fill = fill.set_index("row_id")
        for c in fill.columns:
            if c == "title_norm":
                continue
            if c not in df.columns:
                df[c] = np.nan
            idx = df["row_id"].isin(fill.index)
            df.loc[idx, c] = df.loc[idx, "row_id"].map(fill[c])

    df["matched_visibility"] = df.get("metadata_has_row", pd.Series(np.nan, index=df.index)).notna()
    df["visibility_match_method"] = np.where(exact_has, "title_year", np.where(df["matched_visibility"], "title_only", "none"))

    # Choose primary review count for player-reach weighting.
    if "total_ratings_pos_neg" in df.columns:
        df["reviews"] = pd.to_numeric(df["total_ratings_pos_neg"], errors="coerce")
    else:
        df["reviews"] = np.nan
    return df


def make_visibility_weights(df: pd.DataFrame, reviews_col: str = "reviews") -> pd.DataFrame:
    out = df.copy()
    reviews = pd.to_numeric(out[reviews_col], errors="coerce")
    # Valid review count = positive and nonmissing.
    valid = reviews.notna() & (reviews > 0)
    safe = reviews.where(valid, 1.0).clip(lower=1.0)

    p99_raw = np.nanpercentile(safe[valid], 99) if valid.any() else 1.0
    logw = np.log1p(reviews.where(valid, 0.0))
    log_safe = logw.where(valid, np.log1p(1.0))
    p99_log = np.nanpercentile(log_safe[valid], 99) if valid.any() else np.log1p(1.0)
    mean_log = float(np.nanmean(log_safe[valid])) if valid.any() else 1.0
    if mean_log <= 0 or not np.isfinite(mean_log):
        mean_log = 1.0

    out["weight_equal"] = 1.0
    out["weight_raw_reviews"] = safe
    out["weight_raw_cap_p99"] = safe.clip(upper=p99_raw)
    out["weight_sqrt_reviews"] = np.sqrt(safe)
    out["weight_log_reviews"] = log_safe
    out["weight_log_cap_p99"] = log_safe.clip(upper=p99_log)
    out["weight_blend_equal_log"] = 0.5 + 0.5 * (log_safe / mean_log)
    # Coarse tiers: 1 review -> 1, 10 -> 2, 100 -> 3, 1k -> 4, 10k -> 5, 100k+ -> 6.
    out["weight_tiered_reviews"] = (1.0 + np.floor(np.log10(safe))).clip(lower=1, upper=6)
    out["visibility_available"] = valid
    return out


def explode_contributions(df: pd.DataFrame, scheme_col: str, matched_only: bool) -> pd.DataFrame:
    if matched_only:
        base = df[df["visibility_available"]].copy()
    else:
        base = df.copy()
    rows = []
    pos_weights = [("arch1", 1.0, "primary"), ("arch2", 0.6, "secondary"), ("arch3", 0.3, "tertiary")]
    for col, pw, pos in pos_weights:
        tmp = base[["row_id", "game", "year", col, "confidence_0_1", scheme_col]].copy()
        tmp = tmp.rename(columns={col: "archetype", scheme_col: "visibility_weight"})
        tmp = tmp.dropna(subset=["archetype"])
        tmp["position"] = pos
        tmp["position_weight"] = pw
        tmp["contribution"] = tmp["position_weight"] * tmp["confidence_0_1"] * tmp["visibility_weight"]
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def compute_year_shares(df: pd.DataFrame, scheme_col: str, scheme_name: str, matched_only: bool) -> pd.DataFrame:
    contrib = explode_contributions(df, scheme_col, matched_only=matched_only)
    if contrib.empty:
        return pd.DataFrame()
    g = contrib.groupby(["year", "archetype"], as_index=False)["contribution"].sum()
    totals = g.groupby("year", as_index=False)["contribution"].sum().rename(columns={"contribution": "year_total_contribution"})
    out = g.merge(totals, on="year", how="left")
    out["share"] = out["contribution"] / out["year_total_contribution"]
    out["share_pct"] = out["share"] * 100.0
    out["scheme"] = scheme_name
    out["population"] = "matched_only" if matched_only else "all_rows_missing_visibility_equal"
    return out


def compute_decade_summary(year_shares: pd.DataFrame) -> pd.DataFrame:
    ys = year_shares.copy()
    ys = ys[ys["year"].between(1980, 2029)].copy()
    ys["decade"] = (ys["year"] // 10 * 10).astype(int).astype(str) + "s"
    # Average annual shares so late years with more titles do not dominate the decade.
    dec = ys.groupby(["population", "scheme", "decade", "archetype"], as_index=False)["share_pct"].mean()
    return dec


def coverage_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    d = df.groupby("year", as_index=False).agg(
        rows=("row_id", "count"),
        unique_games=("game", "nunique"),
        visibility_available=("visibility_available", "sum"),
        median_reviews=("reviews", "median"),
        max_reviews=("reviews", "max"),
    )
    d["visibility_coverage_pct"] = 100 * d["visibility_available"] / d["rows"]
    return d


def pivot_full_grid(year_shares: pd.DataFrame, archetypes: List[str]) -> pd.DataFrame:
    years = sorted(year_shares["year"].dropna().astype(int).unique())
    idx = pd.MultiIndex.from_product([years, archetypes], names=["year", "archetype"])
    y = year_shares.set_index(["year", "archetype"])["share_pct"].reindex(idx, fill_value=0).reset_index()
    return y


def plot_linecharts(year_shares: pd.DataFrame, outdir: Path, population: str, schemes: List[str], archetypes: List[str], rolling: int = 5) -> None:
    sub = year_shares[(year_shares["population"] == population) & (year_shares["scheme"].isin(schemes))].copy()
    if sub.empty:
        return
    fig, axes = plt.subplots(2, 2, figsize=(18, 10), sharex=True, sharey=True)
    axes = axes.ravel()
    for ax, scheme in zip(axes, schemes):
        s = sub[sub["scheme"] == scheme]
        for arch in archetypes:
            a = s[s["archetype"] == arch].sort_values("year")
            if a.empty:
                continue
            series = a.set_index("year")["share_pct"].sort_index()
            # Fill missing years to avoid jumping over gaps, then rolling.
            full_idx = range(int(series.index.min()), int(series.index.max()) + 1)
            series = series.reindex(full_idx)
            if rolling and rolling > 1:
                series = series.rolling(rolling, min_periods=max(1, rolling // 2)).mean()
            ax.plot(series.index, series.values, linewidth=1.3, label=arch)
        ax.set_title(scheme)
        ax.set_xlabel("release year")
        ax.set_ylabel("annual share (%)")
        ax.grid(True, alpha=0.2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=8)
    fig.suptitle(f"Archetype shares by visibility weighting ({population}, {rolling}-year rolling mean)", y=0.98)
    fig.tight_layout(rect=[0, 0.08, 1, 0.95])
    fig.savefig(outdir / f"linecharts_{population}_{rolling}yr.png", dpi=180)
    plt.close(fig)


def plot_heatmaps(year_shares: pd.DataFrame, outdir: Path, population: str, schemes: List[str], archetypes: List[str], year_min: int = 1980) -> None:
    sub = year_shares[(year_shares["population"] == population) & (year_shares["scheme"].isin(schemes)) & (year_shares["year"] >= year_min)].copy()
    if sub.empty:
        return
    vmax = np.nanpercentile(sub["share_pct"], 99)
    fig, axes = plt.subplots(1, len(schemes), figsize=(5.2 * len(schemes), 8), sharey=True)
    if len(schemes) == 1:
        axes = [axes]
    for ax, scheme in zip(axes, schemes):
        s = sub[sub["scheme"] == scheme]
        piv = s.pivot_table(index="year", columns="archetype", values="share_pct", fill_value=0)
        # Keep requested order.
        piv = piv[[a for a in archetypes if a in piv.columns]]
        im = ax.imshow(piv.values, aspect="auto", origin="lower", vmin=0, vmax=vmax, cmap="viridis")
        ax.set_title(scheme)
        ax.set_xlabel("archetype")
        ax.set_xticks(range(len(piv.columns)))
        ax.set_xticklabels(piv.columns, rotation=70, ha="right", fontsize=7)
        # Reasonable y ticks.
        years = piv.index.tolist()
        tick_idx = [i for i, y in enumerate(years) if y % 5 == 0]
        ax.set_yticks(tick_idx)
        ax.set_yticklabels([years[i] for i in tick_idx], fontsize=8)
        ax.set_ylabel("release year")
    cbar = fig.colorbar(im, ax=axes, shrink=0.7)
    cbar.set_label("annual share (%)")
    fig.suptitle(f"Heatmaps by visibility weighting ({population})", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(outdir / f"heatmaps_{population}.png", dpi=180)
    plt.close(fig)


def plot_coverage(coverage: pd.DataFrame, outdir: Path) -> None:
    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(coverage["year"], coverage["rows"], label="protagonist rows", linewidth=1.5)
    ax1.plot(coverage["year"], coverage["unique_games"], label="unique games", linewidth=1.5)
    ax1.set_xlabel("release year")
    ax1.set_ylabel("count")
    ax1.grid(True, alpha=0.2)
    ax2 = ax1.twinx()
    ax2.plot(coverage["year"], coverage["visibility_coverage_pct"], linestyle="--", label="visibility coverage (%)", linewidth=1.2)
    ax2.set_ylabel("visibility coverage (%)")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")
    ax1.set_title("Corpus size and visibility coverage by year")
    fig.tight_layout()
    fig.savefig(outdir / "coverage_by_year.png", dpi=180)
    plt.close(fig)


def make_zip(outdir: Path) -> Path:
    zip_path = outdir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in outdir.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(outdir.parent))
    return zip_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--annotations", type=Path, default=Path("igdb_archetype_annotations_simple_characters_only_v001 (1).csv"))
    ap.add_argument("--metadata", type=Path, default=Path("igdb_master_broad_with_steam_llm_overlap_v001.csv"))
    ap.add_argument("--outdir", type=Path, default=Path("archetype_visibility_weight_outputs_v001"))
    ap.add_argument("--min-year", type=int, default=1970)
    ap.add_argument("--matched-only-also", action="store_true", default=True)
    args = ap.parse_args()

    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    ann = read_annotations(args.annotations)
    md_path = args.metadata if args.metadata and args.metadata.exists() else None
    df = attach_visibility(ann, md_path)
    df = make_visibility_weights(df)
    df = df[df["year"] >= args.min_year].copy()

    schemes = {
        "equal": "weight_equal",
        "raw_reviews": "weight_raw_reviews",
        "raw_cap_p99": "weight_raw_cap_p99",
        "sqrt_reviews": "weight_sqrt_reviews",
        "log_reviews": "weight_log_reviews",
        "log_cap_p99": "weight_log_cap_p99",
        "blend_equal_log": "weight_blend_equal_log",
        "tiered_reviews": "weight_tiered_reviews",
    }

    # Archetype order = canonical + any unexpected values.
    observed = pd.unique(pd.concat([df["arch1"], df["arch2"], df["arch3"]]).dropna())
    archetypes = [a for a in DEFAULT_ARCHETYPE_ORDER if a in set(observed)] + sorted([a for a in observed if a not in DEFAULT_ARCHETYPE_ORDER])

    all_year = []
    for scheme_name, col in schemes.items():
        all_year.append(compute_year_shares(df, col, scheme_name, matched_only=False))
        all_year.append(compute_year_shares(df, col, scheme_name, matched_only=True))
    year_shares = pd.concat([x for x in all_year if x is not None and not x.empty], ignore_index=True)
    dec = compute_decade_summary(year_shares)
    coverage = coverage_diagnostics(df)

    # Save merged analysis table and outputs.
    keep_cols = [
        "row_id", "game", "year", "protagonist", "arch1", "arch2", "arch3", "confidence", "confidence_0_1",
        "reviews", "visibility_available", "visibility_match_method",
        "weight_equal", "weight_raw_reviews", "weight_raw_cap_p99", "weight_sqrt_reviews",
        "weight_log_reviews", "weight_log_cap_p99", "weight_blend_equal_log", "weight_tiered_reviews",
    ]
    keep_cols = [c for c in keep_cols if c in df.columns]
    df[keep_cols].to_csv(outdir / "merged_rows_with_visibility_weights.csv", index=False)
    year_shares.to_csv(outdir / "year_archetype_shares_by_weight_scheme_long.csv", index=False)
    dec.to_csv(outdir / "decade_archetype_shares_by_weight_scheme_long.csv", index=False)
    coverage.to_csv(outdir / "year_visibility_coverage.csv", index=False)

    # Wide pivot for easier inspection.
    for pop in sorted(year_shares["population"].unique()):
        for scheme in schemes.keys():
            s = year_shares[(year_shares["population"] == pop) & (year_shares["scheme"] == scheme)]
            if s.empty:
                continue
            wide = s.pivot_table(index="year", columns="archetype", values="share_pct", fill_value=0)
            wide = wide[[a for a in archetypes if a in wide.columns]]
            wide.to_csv(outdir / f"wide_year_{pop}_{scheme}.csv")

    # Plots: compare four most informative schemes.
    plot_schemes = ["equal", "raw_cap_p99", "sqrt_reviews", "log_cap_p99"]
    # If all archetypes visible, but legend can be large. We keep all 12.
    for pop in sorted(year_shares["population"].unique()):
        plot_linecharts(year_shares, outdir, pop, plot_schemes, archetypes, rolling=5)
        plot_heatmaps(year_shares, outdir, pop, plot_schemes, archetypes, year_min=max(args.min_year, 1980))
    plot_coverage(coverage, outdir)

    # Small README.
    readme = f"""# Archetype visibility weighting outputs

Input annotations: `{args.annotations}`
Input metadata: `{args.metadata if md_path else 'none'}`
Rows after min-year filter: {len(df):,}
Rows with positive review visibility: {int(df['visibility_available'].sum()):,} ({100*df['visibility_available'].mean():.1f}%)

## Weight schemes
- `equal`: each protagonist/game row has weight 1.
- `raw_reviews`: raw Steam review count. Use only as a stress test; megahits dominate.
- `raw_cap_p99`: raw reviews capped at 99th percentile.
- `sqrt_reviews`: intermediate damping.
- `log_reviews`: log1p(review count), strongly damped.
- `log_cap_p99`: log1p(review count), capped at 99th percentile. Recommended visibility model.
- `blend_equal_log`: 50% equal + 50% normalized log visibility.
- `tiered_reviews`: coarse log10 tiers.

## Populations
- `all_rows_missing_visibility_equal`: all rows included; missing review counts get a neutral visibility weight of 1.
- `matched_only`: only rows with positive review visibility included. Better for Steam-linked recent subset; more biased historically.

## Main files
- `merged_rows_with_visibility_weights.csv`
- `year_archetype_shares_by_weight_scheme_long.csv`
- `decade_archetype_shares_by_weight_scheme_long.csv`
- `year_visibility_coverage.csv`
- `linecharts_*_5yr.png`
- `heatmaps_*.png`
- `coverage_by_year.png`
"""
    (outdir / "README.md").write_text(readme, encoding="utf-8")

    zip_path = make_zip(outdir)
    print(f"Saved outputs to {outdir}")
    print(f"Saved zip to {zip_path}")
    print(readme)


if __name__ == "__main__":
    main()
