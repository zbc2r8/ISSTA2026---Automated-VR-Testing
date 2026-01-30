#!/usr/bin/env python3
"""
Add floor information to PhantomLimb and PianoTiles metrics files
by matching EntryIDs with data files that contain Floor_X, Floor_Y, Floor_Z
"""

import csv
import os
import math
from datetime import datetime
from typing import Dict, Optional, Tuple

def normalize_entryid(entryid: str) -> str:
    """Normalize EntryID for matching."""
    if not entryid or entryid == '':
        return ''
    
    # Try to parse as datetime and convert to numeric format
    try:
        for fmt in [
            "%m/%d/%Y %H:%M:%S.%f",
            "%m/%d/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
        ]:
            try:
                dt = datetime.strptime(entryid, fmt)
                return dt.strftime("%m%d%Y%H%M%S%f")[:17]
            except ValueError:
                continue
    except:
        pass
    
    return str(entryid).strip()

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

def load_floor_data_from_csv(app_name: str, base_dir: str) -> Dict[str, Tuple[float, float, float]]:
    """Load floor positions from CSV data files."""
    floor_dict = {}
    
    if app_name == "PhantomLimb":
        data_dir = os.path.join(base_dir, "data", "PhantomLimb")
    elif app_name == "PianoTiles":
        data_dir = os.path.join(base_dir, "data", "PianoTiles")
    else:
        return floor_dict
    
    if not os.path.exists(data_dir):
        print(f"  ⚠️ Data directory not found: {data_dir}")
        return floor_dict
    
    csv_files = [f for f in os.listdir(data_dir) if f.endswith('.csv')]
    
    print(f"  Loading floor data from {len(csv_files)} CSV file(s)...")
    
    for csv_file in csv_files:
        csv_path = os.path.join(data_dir, csv_file)
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                if 'EntryID' not in reader.fieldnames:
                    continue
                
                if 'Floor_X' not in reader.fieldnames or 'Floor_Y' not in reader.fieldnames:
                    continue
                
                count = 0
                for row in reader:
                    entryid = row.get('EntryID', '').strip()
                    if entryid:
                        floor_x = safe_float(row.get('Floor_X'))
                        floor_y = safe_float(row.get('Floor_Y'))
                        floor_z = safe_float(row.get('Floor_Z'))
                        
                        if floor_x is not None and floor_y is not None:
                            # Store both original and normalized EntryID
                            floor_dict[entryid] = (floor_x, floor_y, floor_z)
                            normalized = normalize_entryid(entryid)
                            if normalized != entryid:
                                floor_dict[normalized] = (floor_x, floor_y, floor_z)
                            
                            count += 1
                
                print(f"    ✅ {csv_file}: Loaded {count} floor entries")
        
        except Exception as e:
            print(f"    ❌ Error reading {csv_file}: {e}")
    
    return floor_dict

def add_floor_to_metrics_file(metrics_path: str, floor_dict: Dict[str, Tuple[float, float, float]], app_name: str):
    """Add floor information to metrics file."""
    print(f"\n  Processing {os.path.basename(metrics_path)}...")
    
    if not os.path.exists(metrics_path):
        print(f"    ⚠️ Metrics file not found: {metrics_path}")
        return False
    
    try:
        rows = []
        fieldnames = None
        updated_count = 0
        
        with open(metrics_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames)
            
            for row in reader:
                entryid = row.get('EntryID', '').strip()
                
                # Get current COM
                com_x = safe_float(row.get('center_of_mass_x'))
                com_y = safe_float(row.get('center_of_mass_y'))
                com_z = safe_float(row.get('center_of_mass_z'))
                
                # Try to find floor data
                floor_pos = None
                if entryid in floor_dict:
                    floor_pos = floor_dict[entryid]
                else:
                    normalized = normalize_entryid(entryid)
                    if normalized in floor_dict:
                        floor_pos = floor_dict[normalized]
                
                # Calculate floor metrics if we have both COM and floor
                if floor_pos and com_x is not None and com_y is not None:
                    floor_y = floor_pos[1]
                    distance_from_floor = abs(com_y - floor_y)
                    below_floor = com_y < floor_y
                    
                    row['distance_from_floor'] = distance_from_floor
                    row['below_floor'] = 'True' if below_floor else 'False'
                    updated_count += 1
                else:
                    # Keep existing values if any, otherwise leave empty
                    if not row.get('distance_from_floor') or row.get('distance_from_floor') == '':
                        row['distance_from_floor'] = ''
                    if not row.get('below_floor') or row.get('below_floor') == '':
                        row['below_floor'] = ''
                
                rows.append(row)
        
        # Write updated file
        with open(metrics_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"    ✅ Updated {updated_count}/{len(rows)} rows with floor information")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    base_dir = base_dir = os.path.dirname(os.path.abspath(__file__))
    metrics_dir = os.path.join(base_dir, "metrics")
    
    print("="*70)
    print("ADDING FLOOR INFORMATION TO PHANTOMLIMB AND PIANOTILES")
    print("="*70)
    
    apps = {
        "PhantomLimb": os.path.join(metrics_dir, "metrics_PhantomLimb.csv"),
        "PianoTiles": os.path.join(metrics_dir, "metrics_PianoTiles.csv"),
    }
    
    success_count = 0
    
    for app_name, metrics_path in apps.items():
        print(f"\n{'='*70}")
        print(f"Processing {app_name}")
        print(f"{'='*70}")
        
        # Load floor data from CSV files
        floor_dict = load_floor_data_from_csv(app_name, base_dir)
        
        if not floor_dict:
            print(f"  ⚠️ No floor data loaded for {app_name}")
            continue
        
        print(f"  ✅ Loaded {len(floor_dict)} floor entries")
        
        # Add floor information to metrics file
        if add_floor_to_metrics_file(metrics_path, floor_dict, app_name):
            success_count += 1
    
    print(f"\n{'='*70}")
    print(f"✅ Successfully processed {success_count}/{len(apps)} apps")
    print(f"{'='*70}")
    
    # Update combined file
    print(f"\nUpdating combined metrics file...")
    try:
        combined_path = os.path.join(base_dir, "extracted_metrics_all_apps.csv")
        
        all_rows = []
        fieldnames = None
        
        all_apps = ["Archery", "Puzzle", "Sea", "War", "PhantomLimb", "PianoTiles"]
        for app in all_apps:
            metrics_path = os.path.join(metrics_dir, f"metrics_{app}.csv")
            if os.path.exists(metrics_path):
                with open(metrics_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    if fieldnames is None:
                        fieldnames = list(reader.fieldnames)
                    all_rows.extend(list(reader))
        
        if all_rows and fieldnames:
            with open(combined_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            
            print(f"✅ Updated combined file: {combined_path}")
            print(f"   Total rows: {len(all_rows)}")
            
            # Count floor metrics
            with_floor = sum(1 for r in all_rows 
                          if r.get('distance_from_floor') and r['distance_from_floor'] != '')
            print(f"   Rows with floor information: {with_floor}/{len(all_rows)} ({with_floor/len(all_rows)*100:.1f}%)")
    
    except Exception as e:
        print(f"⚠️ Error updating combined file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
