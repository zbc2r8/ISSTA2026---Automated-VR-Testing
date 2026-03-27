# Severity Metrics Summary

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
