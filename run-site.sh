#!/bin/bash
# Lance le site de catalogage (Flask) sur 127.0.0.1:5055.
cd "$(dirname "$0")/app" && exec python -m flask run --host 127.0.0.1 --port 5055 --no-reload
