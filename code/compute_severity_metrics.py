#!/usr/bin/env python3
"""Compute simple defect severity metrics from labeled VR CSV logs.

This script scans all CSV files under a data directory, derives execution IDs
from EntryID timestamp gaps, and computes the requested metrics separately for
the Spatial and Temporal binary labels.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from typing import Iterable

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mpl-cache"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "xdg-cache"))

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd


# Segment-length thresholds used for the simple severity proxy.
MINOR_MAX_LEN = 2
MODERATE_MAX_LEN = 5

# A new execution starts when the time gap between adjacent rows exceeds this.
DEFAULT_TIME_GAP_SECONDS = 10

# Binary labels to process independently.
LABEL_COLUMNS = ("Spatial", "Temporal")


def classify_severity_pattern(
    total_rows: int,
    coverage: float,
    max_segment_length: int,
    instability_rate: float,
) -> str:
    """Assign one severity-pattern label to an execution."""

    severe_condition = coverage >= 0.30 or max_segment_length >= 0.20 * total_rows
    unstable_condition = instability_rate > 0.15 and max_segment_length < 0.20 * total_rows

    if severe_condition:
        return "severe_prolonged"
    if unstable_condition:
        return "unstable_switching"
    return "minor_isolated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute per-execution, per-game, and overall defect metrics."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing one subfolder per game/app with CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        default="results/severity_metrics",
        help="Directory where CSV reports and plots will be written.",
    )
    parser.add_argument(
        "--time-gap-seconds",
        type=int,
        default=DEFAULT_TIME_GAP_SECONDS,
        help="Gap between consecutive EntryID timestamps that starts a new execution.",
    )
    return parser.parse_args()


def extract_datetime_from_entryid(entryid: object) -> pd.Timestamp:
    """Convert an EntryID value into a pandas Timestamp.

    Handles both the shorter 12-digit format seen in some datasets and the
    more common 16/17-digit format with millisecond suffixes.
    """

    entryid = str(entryid).strip()

    if not entryid or entryid.lower() == "nan":
        return pd.NaT

    try:
        if len(entryid) == 12:
            month = int(entryid[:1])
            day = int(entryid[1:3])
            year = int(entryid[3:7])
            hour = int(entryid[7:8])
            minute = int(entryid[8:10])
            second = int(entryid[10:])
            millisecond = 0
        else:
            month = int(entryid[:2])
            day = int(entryid[2:4])
            year = int(entryid[4:8])
            hour = int(entryid[8:10])
            minute = int(entryid[10:12])
            second = int(entryid[12:14])
            millisecond = int(entryid[14:]) if len(entryid) > 14 else 0

        return pd.Timestamp(year, month, day, hour, minute, second, millisecond)
    except Exception:
        return pd.NaT


def assign_sequence_ids(df: pd.DataFrame, time_threshold: int) -> pd.Series:
    """Assign execution sequence IDs within one file using EntryID time gaps."""

    if "EntryID" not in df.columns:
        raise KeyError("Missing required column: EntryID")

    timestamps = df["EntryID"].apply(extract_datetime_from_entryid)
    time_diff = timestamps.diff().dt.total_seconds()
    return (time_diff > time_threshold).cumsum().fillna(0).astype(int)


def normalize_binary_label(series: pd.Series) -> pd.Series:
    """Normalize a label column to 0/1 integers and drop invalid values later."""

    normalized = (
        series.astype(str)
        .str.strip()
        .replace(
            {
                "0.0": "0",
                "1.0": "1",
                "false": "0",
                "true": "1",
                "False": "0",
                "True": "1",
            }
        )
    )
    normalized = pd.to_numeric(normalized, errors="coerce")
    normalized = normalized.where(normalized.isin([0, 1]))
    return normalized.astype("Int64")


def severity_from_length(length: int) -> str:
    """Map a defect-segment length to a simple severity level."""

    if length <= MINOR_MAX_LEN:
        return "minor"
    if length <= MODERATE_MAX_LEN:
        return "moderate"
    return "severe"


def find_defect_segments(group: pd.DataFrame) -> list[dict]:
    """Extract contiguous runs of label=0 inside a sorted execution."""

    labels = group["label"].astype(int).tolist()
    orders = (
        group["row_in_execution"].tolist()
        if "row_in_execution" in group.columns
        else group["order_value"].tolist()
    )

    segments: list[dict] = []
    start_pos = None

    for pos, value in enumerate(labels):
        if value == 0 and start_pos is None:
            start_pos = pos
        elif value == 1 and start_pos is not None:
            end_pos = pos - 1
            length = end_pos - start_pos + 1
            segments.append(
                {
                    "start_index": orders[start_pos],
                    "end_index": orders[end_pos],
                    "segment_length": length,
                    "severity_level": severity_from_length(length),
                }
            )
            start_pos = None

    if start_pos is not None:
        end_pos = len(labels) - 1
        length = end_pos - start_pos + 1
        segments.append(
            {
                "start_index": orders[start_pos],
                "end_index": orders[end_pos],
                "segment_length": length,
                "severity_level": severity_from_length(length),
            }
        )

    return segments


def compute_execution_metrics(
    df: pd.DataFrame, label_name: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute metrics for each execution and collect defect segments."""

    execution_rows: list[dict] = []
    segment_rows: list[dict] = []

    grouped = df.groupby(["game", "execution_id"], sort=False)
    for (game, execution_id), group in grouped:
        group = group.sort_values(["order_value", "row_in_file"], kind="stable").reset_index(drop=True)
        group["row_in_execution"] = np.arange(len(group))
        labels = group["label"].astype(int)
        total_rows = int(len(group))
        defect_count = int((labels == 0).sum())

        # Frequency and coverage are the same ratio here; coverage is reported
        # separately so it can also be displayed as a percentage downstream.
        frequency = defect_count / total_rows if total_rows else 0.0
        coverage = frequency

        # Instability counts how often the binary state flips between adjacent rows.
        instability = int(labels.ne(labels.shift(1)).sum() - 1) if total_rows > 0 else 0
        instability = max(instability, 0)
        instability_rate = instability / (total_rows - 1) if total_rows > 1 else 0.0

        segments = find_defect_segments(group)
        segment_lengths = [segment["segment_length"] for segment in segments]

        execution_rows.append(
            {
                "game": game,
                "execution_id": execution_id,
                "total_rows": total_rows,
                "defect_count": defect_count,
                "frequency": frequency,
                "coverage": coverage,
                "coverage_pct": coverage * 100.0,
                "instability": instability,
                "instability_rate": instability_rate,
                "num_defect_segments": len(segment_lengths),
                "mean_segment_length": float(np.mean(segment_lengths)) if segment_lengths else 0.0,
                "median_segment_length": float(np.median(segment_lengths)) if segment_lengths else 0.0,
                "max_segment_length": int(np.max(segment_lengths)) if segment_lengths else 0,
                "severity_pattern": classify_severity_pattern(
                    total_rows=total_rows,
                    coverage=coverage,
                    max_segment_length=int(np.max(segment_lengths)) if segment_lengths else 0,
                    instability_rate=instability_rate,
                ),
            }
        )

        for segment_id, segment in enumerate(segments, start=1):
            segment_rows.append(
                {
                    "game": game,
                    "execution_id": execution_id,
                    "segment_id": segment_id,
                    "start_index": segment["start_index"],
                    "end_index": segment["end_index"],
                    "segment_length": segment["segment_length"],
                    "severity_level": segment["severity_level"],
                    "label_type": label_name,
                }
            )

    execution_df = pd.DataFrame(execution_rows)
    segments_df = pd.DataFrame(segment_rows)
    return execution_df, segments_df


