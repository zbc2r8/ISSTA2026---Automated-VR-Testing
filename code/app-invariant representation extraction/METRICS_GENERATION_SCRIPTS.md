# Metrics Generation Scripts

## Primary Scripts (Currently Active)

These are the scripts currently used to generate the metrics data files:

### 1. `extract_all_metrics_complete.py` ⭐ **MAIN EXTRACTION SCRIPT**

**Purpose**: Extracts all 25 common metrics from ALL data files for each app.

**What it does**:
- Processes ALL CSV files in the `data/` folder for each app
- Extracts metrics for rows that have BOTH Spatial and Temporal labels
- Creates individual metrics files: `metrics/metrics_<App>.csv`
- Creates combined file: `extracted_metrics_all_apps.csv`

**Apps processed**:
- Archery (3 CSV files)
- Puzzle (1 CSV file)
- Sea (1 CSV file)
- War (1 CSV file)
- PhantomLimb (17 CSV files)
- PianoTiles (1 CSV file)

**Output files**:
- `metrics/metrics_Archery.csv`
- `metrics/metrics_Puzzle.csv`
- `metrics/metrics_Sea.csv`
- `metrics/metrics_War.csv`
- `metrics/metrics_PhantomLimb.csv`
- `metrics/metrics_PianoTiles.csv`
- `extracted_metrics_all_apps.csv` (combined file)

**Usage**:
```bash
python3 extract_all_metrics_complete.py
```

---

### 2. `add_floor_to_metrics.py` ⭐ **FLOOR INFORMATION SCRIPT**

**Purpose**: Adds floor distance information to the metrics files.

**What it does**:
- Reads floor position data from the original data files
- Calculates `distance_from_floor` and `below_floor` metrics
- Updates the metrics CSV files with floor information

**Usage**:
```bash
python3 add_floor_to_metrics.py
```

**Note**: Run this AFTER `extract_all_metrics_complete.py` to add floor information.

---

## Complete Generation Pipeline

To regenerate all metrics files from scratch:

```bash
# Step 1: Extract all metrics from data files
python3 extract_all_metrics_complete.py

# Step 2: Add floor information
python3 add_floor_to_metrics.py
```

---

## Legacy/Development Scripts (Not Currently Used)

These scripts were used during development but are now superseded by `extract_all_metrics_complete.py`:

- `extract_metrics_simple.py` - Early version, processed only single CSV files per app
- `extract_metrics_csv_only.py` - CSV-only version (didn't handle all data files)
- `extract_metrics_robust.py` - Attempted chunked processing
- `extract_all_metrics.py` - Full-featured version (replaced by complete version)
- `extract_metrics_json.py` - JSON-specific extraction (PhantomLimb/PianoTiles now use CSV)
- `extract_common_metrics.py` - Analysis/exploration script

---

## Script Dependencies

The main script (`extract_all_metrics_complete.py`) uses:
- Python standard library only (`csv`, `os`, `math`)
- No external dependencies required

The floor script (`add_floor_to_metrics.py`) uses:
- Python standard library only (`csv`, `os`, `math`, `datetime`)

---

## Data Flow

```
data/ folder (original CSV files)
    ↓
extract_all_metrics_complete.py
    ↓
metrics/metrics_<App>.csv (individual files)
    ↓
extracted_metrics_all_apps.csv (combined file)
    ↓
add_floor_to_metrics.py
    ↓
metrics/metrics_<App>.csv (updated with floor info)
    ↓
extracted_metrics_all_apps.csv (updated combined file)
```

---

## Current Metrics Extracted

The scripts extract 27 common metrics:

1. `missing_joints_count` - Number of missing joints
2. `missing_joints_ratio` - Ratio of missing joints
3. `collapsed_joints_count` - Number of collapsed/overlapping joints
4. `center_of_mass_x/y/z` - Body center of mass
5. `distance_from_origin` - Distance from origin
6. `bbox_width/height/depth/volume` - Bounding box dimensions
7. `max_joint_distance_from_com` - Maximum joint distance from COM
8. `distance_from_floor` - Distance from floor (COM-based)
9. `min_foot_height_above_floor` - Minimum height of feet above floor (feet-based)
10. `below_floor` - Boolean flag if feet are below floor (feet-based)
11. `left/right_forearm_length` - Forearm segment lengths
12. `left/right_shin_length` - Shin segment lengths
13. `arm_length_symmetry` - Left-right arm length difference
14. `leg_length_symmetry` - Left-right leg length difference
15. `body_upright_x/y/z` - Body upright orientation (head-spinebase direction)
16. `body_forward_x/y/z` - Body forward direction (hands-based, horizontal projection)

Plus identifiers:
- `GlobalID` (when available)
- `EntryID`
- `Spatial` (label)
- `Temporal` (label)
- `App` (app name)
