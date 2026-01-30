#!/usr/bin/env python3
"""
Extract metrics from ALL data files for each app, keeping only rows with Spatial/Temporal labels
"""

import csv
import os
import math
from typing import Optional, Tuple, Dict

# Joint mappings
APP_JOINTS = {
    "Archery": {
        "head": "joint_Head",
        "spinebase": "joint_Pelvis",
        "r_elbow": "joint_ElbowRT",
        "r_hand": "joint_HandRT",
        "r_knee": "joint_KneeRT",
        "r_foot": "joint_FootRT",
        "l_elbow": "joint_ElbowLT",
        "l_hand": "joint_HandLT",
        "l_knee": "joint_KneeLT",
        "l_foot": "joint_FootLT",
    },
    "Puzzle": {
        "head": "Head",
        "spinebase": "SpineBase",
        "r_elbow": "ElbowRight",
        "r_hand": "HandRight",
        "r_knee": "KneeRight",
        "r_foot": "FootRight",
        "l_elbow": "ElbowLeft",
        "l_hand": "HandLeft",
        "l_knee": "KneeLeft",
        "l_foot": "FootLeft",
    },
    "Sea": {
        "head": "Head",
        "spinebase": "SpineBase",
        "r_elbow": "ElbowR",
        "r_hand": "HandR",
        "r_knee": "KneeR",
        "r_foot": "FootR",
        "l_elbow": "ElbowL",
        "l_hand": "HandL",
        "l_knee": "KneeL",
        "l_foot": "FootL",
    },
    "War": {
        "head": "Head",
        "spinebase": "SpineBase",
        "r_elbow": "ElbowR",
        "r_hand": "HandR",
        "r_knee": "KneeR",
        "r_foot": "FootR",
        "l_elbow": "ElbowL",
        "l_hand": "HandL",
        "l_knee": "KneeL",
        "l_foot": "FootL",
    },
    "PhantomLimb": {
        "head": "Skeleton0",
        "spinebase": "Skeleton7",
        "r_elbow": "Skeleton9",
        "r_hand": "Skeleton11",
        "r_knee": "Skeleton19",
        "r_foot": "Skeleton20",
        "l_elbow": "Skeleton14",
        "l_hand": "Skeleton16",
        "l_knee": "Skeleton22",
        "l_foot": "Skeleton23",
    },
    "PianoTiles": {
        "head": "Skeleton0",
        "spinebase": "Skeleton7",
        "r_elbow": "Skeleton9",
        "r_hand": "Skeleton11",
        "r_knee": "Skeleton19",
        "r_foot": "Skeleton20",
        "l_elbow": "Skeleton14",
        "l_hand": "Skeleton16",
        "l_knee": "Skeleton22",
        "l_foot": "Skeleton23",
    },
}

def safe_float(val):
    """Safely convert to float."""
    if val is None or val == '' or val == 'nan':
        return None
    try:
        fval = float(val)
        if abs(fval) > 1000:
            return None
        return fval
    except (ValueError, TypeError):
        return None

def get_joint_pos(row, joint_name, app_name):
    """Get joint position."""
    mapping = APP_JOINTS.get(app_name, {})
    base = mapping.get(joint_name)
    if not base:
        return None
    
    x = safe_float(row.get(f"{base}_X"))
    y = safe_float(row.get(f"{base}_Y"))
    z = safe_float(row.get(f"{base}_Z"))
    
    if x is None or y is None or z is None:
        return None
    return (x, y, z)

def distance(p1, p2):
    """Calculate distance."""
    if p1 is None or p2 is None:
        return None
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))