def build_severity_pattern_summary(execution_metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Count how many executions per game fall into each severity-pattern label."""

    summary = (
        execution_metrics_df.groupby(["game", "severity_pattern"]).size().unstack(fill_value=0)
    )
    for column in ["minor_isolated", "unstable_switching", "severe_prolonged"]:
        if column not in summary.columns:
            summary[column] = 0
    summary = summary[["minor_isolated", "unstable_switching", "severe_prolonged"]].reset_index()
    summary["total_executions"] = (
        summary["minor_isolated"] + summary["unstable_switching"] + summary["severe_prolonged"]
    )
    return summary


def aggregate_metrics(
    source_df: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    """Aggregate raw labeled rows into the requested metrics."""

    rows: list[dict] = []
    grouped = source_df.groupby(group_columns, sort=False) if group_columns else [((), source_df)]

    for key, group in grouped:
        if not isinstance(key, tuple):
            key = (key,)

        labels = group["label"].astype(int)
        total_rows = int(len(group))
        defect_count = int((labels == 0).sum())
        frequency = defect_count / total_rows if total_rows else 0.0
        coverage = frequency
        instability = 0
        segment_lengths: list[int] = []

        for _, execution_group in group.groupby("execution_id", sort=False):
            execution_group = execution_group.sort_values(
                ["order_value", "row_in_file"], kind="stable"
            ).reset_index(drop=True)
            execution_group["row_in_execution"] = np.arange(len(execution_group))
            execution_labels = execution_group["label"].astype(int)
            if len(execution_group) > 0:
                instability += int(execution_labels.ne(execution_labels.shift(1)).sum() - 1)
            segment_lengths.extend(
                segment["segment_length"] for segment in find_defect_segments(execution_group)
            )

        instability = max(instability, 0)
        instability_rate = instability / (total_rows - len(group["execution_id"].unique()))
        if total_rows <= len(group["execution_id"].unique()):
            instability_rate = 0.0

        row = {
            "total_rows": total_rows,
            "defect_count": defect_count,
            "frequency": frequency,
            "coverage": coverage,
            "coverage_pct": coverage * 100.0,
            "instability": instability,
            "instability_rate": instability_rate,
            "num_defect_segments": len(segment_lengths),
            "mean_segment_length": float(np.mean(segment_lengths)) if segment_lengths else 0.0,
            "median_segment_length": float(np.median(segment_lengths)) if segment_lengths else 0.0,
            "max_segment_length": int(np.max(segment_lengths)) if segment_lengths else 0,
            "num_executions": int(group["execution_id"].nunique()),
        }

        for column_name, value in zip(group_columns, key):
            row[column_name] = value

        rows.append(row)

    ordered_columns = group_columns + [
        "num_executions",
        "total_rows",
        "defect_count",
        "frequency",
        "coverage",
        "coverage_pct",
        "instability",
        "instability_rate",
        "num_defect_segments",
        "mean_segment_length",
        "median_segment_length",
        "max_segment_length",
    ]

    return pd.DataFrame(rows)[ordered_columns]


def build_overall_metrics(
    labeled_df: pd.DataFrame, execution_metrics_df: pd.DataFrame, game_metrics_df: pd.DataFrame
) -> pd.DataFrame:
    """Create a one-row overall summary plus a few average summary columns."""

    overall_df = aggregate_metrics(labeled_df, group_columns=[])
    overall_df["num_games"] = int(labeled_df["game"].nunique())
    overall_df["avg_execution_frequency"] = execution_metrics_df["frequency"].mean()
    overall_df["avg_execution_coverage_pct"] = execution_metrics_df["coverage_pct"].mean()
    overall_df["avg_execution_instability_rate"] = execution_metrics_df["instability_rate"].mean()
    overall_df["avg_execution_total_rows"] = execution_metrics_df["total_rows"].mean()
    overall_df["avg_execution_defect_count"] = execution_metrics_df["defect_count"].mean()
    overall_df["avg_execution_instability"] = execution_metrics_df["instability"].mean()
    overall_df["avg_execution_num_defect_segments"] = execution_metrics_df["num_defect_segments"].mean()
    overall_df["avg_execution_mean_segment_length"] = execution_metrics_df["mean_segment_length"].mean()
    overall_df["avg_execution_median_segment_length"] = execution_metrics_df["median_segment_length"].mean()
    overall_df["avg_execution_max_segment_length"] = execution_metrics_df["max_segment_length"].mean()
    overall_df["avg_game_frequency"] = game_metrics_df["frequency"].mean()
    overall_df["avg_game_coverage_pct"] = game_metrics_df["coverage_pct"].mean()
    overall_df["avg_game_instability_rate"] = game_metrics_df["instability_rate"].mean()
    overall_df["avg_game_total_rows"] = game_metrics_df["total_rows"].mean()
    overall_df["avg_game_defect_count"] = game_metrics_df["defect_count"].mean()
    overall_df["avg_game_instability"] = game_metrics_df["instability"].mean()
    overall_df["avg_game_num_defect_segments"] = game_metrics_df["num_defect_segments"].mean()
    overall_df["avg_game_mean_segment_length"] = game_metrics_df["mean_segment_length"].mean()
    overall_df["avg_game_median_segment_length"] = game_metrics_df["median_segment_length"].mean()
    overall_df["avg_game_max_segment_length"] = game_metrics_df["max_segment_length"].mean()
    return overall_df


def build_average_summary(metrics_df: pd.DataFrame, level_name: str) -> pd.DataFrame:
    """Compute a simple mean summary across all rows in a report."""

    return pd.DataFrame(
        [
            {
                "summary_level": level_name,
                "num_rows_summarized": int(len(metrics_df)),
                "avg_total_rows": metrics_df["total_rows"].mean(),
                "avg_defect_count": metrics_df["defect_count"].mean(),
                "avg_frequency": metrics_df["frequency"].mean(),
                "avg_coverage": metrics_df["coverage"].mean(),
                "avg_coverage_pct": metrics_df["coverage_pct"].mean(),
                "avg_instability": metrics_df["instability"].mean(),
                "avg_instability_rate": metrics_df["instability_rate"].mean(),
                "avg_num_defect_segments": metrics_df["num_defect_segments"].mean(),
                "avg_mean_segment_length": metrics_df["mean_segment_length"].mean(),
                "avg_median_segment_length": metrics_df["median_segment_length"].mean(),
                "avg_max_segment_length": metrics_df["max_segment_length"].mean(),
            }
        ]
    )


def load_all_labeled_rows(data_dir: Path, time_gap_seconds: int) -> pd.DataFrame:
    """Load all CSV files, derive executions, and keep rows needed for metrics."""

    labeled_frames: list[pd.DataFrame] = []

    for csv_path in sorted(data_dir.rglob("*.csv")):
        game = csv_path.parent.name
        df = pd.read_csv(csv_path)

        required_columns = {"EntryID", "Spatial", "Temporal"}
        missing = required_columns - set(df.columns)
        if missing:
            raise KeyError(f"{csv_path} is missing required columns: {sorted(missing)}")

        df = df.copy()
        df["game"] = game
        df["source_file"] = csv_path.name
        df["row_in_file"] = np.arange(len(df))
        df["timestamp"] = df["EntryID"].apply(extract_datetime_from_entryid)
        df["sequence_id"] = assign_sequence_ids(df, time_gap_seconds)

        # Rows are sorted inside each derived execution before metrics are computed.
        # We keep both timestamp and the original row order so ties remain stable.
        df["order_value"] = np.where(
            df["timestamp"].notna(),
            df["timestamp"].astype("int64"),
            df["row_in_file"],
        )
        df["execution_id"] = (
            df["source_file"].str.replace(".csv", "", regex=False)
            + "__seq_"
            + df["sequence_id"].astype(str)
        )

        labeled_frames.append(
            df[
                [
                    "game",
                    "source_file",
                    "execution_id",
                    "sequence_id",
                    "row_in_file",
                    "order_value",
                    "Spatial",
                    "Temporal",
                ]
            ]
        )

    if not labeled_frames:
        raise FileNotFoundError(f"No CSV files found under {data_dir}")

    return pd.concat(labeled_frames, ignore_index=True)


def plot_frequency_per_game(game_metrics_df: pd.DataFrame, output_path: Path, label_name: str) -> None:
    plt.figure(figsize=(10, 5))
    ordered = game_metrics_df.sort_values("frequency", ascending=False)
    plt.bar(ordered["game"], ordered["frequency"], color="#3366cc")
    plt.ylabel("Defect frequency (defective rows / total rows)")
    plt.xlabel("Game")
    plt.title(f"{label_name} defect frequency per game")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_coverage_per_execution(
    execution_metrics_df: pd.DataFrame, output_path: Path, label_name: str
) -> None:
    plt.figure(figsize=(14, 6))
    ordered = execution_metrics_df.sort_values(["game", "coverage_pct", "execution_id"], ascending=[True, False, True])
    colors = plt.cm.tab20(np.linspace(0, 1, max(1, ordered["game"].nunique())))
    color_map = {game: colors[idx] for idx, game in enumerate(ordered["game"].drop_duplicates())}
    plt.bar(
        np.arange(len(ordered)),
        ordered["coverage_pct"],
        color=[color_map[game] for game in ordered["game"]],
    )
    plt.ylabel("Coverage (% of execution affected)")
    plt.xlabel("Execution")
    plt.title(f"{label_name} coverage per execution")
    plt.xticks([])
    handles = [
        plt.matplotlib.patches.Patch(color=color_map[game], label=game)
        for game in ordered["game"].drop_duplicates()
    ]
    plt.legend(handles=handles, title="Game", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_coverage_boxplot_by_game(
    execution_metrics_df: pd.DataFrame, output_path: Path, label_name: str
) -> None:
    ordered_games = sorted(execution_metrics_df["game"].unique())
    data = [
        execution_metrics_df.loc[execution_metrics_df["game"] == game, "coverage_pct"].to_numpy()
        for game in ordered_games
    ]
    plt.figure(figsize=(10, 6))
    plt.boxplot(data, labels=ordered_games, patch_artist=True)
    plt.ylabel("Coverage (% of execution affected)")
    plt.xlabel("Game")
    plt.title(f"{label_name} coverage distribution by game")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_segment_histogram(segments_df: pd.DataFrame, output_path: Path, label_name: str) -> None:
    plt.figure(figsize=(12, 6))
    if segments_df.empty:
        plt.hist([], bins=1, color="#cc6633")
    else:
        max_len = int(segments_df["segment_length"].max())
        bins = np.arange(1, max_len + 2) - 0.5
        plt.hist(segments_df["segment_length"], bins=bins, color="#cc6633", edgecolor="black")
        # Show fewer integer ticks on long ranges so labels remain legible.
        if max_len <= 20:
            tick_step = 1
        elif max_len <= 50:
            tick_step = 2
        elif max_len <= 100:
            tick_step = 5
        elif max_len <= 200:
            tick_step = 10
        else:
            tick_step = 20

        tick_values = list(range(1, max_len + 1, tick_step))
        if tick_values[-1] != max_len:
            tick_values.append(max_len)
        plt.xticks(tick_values, rotation=45, ha="right")
    plt.ylabel("Count")
    plt.xlabel("Defect segment length (data points)")
    plt.title(f"{label_name} defect segment lengths")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_instability_per_execution(
    execution_metrics_df: pd.DataFrame, output_path: Path, label_name: str
) -> None:
    plt.figure(figsize=(14, 6))
    ordered = execution_metrics_df.sort_values(
        ["game", "instability_rate", "execution_id"], ascending=[True, False, True]
    )
    colors = plt.cm.Set2(np.linspace(0, 1, max(1, ordered["game"].nunique())))
    color_map = {game: colors[idx] for idx, game in enumerate(ordered["game"].drop_duplicates())}
    plt.bar(
        np.arange(len(ordered)),
        ordered["instability_rate"],
        color=[color_map[game] for game in ordered["game"]],
    )
    plt.ylabel("Instability rate (label flips / possible flips)")
    plt.xlabel("Execution")
    plt.title(f"{label_name} instability per execution")
    plt.xticks([])
    handles = [
        plt.matplotlib.patches.Patch(color=color_map[game], label=game)
        for game in ordered["game"].drop_duplicates()
    ]
    plt.legend(handles=handles, title="Game", bbox_to_anchor=(1.02, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_instability_per_game(
    game_metrics_df: pd.DataFrame, output_path: Path, label_name: str
) -> None:
    ordered = game_metrics_df.sort_values("instability_rate", ascending=False)
    plt.figure(figsize=(10, 5))
    plt.bar(ordered["game"], ordered["instability_rate"], color="#b45f06")
    plt.ylabel("Instability rate (label flips / possible flips)")
    plt.xlabel("Game")
    plt.title(f"{label_name} instability per game")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_severity_counts_per_game(
    segments_df: pd.DataFrame, games: Iterable[str], output_path: Path, label_name: str
) -> None:
    severity_order = ["minor", "moderate", "severe"]
    pivot = (
        segments_df.groupby(["game", "severity_level"]).size().unstack(fill_value=0)
        if not segments_df.empty
        else pd.DataFrame(index=list(games), columns=severity_order).fillna(0)
    )
    pivot = pivot.reindex(index=list(games), fill_value=0)
    pivot = pivot.reindex(columns=severity_order, fill_value=0)

    ax = pivot.plot(kind="bar", stacked=False, figsize=(10, 5), color=["#6aa84f", "#f1c232", "#cc0000"])
    ax.set_ylabel("Number of defect segments (count)")
    ax.set_xlabel("Game")
    ax.set_title(f"{label_name} severity counts per game")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def plot_defect_maps_by_game(label_df: pd.DataFrame, output_dir: Path, label_name: str) -> None:
    """Create one defect timeline heatmap per game.

    Each row is one execution. Each column is one ordered data point inside
    that execution. Red marks defects (0), light gray marks correct rows (1).
    """

    for game, game_df in label_df.groupby("game", sort=True):
        safe_game = game.replace(" ", "_")

        for existing_path in output_dir.glob(f"{safe_game}_defect_map*.png"):
            existing_path.unlink()

        execution_groups: list[tuple[str, pd.DataFrame]] = []
        for execution_id, execution_df in game_df.groupby("execution_id", sort=False):
            execution_df = execution_df.sort_values(
                ["order_value", "row_in_file"], kind="stable"
            ).reset_index(drop=True)
            execution_df["row_in_execution"] = np.arange(len(execution_df))
            execution_groups.append((execution_id, execution_df))

        if not execution_groups:
            continue

        panels: list[tuple[str, list[tuple[str, pd.DataFrame]], str]] = []
        if game == "PhantomLimb":
            main_data = [
                item for item in execution_groups
                if item[1]["source_file"].iloc[0] == "PhantomLimb_Data.csv"
            ]
            extra_data = [
                item for item in execution_groups
                if item[1]["source_file"].iloc[0] != "PhantomLimb_Data.csv"
            ]
            if main_data:
                panels.append(("PhantomLimb main data", main_data, f"{safe_game}_main_data_defect_map.png"))
            if extra_data:
                panels.append(("PhantomLimb extra data", extra_data, f"{safe_game}_extra_data_defect_map.png"))
        else:
            panels.append((game, execution_groups, f"{safe_game}_defect_map.png"))

        for panel_title, panel_executions, filename in panels:
            max_len = max(len(execution_df) for _, execution_df in panel_executions)
            matrix = np.full((len(panel_executions), max_len), np.nan)
            y_labels: list[str] = []

            for row_idx, (execution_id, execution_df) in enumerate(panel_executions):
                labels = execution_df["label"].astype(float).to_numpy()
                matrix[row_idx, : len(labels)] = labels
                y_labels.append(execution_id.replace("__seq_", " / seq "))

            cmap = plt.matplotlib.colors.ListedColormap(["#d7191c", "#d9d9d9"])
            cmap.set_bad(color="white")
            norm = plt.matplotlib.colors.BoundaryNorm([-0.5, 0.5, 1.5], cmap.N)

            fig_height = max(3.5, 0.5 * len(panel_executions) + 1.8)
            fig, ax = plt.subplots(figsize=(14, fig_height))
            image = ax.imshow(matrix, aspect="auto", interpolation="nearest", cmap=cmap, norm=norm)
            colorbar = fig.colorbar(image, ax=ax, ticks=[0, 1], fraction=0.03, pad=0.04)
            colorbar.set_label("State")
            colorbar.set_ticklabels(["defect", "no defect"])

            tick_count = min(max_len, 12)
            x_ticks = np.linspace(0, max_len - 1, num=tick_count, dtype=int) if max_len > 1 else np.array([0])
            x_ticks = np.unique(x_ticks)
            ax.set_xticks(x_ticks)
            ax.set_xticklabels(x_ticks)
            ax.set_yticks(np.arange(len(y_labels)))
            ax.set_yticklabels(y_labels, fontsize=8)
            ax.set_xlabel("Ordered data point index within execution (1 row = 1 data point)")
            ax.set_ylabel("Execution")
            ax.set_title(f"{label_name} defect map: {panel_title}")

            for row_idx, (_, execution_df) in enumerate(panel_executions):
                execution_len = len(execution_df)
                if execution_len > 0:
                    ax.vlines(
                        execution_len - 0.5,
                        row_idx - 0.5,
                        row_idx + 0.5,
                        colors="#111111",
                        linewidth=2.0,
                    )

            fig.subplots_adjust(bottom=0.16)
            fig.text(
                0.5,
                0.02,
                "Red = defect | Gray = no defect | Black vertical line = execution end",
                ha="center",
                va="bottom",
                fontsize=9,
            )
            fig.tight_layout(rect=[0, 0.05, 1, 1])
            fig.savefig(output_dir / filename, dpi=200)
            plt.close(fig)


def write_label_reports(base_df: pd.DataFrame, label_name: str, output_dir: Path) -> None:
    """Write CSV reports and plots for one label column."""

    label_df = base_df.copy()
    label_df["label"] = normalize_binary_label(label_df[label_name])
    label_df = label_df.dropna(subset=["label"]).copy()

    execution_metrics_df, segments_df = compute_execution_metrics(label_df, label_name)
    game_metrics_df = aggregate_metrics(label_df, group_columns=["game"])
    overall_metrics_df = build_overall_metrics(label_df, execution_metrics_df, game_metrics_df)
    execution_average_df = build_average_summary(execution_metrics_df, "execution")
    game_average_df = build_average_summary(game_metrics_df, "game")
    severity_pattern_summary_df = build_severity_pattern_summary(execution_metrics_df)

    interpretation_execution_df = execution_metrics_df[
        [
            "game",
            "execution_id",
            "total_rows",
            "defect_count",
            "coverage",
            "num_defect_segments",
            "mean_segment_length",
            "max_segment_length",
            "instability",
            "instability_rate",
            "severity_pattern",
        ]
    ].rename(columns={"num_defect_segments": "num_segments"})

    output_dir.mkdir(parents=True, exist_ok=True)

    execution_metrics_df.to_csv(output_dir / "execution_level_metrics.csv", index=False)
    interpretation_execution_df.to_csv(output_dir / "execution_severity_patterns.csv", index=False)
    execution_average_df.to_csv(output_dir / "execution_level_averages.csv", index=False)
    game_metrics_df.to_csv(output_dir / "game_level_metrics.csv", index=False)
    severity_pattern_summary_df.to_csv(output_dir / "severity_pattern_counts_by_game.csv", index=False)
    game_average_df.to_csv(output_dir / "game_level_averages.csv", index=False)
    overall_metrics_df.to_csv(output_dir / "overall_metrics.csv", index=False)

    segments_output = segments_df.drop(columns=["label_type"]) if not segments_df.empty else pd.DataFrame(
        columns=[
            "game",
            "execution_id",
            "segment_id",
            "start_index",
            "end_index",
            "segment_length",
            "severity_level",
        ]
    )
    segments_output.to_csv(output_dir / "defect_segments.csv", index=False)

    plot_frequency_per_game(game_metrics_df, output_dir / "defect_frequency_per_game.png", label_name)
    plot_coverage_per_execution(
        execution_metrics_df, output_dir / "coverage_per_execution.png", label_name
    )
    plot_coverage_boxplot_by_game(
        execution_metrics_df, output_dir / "coverage_boxplot_by_game.png", label_name
    )
    plot_segment_histogram(segments_df, output_dir / "defect_segment_lengths_histogram.png", label_name)
    plot_instability_per_execution(
        execution_metrics_df, output_dir / "instability_per_execution.png", label_name
    )
    plot_instability_per_game(game_metrics_df, output_dir / "instability_per_game.png", label_name)
    plot_severity_counts_per_game(
        segments_df,
        games=game_metrics_df["game"].tolist(),
        output_path=output_dir / "severity_counts_per_game.png",
        label_name=label_name,
    )
    plot_defect_maps_by_game(label_df, output_dir, label_name)


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    output_root = Path(args.output_dir).resolve()

    base_df = load_all_labeled_rows(data_dir, args.time_gap_seconds)

    for label_name in LABEL_COLUMNS:
        write_label_reports(base_df, label_name, output_root / label_name.lower())

    write_summary_readme(output_root)
    print(f"Reports written to: {output_root}")


def write_summary_readme(output_root: Path) -> None:
    readme_text = """# Severity Metrics Summary

This folder contains simple defect-severity summaries computed from the labeled VR log files in `data/`.

The reports are produced separately for the `Spatial` label and the `Temporal` label.
Each label folder contains:

- `execution_level_metrics.csv`: one row per execution/session
- `execution_severity_patterns.csv`: compact execution-level interpretation table
- `execution_level_averages.csv`: average values across all executions
- `game_level_metrics.csv`: one row per game/app
- `severity_pattern_counts_by_game.csv`: count of executions in each severity pattern
- `game_level_averages.csv`: average values across all games
- `overall_metrics.csv`: one-row summary for the full dataset, plus average execution and average game values
- `defect_segments.csv`: one row per contiguous defect segment
- `defect_frequency_per_game.png`
- `coverage_per_execution.png`
- `coverage_boxplot_by_game.png`
- `defect_segment_lengths_histogram.png`
- `instability_per_execution.png`
- `instability_per_game.png`
- `severity_counts_per_game.png`

## Label convention

- `1` = correct behavior
- `0` = defect

Rows are sorted inside each execution before metrics are computed.
Executions are derived from `EntryID` time gaps. A new execution starts when the gap between adjacent rows is greater than 10 seconds.

## Core metrics

The analysis is organized around four severity dimensions.

### Frequency

Frequency measures how often defects appear in the collected data.

Definition:

`frequency = defect_count / total_rows`

Interpretation:

- high frequency means defects appear often in the observed interaction stream
- low frequency means defects are relatively rare

Files and plots:

- `execution_level_metrics.csv`
- `game_level_metrics.csv`
- `overall_metrics.csv`
- `defect_frequency_per_game.png`

### Coverage

Coverage measures how much of a session is affected by defects.

Definition:

`coverage = defect_count / total_rows`

`coverage_pct = coverage * 100`

Interpretation:

- high coverage means a large portion of the execution is defective
- low coverage means defects affect only a limited part of the session

Files and plots:

- `execution_level_metrics.csv`
- `game_level_metrics.csv`
- `overall_metrics.csv`
- `coverage_per_execution.png`
- `coverage_boxplot_by_game.png`

### Persistence

Persistence measures how long defects continue once they start.
A defect segment is a contiguous run of `0` labels inside one execution.

Reported values:

- `num_defect_segments`
- `mean_segment_length`
- `median_segment_length`
- `max_segment_length`

Interpretation:

- many short segments suggest isolated failures
- long segments suggest sustained disruption

Files and plots:

- `defect_segments.csv`
- `execution_level_metrics.csv`
- `game_level_metrics.csv`
- `overall_metrics.csv`
- `defect_segment_lengths_histogram.png`
- `severity_counts_per_game.png`

### Instability

Instability measures repeated disruption of interaction continuity.
It counts how often the label flips between correct and defect states inside an execution.

Definition:

`instability = count(label[i] != label[i-1])`

`instability_rate = instability / (N - 1)`

Interpretation:

- high instability means the interaction keeps switching between correct and defective states
- low instability means the behavior is more stable over time, even if it contains defects

Files and plots:

- `execution_level_metrics.csv`
- `game_level_metrics.csv`
- `overall_metrics.csv`
- `instability_per_execution.png`
- `instability_per_game.png`

## Supporting values

### Defect count

Number of rows with label `0`.

Formula:

`defect_count = count(label == 0)`

Segment length is measured in data points. One row in the source CSV is treated as one data point.
If one row corresponds to one frame, then the unit is effectively frames.
If one row corresponds to a fixed time window, then the unit is effectively windows.
The script does not convert segment length to milliseconds or seconds.

### Severity proxy

Severity is assigned per defect segment using only segment length.

- `minor`: length 1-2
- `moderate`: length 3-5
- `severe`: length 6+

These thresholds are defined near the top of `code/compute_severity_metrics.py` and can be changed without touching the rest of the script.

## Execution severity patterns

Each execution is also assigned one overall severity-pattern label.

Rule order:

1. `severe_prolonged`
2. `unstable_switching`
3. `minor_isolated`

### severe_prolonged

Assigned when either of these is true:

- `coverage >= 0.30`
- `max_segment_length >= 0.20 * total_rows`

This captures executions where defects affect a large part of the session or remain present for a long uninterrupted block.

### unstable_switching

Assigned when:

- `instability_rate > 0.15`
- `max_segment_length < 0.20 * total_rows`

This captures executions with repeated switching between correct and defect states, without one long dominant defect block.

### minor_isolated

Assigned when the execution is not classified as `severe_prolonged` or `unstable_switching`.

This captures executions where defects remain comparatively limited and isolated.

Files:

- `execution_severity_patterns.csv`
- `severity_pattern_counts_by_game.csv`

## Notes on interpretation

- High frequency or high coverage means a large share of the log is defective.
- High instability means the label flips often, which points to inconsistent behavior over time.
- Long segments indicate persistent defects rather than isolated failures.
- The severity labels here are heuristic. They are useful for summary reporting, but they are not a substitute for domain-specific manual review.
- In the plots, `data points` means labeled observations taken directly from the CSV rows.
"""
    (output_root / "README.md").write_text(readme_text)


if __name__ == "__main__":
    main()
