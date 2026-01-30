# Quick Start Guide

## Option 1: Automated (Recommended) 🚀

Run everything in one command:

```bash
cd server
./start_server_and_test.sh
```

This will:
- ✅ Check dependencies
- ✅ Start the server on port 5000
- ✅ Run tests with real War data
- ✅ Show actual vs predicted labels
- ✅ Display accuracy metrics
- ✅ Stop the server automatically

---

## Option 2: Manual (Step by Step) 📝

### Step 1: Install Dependencies

```bash
cd server
pip install -r requirements.txt
```

Or install individually:
```bash
pip install flask flask-cors joblib numpy pandas scikit-learn requests
```

### Step 2: Start the Server

In Terminal 1:
```bash
cd server
python3 model_server.py
```

You should see:
```
INFO: Loading model from saved_model/model.joblib...
INFO: Model loaded successfully...
INFO: Server ready!
INFO: Starting server on 0.0.0.0:5000
```

**Keep this terminal open** - the server needs to keep running.

### Step 3: Run Tests

In Terminal 2 (new terminal window):
```bash
cd server
python3 test_with_real_data.py
```

You'll see output like:
```
======================================================================
War App Model Server - Real Data Test
======================================================================

Testing health check...
✅ Server is healthy: {'status': 'healthy', 'model_loaded': True, ...}

Testing 20 sequences...

  1. EntryID: 806202507222... | Actual: 0 | Predicted: 0 | Prob: [0.95, 0.05] | ✅
  2. EntryID: 806202507222... | Actual: 0 | Predicted: 0 | Prob: [0.92, 0.08] | ✅
  ...

======================================================================
SUMMARY
======================================================================
Total tests: 20
Correct predictions: 19 (95.0%)
Incorrect predictions: 1 (5.0%)

Confusion Matrix:
                 Predicted
              0        1
Actual  0    15       1
        1     0       4

Metrics:
  Accuracy:  0.9500
  Precision: 1.0000
  Recall:    1.0000
  F1 Score:  0.8000
```

### Step 4: Stop the Server

When done testing, go back to Terminal 1 and press `Ctrl+C` to stop the server.

---

## Option 3: Test with cURL 🌐

Start the server (see Step 2 above), then in another terminal:

```bash
# Health check
curl http://localhost:5000/health

# Get model info
curl http://localhost:5000/info

# Get example request
curl http://localhost:5000/example

# Make a prediction (using example data)
curl -X POST http://localhost:5000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "sequence": [
      {"Bomb_0_X": -5.9, "Bomb_0_Y": 3.4, "Bomb_0_Z": 0, ...},
      {"Bomb_0_X": -5.9, "Bomb_0_Y": 3.4, "Bomb_0_Z": 0, ...},
      {"Bomb_0_X": -5.9, "Bomb_0_Y": 3.4, "Bomb_0_Z": 0, ...},
      {"Bomb_0_X": -5.9, "Bomb_0_Y": 3.4, "Bomb_0_Z": 0, ...},
      {"Bomb_0_X": -5.9, "Bomb_0_Y": 3.4, "Bomb_0_Z": 0, ...}
    ]
  }'
```

---

## Troubleshooting

### ❌ "ModuleNotFoundError: No module named 'flask'"
**Solution**: Install dependencies
```bash
pip install -r requirements.txt
```

### ❌ "Address already in use"
**Solution**: Port 5000 is already taken. Either:
- Stop the other service using port 5000
- Use a different port: `python3 model_server.py --port 8080`

### ❌ "Model file not found"
**Solution**: Make sure you're in the `server/` directory and `saved_model/model.joblib` exists

### ❌ "Connection refused"
**Solution**: Make sure the server is running. Check Terminal 1 for errors.

### ❌ Server won't start
**Solution**: Check the error message. Common issues:
- Missing `flask_cors` - This is OK, server works without it
- Missing model files - Check `saved_model/` directory
- Python version - Requires Python 3.7+

---

## Testing with New Data

To test with a different CSV file:

1. Edit `test_with_real_data.py` (line ~114):
   ```python
   csv_path = "your_new_data.csv"  # Change this
   ```

2. Run the test script again

---

## Expected Results

Based on the model's cross-validation:
- **Accuracy**: ~98.5%
- **Precision**: ~97.6%
- **Recall**: ~99.1%
- **F1 Score**: ~98.3%

Your actual results may vary slightly depending on the test data.