def extract_metrics_row(row, app_name):
    """Extract metrics for one row."""
    metrics = {}
    
    # Get all joints
    joints = {}
    joint_names = ["head", "spinebase", "r_elbow", "r_hand", "r_knee", "r_foot",
                   "l_elbow", "l_hand", "l_knee", "l_foot"]
    
    for joint_name in joint_names:
        joints[joint_name] = get_joint_pos(row, joint_name, app_name)
    
    all_positions = [p for p in joints.values() if p is not None]
    
    # Missing joints
    missing = sum(1 for p in joints.values() if p is None)
    metrics['missing_joints_count'] = missing
    metrics['missing_joints_ratio'] = missing / 10.0
    
    # Collapsed joints
    collapsed = 0
    pos_list = list(all_positions)
    for i, p1 in enumerate(pos_list):
        for p2 in pos_list[i+1:]:
            d = distance(p1, p2)
            if d is not None and d < 0.01:
                collapsed += 1
    metrics['collapsed_joints_count'] = collapsed
    
    # Center of mass
    if all_positions:
        n = len(all_positions)
        com = (
            sum(p[0] for p in all_positions) / n,
            sum(p[1] for p in all_positions) / n,
            sum(p[2] for p in all_positions) / n
        )
        metrics['center_of_mass_x'] = com[0]
        metrics['center_of_mass_y'] = com[1]
        metrics['center_of_mass_z'] = com[2]
        metrics['distance_from_origin'] = math.sqrt(sum(c**2 for c in com))
    else:
        metrics['center_of_mass_x'] = ''
        metrics['center_of_mass_y'] = ''
        metrics['center_of_mass_z'] = ''
        metrics['distance_from_origin'] = ''
    
    # Bounding box
    if all_positions:
        xs = [p[0] for p in all_positions]
        ys = [p[1] for p in all_positions]
        zs = [p[2] for p in all_positions]
        metrics['bbox_width'] = max(xs) - min(xs)
        metrics['bbox_height'] = max(ys) - min(ys)
        metrics['bbox_depth'] = max(zs) - min(zs)
        metrics['bbox_volume'] = metrics['bbox_width'] * metrics['bbox_height'] * metrics['bbox_depth']
    else:
        metrics['bbox_width'] = ''
        metrics['bbox_height'] = ''
        metrics['bbox_depth'] = ''
        metrics['bbox_volume'] = ''
    
    # Max distance from COM
    if all_positions and metrics.get('center_of_mass_x') != '':
        com = (metrics['center_of_mass_x'], metrics['center_of_mass_y'], metrics['center_of_mass_z'])
        max_dist = max((distance(p, com) or 0) for p in all_positions)
        metrics['max_joint_distance_from_com'] = max_dist if max_dist > 0 else ''
    else:
        metrics['max_joint_distance_from_com'] = ''
    
    # Floor (COM-based)
    floor_y = None
    for floor_name in ['Floor_Y', 'Ground_Y', 'Raft_Y']:
        if floor_name in row:
            floor_y = safe_float(row[floor_name])
            if floor_y is not None:
                break
    
    if floor_y is not None and metrics.get('center_of_mass_y') != '':
        metrics['distance_from_floor'] = abs(metrics['center_of_mass_y'] - floor_y)
    else:
        metrics['distance_from_floor'] = ''
    
    # Feet-based floor penetration
    if floor_y is not None:
        foot_heights = []
        if joints.get('l_foot'):
            foot_heights.append(joints['l_foot'][1])
        if joints.get('r_foot'):
            foot_heights.append(joints['r_foot'][1])
        
        if foot_heights:
            min_foot_y = min(foot_heights)
            metrics['min_foot_height_above_floor'] = abs(min_foot_y - floor_y)
            metrics['below_floor'] = 'True' if min_foot_y < floor_y else 'False'
        else:
            # Both feet missing
            metrics['min_foot_height_above_floor'] = ''
            metrics['below_floor'] = ''
    else:
        metrics['min_foot_height_above_floor'] = ''
        metrics['below_floor'] = ''
    
    # Limb lengths
    if joints['l_elbow'] and joints['l_hand']:
        metrics['left_forearm_length'] = distance(joints['l_elbow'], joints['l_hand'])
    else:
        metrics['left_forearm_length'] = ''
    
    if joints['r_elbow'] and joints['r_hand']:
        metrics['right_forearm_length'] = distance(joints['r_elbow'], joints['r_hand'])
    else:
        metrics['right_forearm_length'] = ''
    
    if joints['l_knee'] and joints['l_foot']:
        metrics['left_shin_length'] = distance(joints['l_knee'], joints['l_foot'])
    else:
        metrics['left_shin_length'] = ''
    
    if joints['r_knee'] and joints['r_foot']:
        metrics['right_shin_length'] = distance(joints['r_knee'], joints['r_foot'])
    else:
        metrics['right_shin_length'] = ''
    
    # Symmetry
    if metrics.get('left_forearm_length') != '' and metrics.get('right_forearm_length') != '':
        metrics['arm_length_symmetry'] = abs(metrics['left_forearm_length'] - metrics['right_forearm_length'])
    else:
        metrics['arm_length_symmetry'] = ''
    
    if metrics.get('left_shin_length') != '' and metrics.get('right_shin_length') != '':
        metrics['leg_length_symmetry'] = abs(metrics['left_shin_length'] - metrics['right_shin_length'])
    else:
        metrics['leg_length_symmetry'] = ''
    
    # Body upright orientation (head - spinebase)
    if joints.get('head') and joints.get('spinebase'):
        vec = (
            joints['head'][0] - joints['spinebase'][0],
            joints['head'][1] - joints['spinebase'][1],
            joints['head'][2] - joints['spinebase'][2]
        )
        length = math.sqrt(sum(c**2 for c in vec))
        if length > 0:
            metrics['body_upright_x'] = vec[0] / length
            metrics['body_upright_y'] = vec[1] / length
            metrics['body_upright_z'] = vec[2] / length
        else:
            metrics['body_upright_x'] = ''
            metrics['body_upright_y'] = ''
            metrics['body_upright_z'] = ''
    else:
        metrics['body_upright_x'] = ''
        metrics['body_upright_y'] = ''
        metrics['body_upright_z'] = ''
    
    # Body forward direction (hand_mid - spinebase, projected to horizontal plane)
    if joints.get('spinebase'):
        # Get hand positions (use one if the other is missing)
        hand_positions = []
        if joints.get('l_hand'):
            hand_positions.append(joints['l_hand'])
        if joints.get('r_hand'):
            hand_positions.append(joints['r_hand'])
        
        if hand_positions:
            # Compute hand midpoint
            hand_mid = (
                sum(h[0] for h in hand_positions) / len(hand_positions),
                sum(h[1] for h in hand_positions) / len(hand_positions),
                sum(h[2] for h in hand_positions) / len(hand_positions)
            )
            
            # Vector from spinebase to hand_mid
            raw_forward = (
                hand_mid[0] - joints['spinebase'][0],
                0.0,  # Project to horizontal plane (Y = 0)
                hand_mid[2] - joints['spinebase'][2]
            )
            
            length = math.sqrt(sum(c**2 for c in raw_forward))
            if length > 0:
                metrics['body_forward_x'] = raw_forward[0] / length
                metrics['body_forward_y'] = raw_forward[1] / length
                metrics['body_forward_z'] = raw_forward[2] / length
            else:
                metrics['body_forward_x'] = ''
                metrics['body_forward_y'] = ''
                metrics['body_forward_z'] = ''
        else:
            # Both hands missing
            metrics['body_forward_x'] = ''
            metrics['body_forward_y'] = ''
            metrics['body_forward_z'] = ''
    else:
        metrics['body_forward_x'] = ''
        metrics['body_forward_y'] = ''
        metrics['body_forward_z'] = ''
    
    return metrics

