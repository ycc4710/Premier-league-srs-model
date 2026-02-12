#!/usr/bin/env python3
"""
NBA SRS Ratings - Initialization Script
Runs all necessary scripts to generate site data and ensure frontend works.
"""
import subprocess
import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
site_dir = os.path.join(base_dir, '..', 'site', 'data')

scripts = [
    'fetch_data.py',
    'fetch_schedule.py',
    'update_srs.py',
    'generate_site_data.py',
    'simulate_season.py'
]

for script in scripts:
    script_path = os.path.join(base_dir, script)
    if not os.path.exists(script_path):
        print(f"Script not found: {script}")
        continue
    print(f"Running {script}...")
    try:
        subprocess.run([sys.executable, script_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running {script}: {e}")
        sys.exit(1)

print("Initialization complete. Site data is ready.")
