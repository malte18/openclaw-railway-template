#!/bin/bash
# Wrapper that runs a script and saves output to a results file
# Usage: bash run.sh scout.py --niche "Beef Snacks"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_FILE="/tmp/scout_last_result.txt"

# Run the python script, capture all output
python3 "$SCRIPT_DIR/$@" > "$RESULTS_FILE" 2>&1
EXIT_CODE=$?

# Print the results
cat "$RESULTS_FILE"
exit $EXIT_CODE
