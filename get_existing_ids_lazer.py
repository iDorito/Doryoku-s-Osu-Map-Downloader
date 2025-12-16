#!/usr/bin/env python
"""\
Helper module to find osu beatmapset ids inside folders for lazer.
"""

import os
import json
import config
from pathlib import Path

# MAIN PATHS
LASER_FILES_PATH = config.LASER_FILES_PATH
DOWNLOAD_PATH = config.DOWNLOAD_PATH
DB_JSON_DIR = config.DB_JSON          
JSON_FILE_PATH = DB_JSON_DIR / config.json_file  

# Create folders
DOWNLOAD_PATH.mkdir(parents=True, exist_ok=True)
LASER_FILES_PATH.mkdir(parents=True, exist_ok=True)
DB_JSON_DIR.mkdir(parents=True, exist_ok=True)

print(f"downloads: {DOWNLOAD_PATH}")
print(f"lazer files: {LASER_FILES_PATH}")
print(f"Json: {JSON_FILE_PATH}")

# === CREAR ARCHIVO JSON SI NO EXISTE ===
if not JSON_FILE_PATH.exists():
    print("Creatings new empty db.json...")
    JSON_FILE_PATH.write_text(json.dumps({"downloaded_maps": []}, indent=4), encoding='utf-8')
else:
    print("db.json exists.")

def is_osu_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
            return first_line.startswith('osu file format')
    except Exception:
        return False

def extract_beatmapset_id(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            f.readline()  # Skip first line
            for line in f:
                if line.startswith('BeatmapSetID:'):
                    try:
                        return int(line.split(':', 1)[1].strip())
                    except ValueError:
                        return None
                if line.startswith('[HitObjects]'):
                    break
    except Exception:
        return None
    return None

def lazer_beatmapsets_ids_scan():
    print(f"Scanning: {LASER_FILES_PATH}")
    print("This could take a while depending on how many maps you have...")

    found_id_sets = set()
    revised_files = 0
    maps_found = 0

    if not LASER_FILES_PATH.exists():
        print("Error: Osu lazer folder doesn't exist.")
        return []

    for root, dirs, files in os.walk(LASER_FILES_PATH):
        for filename in files:
            full_path = Path(root) / filename
            revised_files += 1

            if not is_osu_file(full_path):
                continue

            maps_found += 1
            beatmapset_id = extract_beatmapset_id(full_path)
            if beatmapset_id is not None and beatmapset_id != -1: # For local maps
                found_id_sets.add(beatmapset_id)

    print("\n--- RESUMEN ---")
    print(f"Scanned files: {revised_files}")
    print(f".osu files detected: {maps_found}")
    print(f"Unique sets found: {len(found_id_sets)}")

    return sorted(found_id_sets)

def scan_maps():
    found_ids = lazer_beatmapsets_ids_scan()

    result = {"downloaded_maps": found_ids}

    # Guardar en el JSON
    with open(JSON_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4)   

    print("\nIds saved to:")
    print(f"   {JSON_FILE_PATH}")
    print(f"   Total unique sets: {len(found_ids)}")
    if found_ids:
        print(f"   First 20 maps: {found_ids[:20]}")

        return True, found_ids



# === EJECUCIÓN PRINCIPAL ===
if __name__ == "__main__":
    scan_maps()