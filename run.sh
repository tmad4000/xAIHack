#!/bin/bash
# Start CityVoice server

cd "$(dirname "$0")"
source venv/bin/activate
python server.py
