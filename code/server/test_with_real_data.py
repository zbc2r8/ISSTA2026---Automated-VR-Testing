#!/usr/bin/env python3
"""
Test script using actual War data from gameover_war_data_5fps_p1_01.csv
Tests the server with real sequences and shows actual vs predicted labels
"""

import csv
import json
import os
import requests
import time
import sys
from typing import List, Dict, Tuple
from collections import defaultdict

SERVER_URL = "http://localhost:5000"

def load_war_data(csv_path: str) -> List[Dict]:
    """Load War CSV data and convert numeric strings to floats."""
    data = []
    # Define columns that should stay as strings (identifiers and labels)
    string_columns = {'EntryID', 'GlobalID', 'Spatial', 'Temporal', 
                     'Spatial_1', 'Temporal_1', 'Spatial_2', 'Temporal_2'}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            processed_row = {}
            for key, value in row.items():
                if key in string_columns:
                    # Keep identifiers and labels as strings
                    processed_row[key] = value if value else ''
                elif value and value.strip():  # Skip empty strings
                    # Try to convert to float if it looks numeric
                    try:
                        float_val = float(value)
                        processed_row[key] = float_val
                    except (ValueError, TypeError):
                        # Keep as string if conversion fails
                        processed_row[key] = value
                else:
                    # Empty string -> empty string for non-numeric, 0 for numeric will be handled by server
                    processed_row[key] = ''
            data.append(processed_row)
    return data

