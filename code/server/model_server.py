#!/usr/bin/env python3
"""
Python Server for War App Model Inference

This server loads a trained model and provides REST API endpoints for inference.
It expects sequence data (5 frames) with 91 features per frame, which are aggregated
into 546 features according to the training pipeline specifications.
"""

import os
import sys
import json
import joblib
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify
from typing import Dict, List, Optional
import logging

# Try to import flask_cors, make it optional
try:
    from flask_cors import CORS
    CORS_AVAILABLE = True
except ImportError:
    CORS_AVAILABLE = False
    logging.warning("flask_cors not available. CORS will be disabled. Install with: pip install flask-cors")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
if CORS_AVAILABLE:
    CORS(app)  # Enable CORS for all routes

# Global variables for model and metadata
model = None
scaler = None
feature_names = None
model_meta = None

def load_model(model_dir: str = "saved_model"):
    """Load the model and metadata."""
    global model, scaler, feature_names, model_meta
    
    model_path = os.path.join(model_dir, "model.joblib")
    meta_path = os.path.join(model_dir, "meta.json")
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model file not found: {model_path}")
    
    logger.info(f"Loading model from {model_path}...")
    try:
        model = joblib.load(model_path)
        logger.info(f"Model loaded successfully. Type: {type(model)}")
        
        # Try to get feature names from model
        if hasattr(model, 'feature_names_in_'):
            feature_names = list(model.feature_names_in_)
            logger.info(f"Model expects {len(feature_names)} features")
        elif hasattr(model, 'n_features_in_'):
            logger.info(f"Model expects {model.n_features_in_} features")
        
        # Load metadata
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                model_meta = json.load(f)
            logger.info(f"Loaded metadata: {json.dumps(model_meta, indent=2)}")
            
            # Check if scaler is in metadata or same directory
            scaler_path = os.path.join(model_dir, "scaler.joblib")
            if 'scaler_path' in model_meta:
                scaler_path = model_meta['scaler_path']
                if not os.path.isabs(scaler_path):
                    scaler_path = os.path.join(model_dir, scaler_path)
            
            if os.path.exists(scaler_path):
                scaler = joblib.load(scaler_path)
                logger.info("Scaler loaded successfully")
            else:
                logger.warning(f"Scaler not found at {scaler_path}, will skip scaling")
        
        return True
    except Exception as e:
        logger.error(f"Error loading model: {e}", exc_info=True)
        raise

def aggregate_sequence_features(sequence_data: List[Dict], agg_functions: List[str], frame_feature_cols: List[str]) -> np.ndarray:
    """
    Aggregate sequence features according to training specifications.
    
    Args:
        sequence_data: List of 5 frame dictionaries
        agg_functions: List of aggregation functions to apply (e.g., ['mean', 'std', 'delta', 'range', 'mean_abs_vel', 'vel_std'])
        frame_feature_cols: List of feature column names expected in each frame (91 features)
    
    Returns:
        Aggregated feature vector (546 dimensions for 91 features * 6 aggregations)
    """
    if len(sequence_data) != 5:
        raise ValueError(f"Sequence must contain exactly 5 frames, got {len(sequence_data)}")
    
    # Convert sequence to DataFrame
    df = pd.DataFrame(sequence_data)
    
    # Ensure all required columns exist, fill missing with 0
    for col in frame_feature_cols:
        if col not in df.columns:
            df[col] = 0.0
    
    # Select only frame features in correct order
    df_features = df[frame_feature_cols].copy()
    
    # Convert to numeric, handling missing values and string inputs
    # This is critical because CSV values arrive as strings
    for col in df_features.columns:
        if col in df_features.columns:
            # Convert to numeric, coercing errors (strings, empty, etc.) to NaN
            df_features[col] = pd.to_numeric(df_features[col], errors='coerce')
    
    # Fill NaN with 0 (handles missing, empty strings, invalid values)
    df_features = df_features.fillna(0)
    
    # Ensure all values are actually numeric (float64)
    df_features = df_features.astype(float)
    
    # Calculate aggregations
    aggregated_features = []
    
    for agg_func in agg_functions:
        if agg_func == 'mean':
            agg_features = df_features.mean().values
        elif agg_func == 'std':
            agg_features = df_features.std().values
            agg_features = np.nan_to_num(agg_features, nan=0.0)
        elif agg_func == 'delta':
            # Difference between last and first frame
            if len(df_features) > 1:
                agg_features = (df_features.iloc[-1] - df_features.iloc[0]).values
            else:
                agg_features = np.zeros(len(frame_feature_cols))
        elif agg_func == 'range':
            # Range (max - min) for each feature
            agg_features = (df_features.max() - df_features.min()).values
        elif agg_func == 'mean_abs_vel':
            # Mean absolute velocity (average of absolute differences between consecutive frames)
            if len(df_features) > 1:
                velocities = np.abs(df_features.diff().iloc[1:]).values
                agg_features = np.mean(velocities, axis=0)
            else:
                agg_features = np.zeros(len(frame_feature_cols))
        elif agg_func == 'vel_std':
            # Standard deviation of velocities
            if len(df_features) > 1:
                velocities = df_features.diff().iloc[1:].values
                agg_features = np.std(velocities, axis=0)
                agg_features = np.nan_to_num(agg_features, nan=0.0)
            else:
                agg_features = np.zeros(len(frame_feature_cols))
        else:
            raise ValueError(f"Unknown aggregation function: {agg_func}")
        
        aggregated_features.extend(agg_features)
    
    return np.array(aggregated_features).reshape(1, -1)

