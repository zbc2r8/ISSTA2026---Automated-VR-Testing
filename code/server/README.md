# War App Model Server

Self-contained server for running the War app temporal sequence model with real data testing.

## Files

- `model_server.py` - Flask server for model inference
- `test_with_real_data.py` - Test script using actual War data
- `start_server_and_test.sh` - Automated startup and testing script
- `requirements.txt` - Python dependencies
- `saved_model/` - Model files (model.joblib, meta.json)
- `gameover_war_data_5fps_p1_01.csv` - Test data

## Quick Start

### Option 1: Automated (Recommended)

```bash
cd server
./start_server_and_test.sh
```

This will:
1. Check dependencies
2. Start the server
3. Run tests with real data
4. Show actual vs predicted labels
5. Stop the server

### Option 2: Manual

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Start the server:**
```bash
python3 model_server.py
```

3. **In another terminal, run tests:**
```bash
python3 test_with_real_data.py
```

## Model Details

Based on `saved_model/meta.json`:
- **Task**: Temporal sequence prediction
- **Model Type**: Logistic Regression (balanced)
- **Sequence Length**: 5 frames
- **Frame Features**: 91 features per frame
- **Aggregated Features**: 546 features (91 × 6 aggregations)
- **Aggregations**: mean, std, delta, range, mean_abs_vel, vel_std
- **Target**: Temporal label (0 = no error, 1 = error)

### Expected Input Format

The model expects sequences of 5 consecutive frames. Each frame should contain all 91 features from `frame_feature_cols` in `meta.json`:

```json
{
  "sequence": [
    {
      "Bomb_0_X": 1.0, "Bomb_0_Y": 2.0, ...,
      "ElbowL_X": 1.0, "ElbowL_Y": 2.0, ...,
      "Head_X": 1.0, ...,
      ... (all 91 features)
    },
    ... (4 more frames)
  ]
}
```

## API Endpoints

- `GET /health` - Health check
- `GET /info` - Model information
- `GET /example` - Example request format
- `POST /predict` - Make predictions

## Testing

The `test_with_real_data.py` script:
1. Loads actual War data from CSV
2. Creates 5-frame sequences
3. Sends them to the server
4. Compares predictions with actual Temporal labels
5. Shows accuracy, precision, recall, F1 score
6. Displays confusion matrix
7. Shows examples of correct and incorrect predictions

## Expected Performance

Based on the model metadata (5-fold cross-validation):
- **Mean Accuracy**: 98.55%
- **Mean Precision**: 97.57%
- **Mean Recall**: 99.13%
- **Mean F1 Score**: 98.30%

## Troubleshooting

- **Server won't start**: Check if port 5000 is already in use
- **Model not found**: Ensure `saved_model/model.joblib` exists
- **Missing dependencies**: Run `pip install -r requirements.txt`
- **Connection refused**: Wait a few seconds for the server to fully start
- **flask_cors not found**: This is optional. The server will work without it, but CORS will be disabled. Install with `pip install flask-cors` if you need browser-based access.

## Notes

- The server automatically aggregates 5-frame sequences into 546-dimensional feature vectors
- Missing features are filled with 0.0
- If a scaler is available (scaler.joblib), it will be applied automatically
- The model predicts Temporal labels (0 = no error, 1 = error)
