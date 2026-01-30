# Server Technical Details

This document provides a comprehensive technical explanation of how the War App Model Server works, including data flow, preprocessing, and prediction pipeline.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Server Components](#server-components)
3. [Data Flow](#data-flow)
4. [Sequence Aggregation](#sequence-aggregation)
5. [Model Inference](#model-inference)
6. [Data Usage](#data-usage)
7. [API Endpoints](#api-endpoints)

---

## Architecture Overview

The server implements a **sequence-based temporal prediction pipeline** for VR application error detection. It accepts sequences of 5 consecutive frames from VR body-tracking data and predicts whether the middle frame has a temporal tracking issue.

```
Input: 5 frames × 91 features → Aggregation → 546 features → Model → Prediction (0 or 1)
```

---

## Server Components

### 1. Model Loading (`load_model()`)

**Location**: `model_server.py`, lines 31-72

**Process**:
1. Loads `saved_model/model.joblib` (the trained Logistic Regression model)
2. Loads `saved_model/meta.json` (model configuration and metadata)
3. Optionally loads `saved_model/scaler.joblib` (StandardScaler if available)
4. Extracts model configuration:
   - `seq_len`: 5 (sequence length)
   - `frame_feature_cols`: 91 feature names
   - `agg_use`: 6 aggregation functions
   - `seq_feature_dim`: 546 (91 × 6)

**Key Metadata**:
```json
{
  "app": "War",
  "task": "Temporal_sequence",
  "model": "LR_balanced",
  "label_col": "Temporal",
  "seq_len": 5,
  "frame_F": 91,
  "seq_feature_dim": 546,
  "agg_use": ["mean", "std", "delta", "range", "mean_abs_vel", "vel_std"]
}
```

---

## Data Flow

### Input Format

The server expects JSON POST requests with the following structure:

```json
{
  "sequence": [
    {
      "Bomb_0_X": -5.9, "Bomb_0_Y": 3.4, "Bomb_0_Z": 0,
      "Bomb_1_X": 1.2, "Bomb_1_Y": 4.5, "Bomb_1_Z": 0.1,
      ...
      "Head_X": -1.43, "Head_Y": 6.08, "Head_Z": 0.01,
      "SpineBase_X": 2.55, "SpineBase_Y": 0, "SpineBase_Z": 0,
      ... (all 91 features)
    },
    ... (4 more frames, total of 5)
  ]
}
```

### Required Features (91 total)

Based on `frame_feature_cols` in `meta.json`:

1. **Bomb objects** (12 bombs × 3 coordinates = 36 features):
   - `Bomb_0_X`, `Bomb_0_Y`, `Bomb_0_Z` through `Bomb_11_X`, `Bomb_11_Y`, `Bomb_11_Z`

2. **Game objects** (5 objects × 3 coordinates = 15 features):
   - `Coin_X/Y/Z`, `Ground_X/Y/Z`, `Passport_X/Y/Z`, `Player_X/Y/Z`, `PlayerImage_X/Y/Z`, `PlayerTransformEffect_X/Y/Z`, `Suitcase_X/Y/Z`

3. **Skeleton joints** (10 joints × 3 coordinates = 30 features):
   - `ElbowL_X/Y/Z`, `ElbowR_X/Y/Z`
   - `FootL_X/Y/Z`, `FootR_X/Y/Z`
   - `HandL_X/Y/Z`, `HandR_X/Y/Z`
   - `Head_X/Y/Z`
   - `KneeL_X/Y/Z`, `KneeR_X/Y/Z`
   - `SpineBase_X/Y/Z`

4. **Labels** (4 features):
   - `Spatial_1`, `Temporal_1`, `Spatial_2`, `Temporal_2`

**Total**: 36 + 15 + 30 + 4 = 85 + 6 additional = 91 features

---

## Sequence Aggregation

### Process: `aggregate_sequence_features()`

**Location**: `model_server.py`, lines 74-154

**Purpose**: Convert 5 frames × 91 features → 1 vector × 546 features

### Step-by-Step Process

1. **Input Validation**:
   ```python
   if len(sequence_data) != 5:
       raise ValueError("Sequence must contain exactly 5 frames")
   ```

2. **DataFrame Creation**:
   ```python
   df = pd.DataFrame(sequence_data)  # Shape: (5, variable)
   ```

3. **Feature Selection**:
   ```python
   # Ensure all 91 expected features exist, fill missing with 0
   df_features = df[frame_feature_cols]  # Shape: (5, 91)
   ```

4. **Type Conversion**:
   ```python
   # Convert to numeric, handle missing values
   df_features = df_features.apply(pd.to_numeric, errors='coerce')
   df_features = df_features.fillna(0)  # Fill NaN with 0
   ```

5. **Aggregation** (per feature, across 5 frames):

   For each of the 6 aggregation functions:

   **a. Mean**:
   ```python
   mean = df_features.mean()  # (91,) - average across 5 frames
   ```

   **b. Standard Deviation**:
   ```python
   std = df_features.std()  # (91,) - variability across frames
   ```

   **c. Delta**:
   ```python
   delta = df_features.iloc[-1] - df_features.iloc[0]  # (91,) - change from first to last
   ```

   **d. Range**:
   ```python
   range_val = df_features.max() - df_features.min()  # (91,) - spread across frames
   ```

   **e. Mean Absolute Velocity**:
   ```python
   # Calculate differences between consecutive frames
   velocities = np.abs(df_features.diff().iloc[1:])  # (4, 91)
   mean_abs_vel = np.mean(velocities, axis=0)  # (91,) - average speed of change
   ```

   **f. Velocity Standard Deviation**:
   ```python
   velocities = df_features.diff().iloc[1:]  # (4, 91)
   vel_std = np.std(velocities, axis=0)  # (91,) - variability of velocity
   ```

6. **Feature Vector Construction**:
   ```python
   # Concatenate all aggregations
   aggregated = [mean, std, delta, range, mean_abs_vel, vel_std]
   feature_vector = np.concatenate(aggregated)  # (546,) = 91 × 6
   ```

### Example Calculation

For a single feature (e.g., `Head_X`) across 5 frames:

```
Frame 1: Head_X = 1.0
Frame 2: Head_X = 1.1
Frame 3: Head_X = 1.2
Frame 4: Head_X = 1.1
Frame 5: Head_X = 1.3

Aggregations:
- mean: (1.0 + 1.1 + 1.2 + 1.1 + 1.3) / 5 = 1.14
- std: 0.114
- delta: 1.3 - 1.0 = 0.3
- range: 1.3 - 1.0 = 0.3
- mean_abs_vel: mean(|0.1|, |0.1|, |-0.1|, |0.2|) = 0.125
- vel_std: std(0.1, 0.1, -0.1, 0.2) = 0.129
```

This is repeated for all 91 features, resulting in 546 aggregated features.

---

## Model Inference

### Preprocessing: `preprocess_input()`

**Location**: `model_server.py`, lines 156-197

**Process**:
1. Validates sequence structure
2. Calls `aggregate_sequence_features()` → produces (1, 546) array
3. Applies StandardScaler (if available):
   ```python
   if scaler is not None:
       X = scaler.transform(X)  # Normalize features
   ```

### Prediction: `/predict` endpoint

**Location**: `model_server.py`, lines 218-278

**Process**:
1. Receives JSON request with sequence
2. Preprocesses input → (1, 546) feature vector
3. Runs model prediction:
   ```python
   prediction = model.predict(X)  # Returns 0 or 1
   ```
4. Gets probabilities (if available):
   ```python
   probabilities = model.predict_proba(X)  # [prob_class_0, prob_class_1]
   ```
5. Returns JSON response:
   ```json
   {
     "prediction": 0,
     "probabilities": [0.95, 0.05],
     "sequence_length": 5
   }
   ```

---

## Data Usage

### Current Test Data

**Fixed Test File**: `gameover_war_data_5fps_p1_01.csv`

- **Source**: Pre-recorded War app session
- **Rows**: ~277 frames
- **Usage**: Creates sequences by sliding window
  - Window size: 5 frames
  - Stride: 1 frame
  - Total sequences: ~272 (277 - 5 + 1)

**Testing Process** (`test_with_real_data.py`):

1. **Load CSV**:
   ```python
   data = load_war_data("gameover_war_data_5fps_p1_01.csv")
   ```

2. **Create Sequences**:
   ```python
   sequences = create_sequences_from_data(data, sequence_length=5, stride=1)
   # Creates overlapping sequences: [0-4], [1-5], [2-6], ...
   ```

3. **Filter by Labels**:
   ```python
   labeled_sequences = [seq for seq in sequences if seq has Temporal label]
   ```

4. **Test Predictions**:
   ```python
   for sequence, label_info in labeled_sequences:
       prediction = server.predict(sequence)
       compare prediction with actual label
   ```

### Can We Use New Data?

**✅ YES!** The server can accept **any new data** as long as it matches the format.

**Options**:

1. **Same CSV format**:
   - Use any War app CSV file with the same column structure
   - Update `test_with_real_data.py` to point to new file:
     ```python
     csv_path = "new_war_data.csv"  # Change this
     ```

2. **Real-time inference**:
   - Send new sequences via API:
     ```bash
     curl -X POST http://localhost:5000/predict \
       -H "Content-Type: application/json" \
       -d @new_sequence.json
     ```

3. **Batch processing**:
   - Modify `test_with_real_data.py` to process multiple CSV files
   - Process data from different sessions/users

**Requirements for New Data**:
- Must have all 91 features from `frame_feature_cols`
- Must provide sequences of exactly 5 frames
- Missing features will be filled with 0.0

---

## API Endpoints

### 1. `GET /health`

**Purpose**: Check server status

**Response**:
```json
{
  "status": "healthy",
  "model_loaded": true,
  "scaler_loaded": true,
  "metadata_loaded": true
}
```

### 2. `GET /info`

**Purpose**: Get model information

**Response**:
```json
{
  "model_type": "<class 'sklearn.linear_model._logistic.LogisticRegression'>",
  "feature_count": 546,
  "expected_sequence_length": 5,
  "expected_frame_features": 91,
  "expected_aggregated_features": 546,
  "aggregation_functions": ["mean", "std", "delta", "range", "mean_abs_vel", "vel_std"]
}
```

### 3. `GET /example`

**Purpose**: Get example request format

**Response**: Example sequence with all 91 features

### 4. `POST /predict`

**Purpose**: Make prediction on a sequence

**Request**:
```json
{
  "sequence": [
    { "Bomb_0_X": 1.0, ... },  // Frame 1
    { "Bomb_0_X": 1.1, ... },  // Frame 2
    { "Bomb_0_X": 1.2, ... },  // Frame 3
    { "Bomb_0_X": 1.1, ... },  // Frame 4
    { "Bomb_0_X": 1.3, ... }   // Frame 5
  ]
}
```

**Response**:
```json
{
  "prediction": 0,
  "probabilities": [0.95, 0.05],
  "sequence_length": 5
}
```

**Label Meaning**:
- `prediction: 0` = No temporal error (correct tracking)
- `prediction: 1` = Temporal error (tracking issue detected)

---

## Summary

### Data Flow Diagram

```
Raw CSV Data (277 frames × 95 cols)
    ↓
Create Sequences (sliding window, stride=1)
    ↓
272 sequences × (5 frames × 91 features)
    ↓
Aggregate Each Sequence
    ↓
272 sequences × 546 aggregated features
    ↓
StandardScaler (if available)
    ↓
Model Inference (Logistic Regression)
    ↓
272 predictions (0 or 1)
    ↓
Compare with Ground Truth Labels
    ↓
Calculate Metrics (Accuracy, Precision, Recall, F1)
```

### Key Points

1. **Fixed vs. New Data**:
   - Current test uses fixed CSV file
   - Server can process ANY new data matching the format
   - No retraining needed for new data

2. **Sequence Processing**:
   - Always uses 5-frame sequences
   - Middle frame (index 2) is the prediction target
   - Aggregation extracts temporal patterns

3. **Model**:
   - Pre-trained Logistic Regression
   - Uses balanced class weights
   - Expected accuracy: ~98.55%

4. **Scalability**:
   - Can process single sequences or batches
   - Real-time inference capable
   - Stateless (no session management needed)

---

## Questions Answered

**Q: Is the experiment using the same data always?**
- **A**: The test script (`test_with_real_data.py`) currently uses a fixed CSV file, but you can easily change it to use different data files or accept new data via API.

**Q: Can we test with new data?**
- **A**: Yes! Update the CSV path in the test script, or send new sequences directly to the `/predict` endpoint.