def create_sequences_from_data(data: List[Dict], sequence_length: int = 5, stride: int = 1) -> List[Tuple[List[Dict], Dict]]:
    """
    Create sequences from data with labels.
    
    Returns:
        List of (sequence, label_info) tuples
        where sequence is a list of frame dictionaries
        and label_info contains the label for the middle frame
    """
    sequences = []
    
    for i in range(0, len(data) - sequence_length + 1, stride):
        sequence = data[i:i + sequence_length]
        
        # Get label from middle frame (index 2)
        middle_frame = sequence[sequence_length // 2]
        label_info = {
            'Temporal': middle_frame.get('Temporal', ''),
            'Spatial': middle_frame.get('Spatial', ''),
            'EntryID': middle_frame.get('EntryID', ''),
            'GlobalID': middle_frame.get('GlobalID', '')
        }
        
        sequences.append((sequence, label_info))
    
    return sequences

def test_health():
    """Test health check endpoint."""
    print("Testing health check...")
    try:
        response = requests.get(f"{SERVER_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"✅ Server is healthy: {response.json()}")
            return True
        else:
            print(f"❌ Server health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        return False

def test_model_info():
    """Test model info endpoint."""
    print("\nGetting model info...")
    try:
        response = requests.get(f"{SERVER_URL}/info", timeout=5)
        if response.status_code == 200:
            info = response.json()
            print(f"✅ Model info retrieved:")
            print(f"   Model type: {info.get('model_type')}")
            print(f"   Expected sequence length: {info.get('expected_sequence_length')}")
            print(f"   Expected frame features: {info.get('expected_frame_features')}")
            print(f"   Expected aggregated features: {info.get('expected_aggregated_features')}")
            print(f"   Aggregation functions: {info.get('aggregation_functions')}")
            return info
        else:
            print(f"❌ Failed to get model info: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error getting model info: {e}")
        return None

def test_prediction(sequence: List[Dict], label_info: Dict) -> Dict:
    """Test a single prediction."""
    try:
        payload = {"sequence": sequence}
        response = requests.post(f"{SERVER_URL}/predict", json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            return {
                'success': True,
                'prediction': result.get('prediction'),
                'probabilities': result.get('probabilities'),
                'actual_temporal': int(label_info.get('Temporal', 0)) if label_info.get('Temporal') else None,
                'actual_spatial': int(label_info.get('Spatial', 0)) if label_info.get('Spatial') else None,
                'entry_id': label_info.get('EntryID', ''),
                'match': result.get('prediction') == int(label_info.get('Temporal', 0)) if label_info.get('Temporal') else None
            }
        else:
            return {
                'success': False,
                'error': f"HTTP {response.status_code}: {response.text}"
            }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def main():
    print("="*70)
    print("War App Model Server - Real Data Test")
    print("="*70)
    
    # Wait for server to be ready
    print("\nWaiting for server to be ready...")
    max_retries = 10
    for i in range(max_retries):
        if test_health():
            break
        if i < max_retries - 1:
            time.sleep(2)
        else:
            print("❌ Server not responding. Please start the server first:")
            print("   python3 model_server.py")
            sys.exit(1)
    
    # Get model info
    model_info = test_model_info()
    if not model_info:
        print("❌ Failed to get model info")
        sys.exit(1)
    
    # Load test data
    csv_path = "gameover_war_data_5fps_p1_01.csv"
    if not os.path.exists(csv_path):
        print(f"❌ Test data file not found: {csv_path}")
        sys.exit(1)
    
    print(f"\nLoading test data from {csv_path}...")
    data = load_war_data(csv_path)
    print(f"✅ Loaded {len(data)} rows")
    
    # Create sequences
    print("\nCreating sequences (5 frames each)...")
    sequences = create_sequences_from_data(data, sequence_length=5, stride=1)
    print(f"✅ Created {len(sequences)} sequences")
    
    # Filter to only sequences with Temporal labels
    labeled_sequences = [(seq, label) for seq, label in sequences 
                        if label.get('Temporal') and label.get('Temporal') != '']
    print(f"✅ {len(labeled_sequences)} sequences have Temporal labels")
    
    if len(labeled_sequences) == 0:
        print("❌ No sequences with Temporal labels found")
        sys.exit(1)
    
    # Test predictions
    print(f"\n{'='*70}")
    print("Testing predictions with actual data...")
    print(f"{'='*70}")
    
    results = []
    num_tests = min(20, len(labeled_sequences))  # Test first 20 sequences
    
    print(f"\nTesting {num_tests} sequences...\n")
    
    for i, (sequence, label_info) in enumerate(labeled_sequences[:num_tests], 1):
        result = test_prediction(sequence, label_info)
        
        if result['success']:
            actual = result['actual_temporal']
            predicted = result['prediction']
            match = "✅" if result['match'] else "❌"
            prob = result.get('probabilities', [None, None])
            prob_str = f"[{prob[0]:.3f}, {prob[1]:.3f}]" if prob[0] is not None else "N/A"
            
            # Safely handle EntryID (may be string, float, or None)
            entry_id = label_info.get('EntryID', 'N/A')
            if entry_id is None:
                entry_id = 'N/A'
            else:
                entry_id = str(entry_id)
            entry_id_str = entry_id[:15] + "..." if len(entry_id) > 15 else entry_id
            
            print(f"{i:3d}. EntryID: {entry_id_str} | "
                  f"Actual: {actual} | Predicted: {predicted} | "
                  f"Prob: {prob_str} | {match}")
            
            results.append(result)
        else:
            print(f"{i:3d}. ❌ Error: {result.get('error', 'Unknown error')}")
            results.append(result)
        
        # Small delay to avoid overwhelming server
        time.sleep(0.1)
    
    # Summary statistics
    successful_results = [r for r in results if r.get('success')]
    if successful_results:
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        
        matches = sum(1 for r in successful_results if r.get('match') is True)
        mismatches = sum(1 for r in successful_results if r.get('match') is False)
        total = len(successful_results)
        
        print(f"Total tests: {total}")
        print(f"Correct predictions: {matches} ({matches/total*100:.1f}%)")
        print(f"Incorrect predictions: {mismatches} ({mismatches/total*100:.1f}%)")
        
        # Confusion matrix
        actual_pred = [(r['actual_temporal'], r['prediction']) 
                      for r in successful_results if r.get('actual_temporal') is not None]
        
        tp = sum(1 for a, p in actual_pred if a == 1 and p == 1)
        tn = sum(1 for a, p in actual_pred if a == 0 and p == 0)
        fp = sum(1 for a, p in actual_pred if a == 0 and p == 1)
        fn = sum(1 for a, p in actual_pred if a == 1 and p == 0)
        
        print(f"\nConfusion Matrix:")
        print(f"                 Predicted")
        print(f"              0        1")
        print(f"Actual  0   {tn:4d}    {fp:4d}")
        print(f"        1   {fn:4d}    {tp:4d}")
        
        if total > 0:
            accuracy = (tp + tn) / total
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            print(f"\nMetrics:")
            print(f"  Accuracy:  {accuracy:.4f}")
            print(f"  Precision: {precision:.4f}")
            print(f"  Recall:    {recall:.4f}")
            print(f"  F1 Score:  {f1:.4f}")
        
        # Show some examples of correct and incorrect predictions
        print(f"\n{'='*70}")
        print("Sample Results:")
        print(f"{'='*70}")
        
        correct_examples = [r for r in successful_results if r.get('match') is True][:3]
        incorrect_examples = [r for r in successful_results if r.get('match') is False][:3]
        
        if correct_examples:
            print("\n✅ Correct Predictions:")
            for r in correct_examples:
                entry_id = str(r['entry_id'])[:15] if r['entry_id'] else 'N/A'
                entry_id_str = entry_id + "..." if len(entry_id) == 15 else entry_id
                print(f"   EntryID: {entry_id_str} | "
                      f"Actual: {r['actual_temporal']}, Predicted: {r['prediction']}, "
                      f"Prob: {r.get('probabilities', [None, None])}")
        
        if incorrect_examples:
            print("\n❌ Incorrect Predictions:")
            for r in incorrect_examples:
                entry_id = str(r['entry_id'])[:15] if r['entry_id'] else 'N/A'
                entry_id_str = entry_id + "..." if len(entry_id) == 15 else entry_id
                print(f"   EntryID: {entry_id_str} | "
                      f"Actual: {r['actual_temporal']}, Predicted: {r['prediction']}, "
                      f"Prob: {r.get('probabilities', [None, None])}")
    else:
        print("\n❌ No successful predictions to summarize")
    
    print(f"\n{'='*70}")
    print("Test completed!")
    print(f"{'='*70}")

if __name__ == '__main__':
    import os
    main()
