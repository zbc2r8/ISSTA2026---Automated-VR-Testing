#!/usr/bin/env python3
"""Generate a short defect severity report for spatial or temporal analysis."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable

import pandas as pd

# Heuristic thresholds. These are easy to adjust in one place.
MINOR_MAX_LENGTH = 2
MODERATE_MAX_LENGTH = 5
SEVERE_MIN_LENGTH = 6

COVERAGE_SEVERE_THRESHOLD = 0.30
INSTABILITY_THRESHOLD = 0.15
PERSISTENCE_RATIO_THRESHOLD = 0.20

GAME_ORDER = [
    "Archery",
    "PhantomLimb",
    "PhantomLimb Holdout",
    "PianoTiles",
    "Puzzle",
    "Sea",
    "War",
]

TOOLTIPS = {
    "total rows": "Number of labeled data points in the analysis. Formula: count(all rows)",
    "total defects": "Number of defective data points. Formula: count(defect rows)",
    "frequency": "Proportion of defective frames. Formula: defects / total_frames",
    "coverage": "Portion of session affected by defects. Formula: defects / total_frames",
    "mean persistence": "Average length of continuous defect segments. Formula: mean(segment lengths)",
    "max persistence": "Longest continuous defect segment. Formula: max(segment lengths)",
    "instability_rate": "Number of label changes normalized by sequence length. Formula: transitions / (N - 1)",
}

CLASSIFICATION_EXPLANATIONS = {
    "short isolated defects": (
        "This game is classified as short isolated defects, meaning defects occur in shorter and more limited bursts."
    ),
    "unstable defects": (
        "This game is classified as unstable defects, meaning the labels switch frequently between correct and defective."
    ),
    "long-lasting defects": (
        "This game is classified as long-lasting defects, meaning defects persist for long stretches or affect a large part of the execution."
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--analysis_type",
        required=True,
        choices=["spatial", "temporal"],
        help="Choose which analysis outputs to summarize.",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root containing results/severity_metrics and results/severity.",
    )
    return parser.parse_args()


def escape_html(text: object) -> str:
    value = "N/A" if text is None else str(text)
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def find_input_file(project_root: Path, analysis_type: str, base_name: str) -> Path:
    """Support both suffixed filenames and the existing per-folder layout."""

    candidates = [
        project_root / "results" / "severity" / f"{base_name}_{analysis_type}.csv",
        project_root / "results" / "severity_metrics" / analysis_type / f"{base_name}.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find input file for {base_name} ({analysis_type})")


def find_image_candidates(project_root: Path, analysis_type: str, stem: str) -> list[Path]:
    """Return existing image candidates for one logical image slot."""

    severity_dir = project_root / "results" / "severity"
    metrics_dir = project_root / "results" / "severity_metrics" / analysis_type
    candidates = [
        severity_dir / f"{analysis_type}_{stem}.png",
        metrics_dir / f"{stem}.png",
    ]
    return [path for path in candidates if path.exists()]


def find_game_images(project_root: Path, analysis_type: str, game: str) -> list[Path]:
    safe = game.replace(" ", "_")
    metrics_dir = project_root / "results" / "severity_metrics" / analysis_type
    severity_dir = project_root / "results" / "severity"

    if game == "PhantomLimb":
        candidates = [
            severity_dir / f"{analysis_type}_{safe}_defect_map.png",
            metrics_dir / f"{safe}_defect_map.png",
            metrics_dir / f"{safe}_main_data_defect_map.png",
            metrics_dir / f"{safe}_extra_data_defect_map.png",
        ]
    else:
        candidates = [
            severity_dir / f"{analysis_type}_{safe}_defect_map.png",
            metrics_dir / f"{safe}_defect_map.png",
        ]

    existing: list[Path] = []
    for path in candidates:
        if path.exists() and path not in existing:
            existing.append(path)
    return existing


def relative_image_path(report_path: Path, image_path: Path) -> str:
    return os.path.relpath(image_path, start=report_path.parent)


def fmt_ratio(value: object, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.{digits}f}"


def fmt_percent_from_ratio(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value) * 100:.1f}%"


def fmt_percent(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.1f}%"


def fmt_data_points(value: object) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.1f} data points"


def classify_game(game_row: pd.Series | None) -> tuple[str, str]:
    if game_row is None:
        return "short isolated defects", "short isolated: fallback"

    coverage = float(game_row["coverage"]) if pd.notna(game_row["coverage"]) else None
    max_persistence = (
        float(game_row["max_segment_length"]) if pd.notna(game_row["max_segment_length"]) else None
    )
    instability_rate = (
        float(game_row["instability_rate"]) if pd.notna(game_row["instability_rate"]) else None
    )
    avg_execution_length = None
    if pd.notna(game_row.get("num_executions")) and float(game_row["num_executions"]) > 0:
        avg_execution_length = float(game_row["total_rows"]) / float(game_row["num_executions"])

    long_lasting = False
    if coverage is not None and coverage >= COVERAGE_SEVERE_THRESHOLD:
        return "long-lasting defects", "long-lasting: coverage"
    if (
        not long_lasting
        and max_persistence is not None
        and avg_execution_length is not None
        and max_persistence >= PERSISTENCE_RATIO_THRESHOLD * avg_execution_length
    ):
        return "long-lasting defects", "long-lasting: persistence"
    if instability_rate is not None and instability_rate >= INSTABILITY_THRESHOLD:
        return "unstable defects", "unstable: instability"
    return "short isolated defects", "short isolated: fallback"


def build_overall_sentences(overall_row: pd.Series | None) -> tuple[str, str]:
    if overall_row is None:
        return (
            "Defects occur at N/A frequency with N/A coverage across the full dataset.",
            "Defects show N/A persistence and N/A instability.",
        )

    sentence1 = (
        f"Defects occur in {float(overall_row['frequency']) * 100:.1f}% of data points overall, "
        f"with {float(overall_row['coverage']) * 100:.1f}% of the full dataset affected."
    )

    mean_persistence = overall_row["mean_segment_length"]
    instability_rate = overall_row["instability_rate"]
    if pd.isna(mean_persistence) or pd.isna(instability_rate):
        sentence2 = "Defects show N/A persistence and N/A instability."
    elif float(mean_persistence) >= SEVERE_MIN_LENGTH:
        sentence2 = (
            f"Defects are frequent overall and include several long-lasting segments, with mean persistence of {float(mean_persistence):.1f} "
            f"data points and instability_rate of {float(instability_rate):.3f}."
        )
    elif float(instability_rate) >= INSTABILITY_THRESHOLD:
        sentence2 = (
            f"Defects are unstable, with mean persistence of {float(mean_persistence):.1f} "
            f"data points and instability_rate of {float(instability_rate):.3f}."
        )
    else:
        sentence2 = (
            f"Defects are mostly short, with mean persistence of {float(mean_persistence):.1f} "
            f"data points and instability_rate of {float(instability_rate):.3f}."
        )
    return sentence1, sentence2


def metric_cell(label: str, value: str) -> str:
    tooltip = TOOLTIPS[label]
    return (
        f'<tr><td title="{escape_html(tooltip)}">{escape_html(label)}</td>'
        f'<td title="{escape_html(tooltip)}">{escape_html(value)}</td></tr>'
    )


def build_html_report(
    analysis_type: str,
    report_path: Path,
    execution_df: pd.DataFrame,
    game_df: pd.DataFrame,
    overall_df: pd.DataFrame,
    project_root: Path,
) -> str:
    overall_row = overall_df.iloc[0] if not overall_df.empty else None
    overall_sentence1, overall_sentence2 = build_overall_sentences(overall_row)
    title = f"{analysis_type.capitalize()} Defect Severity Report"

    html: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{escape_html(title)}</title>",
        (
            "<style>"
            "body{font-family:Arial,sans-serif;max-width:1120px;margin:32px auto;padding:0 20px;color:#222;line-height:1.4}"
            "h1,h2{margin-bottom:8px}"
            "table{border-collapse:collapse;width:100%;max-width:760px;margin:10px 0 16px 0}"
            "th,td{border:1px solid #ccc;padding:8px 10px;text-align:left;vertical-align:top}"
            "th{background:#f5f5f5}"
            "img{max-width:100%;height:auto;border:1px solid #ddd;margin:8px 0 14px 0}"
            "ul{margin-top:8px}"
            ".game{margin-top:28px}"
            "p{max-width:920px}"
            "</style></head><body>"
        ),
        f"<h1>{escape_html(title)}</h1>",
        "<h2>Overall Summary</h2>",
        "<table>",
        "<tr><th>Metric</th><th>Value</th></tr>",
    ]

    overall_rows = [
        ("total rows", "N/A" if overall_row is None else str(int(overall_row["total_rows"]))),
        ("total defects", "N/A" if overall_row is None else str(int(overall_row["defect_count"]))),
        ("frequency", "N/A" if overall_row is None else fmt_ratio(overall_row["frequency"])),
        ("coverage", "N/A" if overall_row is None else fmt_percent_from_ratio(overall_row["coverage"])),
        (
            "mean persistence",
            "N/A" if overall_row is None else fmt_data_points(overall_row["mean_segment_length"]),
        ),
        (
            "max persistence",
            "N/A" if overall_row is None else fmt_data_points(overall_row["max_segment_length"]),
        ),
        (
            "instability_rate",
            "N/A" if overall_row is None else fmt_ratio(overall_row["instability_rate"]),
        ),
    ]
    html.extend(metric_cell(label, value) for label, value in overall_rows)
    html.append("</table>")

    for image_path in find_image_candidates(project_root, analysis_type, "defect_frequency_per_game"):
        html.append(
            f'<img src="{escape_html(relative_image_path(report_path, image_path))}" alt="{escape_html(image_path.name)}">'
        )
    for image_path in find_image_candidates(
        project_root, analysis_type, "defect_segment_lengths_histogram"
    ):
        html.append(
            f'<img src="{escape_html(relative_image_path(report_path, image_path))}" alt="{escape_html(image_path.name)}">'
        )

    html.append(f"<p>{escape_html(overall_sentence1)} {escape_html(overall_sentence2)}</p>")

    html.append("<h2>Severity Pattern Legend</h2>")
    html.append("<table>")
    html.append("<tr><th>Severity Pattern</th><th>Definition</th><th>Rule</th></tr>")
    html.append(
        "<tr><td>Short isolated defects</td><td>Low persistence, low coverage, and not classified as unstable.</td>"
        "<td>Assigned when neither the long-lasting rule nor the unstable rule is triggered.</td></tr>"
    )
    html.append(
        "<tr><td>Unstable defects</td><td>Frequent switching between correct and defective states.</td>"
        f"<td>Assigned when instability_rate &gt;= {INSTABILITY_THRESHOLD:.2f} and the long-lasting rule is not triggered.</td></tr>"
    )
    html.append(
        "<tr><td>Long-lasting defects</td><td>Defects persist for long continuous stretches or affect a large portion of the execution.</td>"
        f"<td>Assigned when coverage &gt;= {COVERAGE_SEVERE_THRESHOLD:.2f} OR max_persistence &gt;= {PERSISTENCE_RATIO_THRESHOLD:.2f} * avg_execution_length.</td></tr>"
    )
    html.append("</table>")
    html.append(
        "<p>These severity patterns are based on configurable operational thresholds for this dataset.</p>"
    )
    html.append("<table>")
    html.append("<tr><th>Threshold</th><th>Value</th></tr>")
    html.append(f"<tr><td>MINOR_MAX_LENGTH</td><td>{MINOR_MAX_LENGTH}</td></tr>")
    html.append(f"<tr><td>MODERATE_MAX_LENGTH</td><td>{MODERATE_MAX_LENGTH}</td></tr>")
    html.append(f"<tr><td>SEVERE_MIN_LENGTH</td><td>{SEVERE_MIN_LENGTH}</td></tr>")
    html.append(f"<tr><td>COVERAGE_SEVERE_THRESHOLD</td><td>{COVERAGE_SEVERE_THRESHOLD:.2f}</td></tr>")
    html.append(f"<tr><td>INSTABILITY_THRESHOLD</td><td>{INSTABILITY_THRESHOLD:.2f}</td></tr>")
    html.append(f"<tr><td>PERSISTENCE_RATIO_THRESHOLD</td><td>{PERSISTENCE_RATIO_THRESHOLD:.2f}</td></tr>")
    html.append("</table>")

    html.append("<h2>All Games Quick Summary</h2>")
    html.append(
        "<table><tr><th>Game</th><th>Frequency</th><th>Coverage</th><th>Mean Persistence</th>"
        "<th>Instability</th><th>Severity Type</th><th>Trigger Rule</th></tr>"
    )
    for game in GAME_ORDER:
        rows = game_df[game_df["game"] == game]
        row = rows.iloc[0] if not rows.empty else None
        classification, trigger_rule = classify_game(row)
        html.append(
            "<tr>"
            f"<td>{escape_html(game)}</td>"
            f"<td>{escape_html('N/A' if row is None else fmt_ratio(row['frequency']))}</td>"
            f"<td>{escape_html('N/A' if row is None else fmt_percent(row['coverage_pct']))}</td>"
            f"<td>{escape_html('N/A' if row is None else fmt_data_points(row['mean_segment_length']))}</td>"
            f"<td>{escape_html('N/A' if row is None else fmt_ratio(row['instability_rate']))}</td>"
            f"<td>{escape_html(classification)}</td>"
            f"<td>{escape_html(trigger_rule)}</td>"
            "</tr>"
        )
    html.append("</table>")

    html.append("<h2>How To Read Metrics</h2>")
    html.append("<ul>")
    html.append("<li>Frequency: how often defects occur</li>")
    html.append("<li>Coverage: how much of the session is affected</li>")
    html.append("<li>Persistence: how long defects last</li>")
    html.append("<li>Instability: how often defects switch</li>")
    html.append("</ul>")

    for game in GAME_ORDER:
        rows = game_df[game_df["game"] == game]
        row = rows.iloc[0] if not rows.empty else None
        classification, trigger_rule = classify_game(row)
        html.append(f'<div class="game"><h2>{escape_html(game)}</h2>')
        html.append("<table><tr><th>Metric</th><th>Value</th></tr>")
        per_game_rows = [
            ("Frequency", "N/A" if row is None else fmt_ratio(row["frequency"])),
            ("Coverage", "N/A" if row is None else fmt_percent(row["coverage_pct"])),
            (
                "Mean Persistence",
                "N/A" if row is None else fmt_data_points(row["mean_segment_length"]),
            ),
            (
                "Max Persistence",
                "N/A" if row is None else fmt_data_points(row["max_segment_length"]),
            ),
            (
                "Instability Rate",
                "N/A" if row is None else fmt_ratio(row["instability_rate"]),
            ),
        ]
        for label, value in per_game_rows:
            html.append(f"<tr><td>{escape_html(label)}</td><td>{escape_html(value)}</td></tr>")
        html.append("</table>")

        for image_path in find_game_images(project_root, analysis_type, game):
            html.append(
                f'<img src="{escape_html(relative_image_path(report_path, image_path))}" alt="{escape_html(image_path.name)}">'
            )

        sentence1 = CLASSIFICATION_EXPLANATIONS[classification]
        if row is None:
            sentence2 = (
                "This is based on Frequency = N/A, Coverage = N/A, Mean Persistence = N/A, "
                "Max Persistence = N/A, and Instability Rate = N/A."
            )
        else:
            high_instability_clause = ""
            if (
                classification == "long-lasting defects"
                and pd.notna(row["instability_rate"])
                and float(row["instability_rate"]) >= INSTABILITY_THRESHOLD
            ):
                high_instability_clause = (
                    f" It also shows high instability (instability_rate = {fmt_ratio(row['instability_rate'])})."
                )

            if (
                classification == "short isolated defects"
                and (
                    (pd.notna(row["mean_segment_length"]) and float(row["mean_segment_length"]) >= 10)
                    or (pd.notna(row["max_segment_length"]) and float(row["max_segment_length"]) >= 20)
                )
            ):
                sentence1 = (
                    "This game does not cross the configured long-lasting or unstable thresholds, although some defect segments are still moderately persistent."
                )

            avg_execution_length = (
                float(row["total_rows"]) / float(row["num_executions"])
                if pd.notna(row["num_executions"]) and float(row["num_executions"]) > 0
                else None
            )
            if trigger_rule == "long-lasting: coverage":
                sentence2 = (
                    f"This classification is triggered because coverage = {fmt_ratio(row['coverage'])}, "
                    f"which is above the threshold of {COVERAGE_SEVERE_THRESHOLD:.2f}.{high_instability_clause}"
                )
            elif trigger_rule == "long-lasting: persistence":
                threshold_value = (
                    PERSISTENCE_RATIO_THRESHOLD * avg_execution_length
                    if avg_execution_length is not None
                    else None
                )
                threshold_text = "N/A" if threshold_value is None else f"{threshold_value:.1f}"
                sentence2 = (
                    f"This classification is triggered because max persistence = {fmt_ratio(row['max_segment_length'], 1)}, "
                    f"which is above the threshold of {threshold_text} data points.{high_instability_clause}"
                )
            elif trigger_rule == "unstable: instability":
                sentence2 = (
                    f"This classification is triggered because instability_rate = {fmt_ratio(row['instability_rate'])}, "
                    f"which is above the threshold of {INSTABILITY_THRESHOLD:.2f}."
                )
            else:
                sentence2 = (
                    "This classification is assigned because neither the long-lasting nor unstable thresholds were reached."
                )
        html.append(f"<p>{escape_html(sentence1)} {escape_html(sentence2)}</p></div>")

    html.append("</body></html>")
    return "\n".join(html)


def build_readme(analysis_type: str) -> str:
    return (
        "SECTION 1 — How to run\n"
        f"Run the script with analysis_type = spatial or temporal.\n\n"
        "SECTION 2 — How to read metrics\n"
        "Frequency = how often defects happen\n"
        "Coverage = how much of the session is affected\n"
        "Persistence = how long defects last\n"
        "Instability = how often defects switch\n\n"
        "SECTION 3 — Severity thresholds\n"
        "The thresholds are heuristic and are not from literature.\n"
        "They can be modified in the script.\n"
        "Changing the thresholds changes classification.\n\n"
        "Current Thresholds\n"
        f"MINOR_MAX_LENGTH = {MINOR_MAX_LENGTH}\n"
        f"MODERATE_MAX_LENGTH = {MODERATE_MAX_LENGTH}\n"
        f"SEVERE_MIN_LENGTH = {SEVERE_MIN_LENGTH}\n"
        f"COVERAGE_SEVERE_THRESHOLD = {COVERAGE_SEVERE_THRESHOLD:.2f}\n"
        f"INSTABILITY_THRESHOLD = {INSTABILITY_THRESHOLD:.2f}\n"
        f"PERSISTENCE_RATIO_THRESHOLD = {PERSISTENCE_RATIO_THRESHOLD:.2f}\n"
        "Changing these values changes how games are classified in the report.\n\n"
        "SECTION 4 — What the report shows\n"
        "The report summarizes defect severity per game.\n"
        "It highlights minor, unstable, and severe patterns.\n"
    )


def main() -> None:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    analysis_type = args.analysis_type

    execution_df = pd.read_csv(
        find_input_file(project_root, analysis_type, "execution_level_metrics")
    )
    game_df = pd.read_csv(find_input_file(project_root, analysis_type, "game_level_metrics"))
    overall_df = pd.read_csv(find_input_file(project_root, analysis_type, "overall_metrics"))
    pd.read_csv(find_input_file(project_root, analysis_type, "defect_segments"))

    output_dir = project_root / "results" / "severity"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{analysis_type}_defect_report.html"
    readme_path = output_dir / f"{analysis_type}_README.txt"

    report_html = build_html_report(
        analysis_type=analysis_type,
        report_path=report_path,
        execution_df=execution_df,
        game_df=game_df,
        overall_df=overall_df,
        project_root=project_root,
    )
    report_path.write_text(report_html, encoding="utf-8")
    readme_path.write_text(build_readme(analysis_type), encoding="utf-8")

    print(f"Report saved to results/severity/{analysis_type}_defect_report.html")
    print(f"README saved to results/severity/{analysis_type}_README.txt")


if __name__ == "__main__":
    main()
