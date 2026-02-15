#!/bin/bash
# Start React app in background
yarn --cwd webapp start &

# Start Flask backend
python3 main.py