#!/bin/bash
# Run backend scripts for NBA SRS site

# Fetch schedule for this week
python3 scripts/fetch_schedule.py

# Run season simulation with default params
python3 scripts/simulate_season.py