def preprocess_input(data: Dict) -> np.ndarray:
    """
    Preprocess input data to match model expectations.
    
    The model expects sequence-based features:
    - 5 consecutive frames
    - Each frame has 91 features (from frame_feature_cols in meta.json)
    - These are aggregated into a single 546-dimensional feature vector
    
    Args:
        data: Dictionary containing:
              - "sequence": list of 5 frame dictionaries with frame_feature_cols
    
    Returns:
        numpy array ready for model prediction
    """
    global model_meta
    
    if model_meta is None:
        raise ValueError("Model metadata not loaded")
    
    # Check if this is a sequence-based input
    if 'sequence' not in data:
        raise ValueError('Request must contain "sequence" key with list of 5 frames')
    
    sequence = data['sequence']
    if not isinstance(sequence, list) or len(sequence) != 5:
        raise ValueError(f"Sequence must be a list of exactly 5 frames, got {len(sequence) if isinstance(sequence, list) else type(sequence)}")
    
    agg_functions = model_meta.get('agg_use', ['mean', 'std', 'delta', 'range', 'mean_abs_vel', 'vel_std'])
    frame_feature_cols = model_meta.get('frame_feature_cols', [])
    
    if not frame_feature_cols:
        raise ValueError("frame_feature_cols not found in model metadata")
    
    X = aggregate_sequence_features(sequence, agg_functions, frame_feature_cols)
    
    # Apply scaler if available
    if scaler is not None:
        X = scaler.transform(X)
    
    return X

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'model_loaded': model is not None,
        'scaler_loaded': scaler is not None,
        'metadata_loaded': model_meta is not None
    })

@app.route('/predict', methods=['POST'])
def predict():
    """
    Predict endpoint that accepts sequence data.
    
    Expected JSON format:
    {
        "sequence": [
            {"Bomb_0_X": 1.0, "Bomb_0_Y": 2.0, ..., "EntryID": "..."},
            ... (5 frames total)
        ]
    }
    
    Returns:
    {
        "prediction": 0 or 1,
        "probabilities": [prob_class_0, prob_class_1],
        "sequence_length": 5
    }
    """
    if model is None:
        return jsonify({'error': 'Model not loaded'}), 500
    
    try:
        data = request.json
        
        if not data:
            return jsonify({'error': 'Empty request body'}), 400
        
        # Handle sequence-based input
        if 'sequence' not in data:
            return jsonify({'error': 'Request must contain "sequence" key'}), 400
        
        sequence = data['sequence']
        if not isinstance(sequence, list):
            return jsonify({'error': 'Sequence must be a list'}), 400
        
        if len(sequence) != 5:
            return jsonify({'error': f'Sequence must contain exactly 5 frames, got {len(sequence)}'}), 400
        
        X = preprocess_input({'sequence': sequence})
        predictions = model.predict(X)
        probabilities = None
        
        # Get probabilities if available
        if hasattr(model, 'predict_proba'):
            probabilities = model.predict_proba(X).tolist()
        elif hasattr(model, 'predict_log_proba'):
            proba = np.exp(model.predict_log_proba(X))
            probabilities = proba.tolist()
        
        result = {
            'prediction': int(predictions[0]) if len(predictions.shape) == 0 else int(predictions[0]),
            'probabilities': probabilities[0] if probabilities else None,
            'sequence_length': len(sequence)
        }
        
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/info', methods=['GET'])
def model_info():
    """Get information about the loaded model."""
    if model is None:
        return jsonify({'error': 'Model not loaded'}), 500
    
    info = {
        'model_type': str(type(model)),
        'feature_count': getattr(model, 'n_features_in_', None),
        'feature_names': feature_names,
        'metadata': model_meta,
        'expected_sequence_length': model_meta.get('seq_len', 5) if model_meta else None,
        'expected_frame_features': len(model_meta.get('frame_feature_cols', [])) if model_meta else None,
        'expected_aggregated_features': model_meta.get('seq_feature_dim', None) if model_meta else None,
        'aggregation_functions': model_meta.get('agg_use', []) if model_meta else []
    }
    
    return jsonify(info)

@app.route('/example', methods=['GET'])
def example_request():
    """Return an example request format."""
    if model_meta is None:
        return jsonify({'error': 'Model metadata not loaded'}), 500
    
    frame_feature_cols = model_meta.get('frame_feature_cols', [])
    
    # Create example frame with all required features set to 0
    example_frame = {col: 0.0 for col in frame_feature_cols}
    
    # Set some example values for a few features
    if 'Head_X' in example_frame:
        example_frame['Head_X'] = 1.0
        example_frame['Head_Y'] = 2.0
        example_frame['Head_Z'] = 3.0
    if 'SpineBase_X' in example_frame:
        example_frame['SpineBase_X'] = 1.0
        example_frame['SpineBase_Y'] = 1.5
        example_frame['SpineBase_Z'] = 3.0
    
    # Create example sequence (5 frames with slight variation)
    example_sequence = [example_frame.copy() for _ in range(5)]
    for i, frame in enumerate(example_sequence):
        for col in frame_feature_cols:
            if '_X' in col or '_Y' in col or '_Z' in col:
                frame[col] = frame.get(col, 0.0) + i * 0.1
    
    return jsonify({
        'example_request': {
            'sequence': example_sequence
        },
        'expected_sequence_length': 5,
        'expected_frame_features': len(frame_feature_cols),
        'aggregation_functions': model_meta.get('agg_use', [])
    })

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='War App Model Inference Server')
    parser.add_argument('--model-dir', type=str, default='saved_model',
                        help='Directory containing the model files')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000,
                        help='Port to bind to')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Load model
    try:
        load_model(args.model_dir)
        logger.info("Server ready!")
        logger.info(f"Starting server on {args.host}:{args.port}")
        app.run(host=args.host, port=args.port, debug=args.debug)
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        sys.exit(1)