def process_all_data_files(app_name: str, base_dir: str):
    """Process ALL data files for an app and extract metrics for rows with labels."""
    data_dir = os.path.join(base_dir, "data", app_name)
    
    if not os.path.exists(data_dir):
        print(f"  ⚠️ Data directory not found: {data_dir}")
        return []
    
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    if not csv_files:
        print(f"  ⚠️ No CSV files found in {data_dir}")
        return []
    
    print(f"  Processing {len(csv_files)} CSV file(s)...")
    
    all_metrics = []
    
    for csv_file in csv_files:
        csv_path = os.path.join(data_dir, csv_file)
        print(f"    Processing {csv_file}...")
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                if 'EntryID' not in reader.fieldnames:
                    print(f"      ⚠️ No EntryID column, skipping")
                    continue
                
                if 'Spatial' not in reader.fieldnames or 'Temporal' not in reader.fieldnames:
                    print(f"      ⚠️ No Spatial/Temporal columns, skipping")
                    continue
                
                file_count = 0
                skipped_count = 0
                
                for row in reader:
                    spatial = row.get('Spatial', '').strip()
                    temporal = row.get('Temporal', '').strip()
                    
                    # Only process rows that have BOTH Spatial and Temporal labels
                    if spatial == '' or temporal == '':
                        skipped_count += 1
                        continue
                    
                    # Extract metrics
                    metrics = extract_metrics_row(row, app_name)
                    
                    # Add identifiers
                    if 'GlobalID' in row:
                        metrics['GlobalID'] = row['GlobalID']
                    metrics['EntryID'] = row['EntryID']
                    metrics['Spatial'] = spatial
                    metrics['Temporal'] = temporal
                    metrics['App'] = app_name
                    
                    all_metrics.append(metrics)
                    file_count += 1
                    
                    if file_count % 500 == 0:
                        print(f"      Processed {file_count} rows...")
                
                print(f"      ✅ Extracted {file_count} rows (skipped {skipped_count} without labels)")
        
        except Exception as e:
            print(f"      ❌ Error processing {csv_file}: {e}")
            import traceback
            traceback.print_exc()
    
    return all_metrics

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    metrics_dir = os.path.join(base_dir, "metrics")
    
    apps = ["Archery", "Puzzle", "Sea", "War", "PhantomLimb", "PianoTiles"]
    
    print("="*70)
    print("EXTRACTING METRICS FROM ALL DATA FILES")
    print("(Keeping only rows with Spatial and Temporal labels)")
    print("="*70)
    
    metric_cols = [
        'missing_joints_count', 'missing_joints_ratio', 'collapsed_joints_count',
        'center_of_mass_x', 'center_of_mass_y', 'center_of_mass_z',
        'distance_from_origin', 'bbox_width', 'bbox_height', 'bbox_depth', 'bbox_volume',
        'max_joint_distance_from_com', 'distance_from_floor', 'min_foot_height_above_floor', 'below_floor',
        'left_forearm_length', 'right_forearm_length', 'left_shin_length', 'right_shin_length',
        'arm_length_symmetry', 'leg_length_symmetry',
        'body_upright_x', 'body_upright_y', 'body_upright_z',
        'body_forward_x', 'body_forward_y', 'body_forward_z'
    ]
    
    all_app_metrics = {}
    
    for app in apps:
        print(f"\n{'='*70}")
        print(f"Processing {app}")
        print(f"{'='*70}")
        
        metrics_list = process_all_data_files(app, base_dir)
        
        if metrics_list:
            # Save to metrics file
            output_path = os.path.join(metrics_dir, f"metrics_{app}.csv")
            
            # Determine fieldnames
            fieldnames = []
            if metrics_list[0].get('GlobalID'):
                fieldnames.append('GlobalID')
            fieldnames.extend(['EntryID', 'Spatial', 'Temporal', 'App'])
            fieldnames.extend(metric_cols)
            
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(metrics_list)
            
            print(f"\n  ✅ Saved {len(metrics_list)} rows to {output_path}")
            all_app_metrics[app] = metrics_list
        else:
            print(f"  ⚠️ No metrics extracted for {app}")
    
    # Update combined file
    if all_app_metrics:
        print(f"\n{'='*70}")
        print("Updating combined metrics file...")
        print(f"{'='*70}")
        
        # Also include PhantomLimb and PianoTiles
        for app in ["PhantomLimb", "PianoTiles"]:
            metrics_path = os.path.join(metrics_dir, f"metrics_{app}.csv")
            if os.path.exists(metrics_path):
                with open(metrics_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    all_app_metrics[app] = list(reader)
        
        # Combine all
        all_rows = []
        fieldnames = None
        
        for app in ["Archery", "Puzzle", "Sea", "War", "PhantomLimb", "PianoTiles"]:
            if app in all_app_metrics:
                rows = all_app_metrics[app]
                if rows:
                    if fieldnames is None:
                        fieldnames = list(rows[0].keys())
                    all_rows.extend(rows)
        
        if all_rows and fieldnames:
            combined_path = os.path.join(base_dir, "extracted_metrics_all_apps.csv")
            with open(combined_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            
            print(f"✅ Updated combined file: {combined_path}")
            print(f"   Total rows: {len(all_rows)}")
            
            # Count by app
            apps_count = {}
            for row in all_rows:
                app = row.get('App', 'Unknown')
                apps_count[app] = apps_count.get(app, 0) + 1
            
            print(f"\n   Rows per app:")
            for app in sorted(apps_count.keys()):
                print(f"     {app}: {apps_count[app]} rows")

if __name__ == "__main__":
    main()
