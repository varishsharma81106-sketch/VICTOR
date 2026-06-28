#!/usr/bin/env bash
# test_count.sh — the single source of truth for "N tests passing" in any doc.
#
# Why this exists: VICTOR_WHAT_IS_BUILT.md claimed 192 tests when the real,
# collected number was 177 — a hand-typed arithmetic error (142 + 25 + 20 + 5)
# that nobody caught because nobody ran the command the doc was describing.
# Run this and paste its output instead of doing the addition by hand.
#
# Usage:
#   ./scripts/test_count.sh            # "176 passed, 1 failed, 177 total"
#   ./scripts/test_count.sh --collect  # just the collected count, no run
#
# Run from the repo root (same directory as setup.py).

set -uo pipefail
# Note: deliberately not `set -e` — pytest exits non-zero on any test
# failure, which is informative output here, not a script error.

if [[ "${1:-}" == "--collect" ]]; then
    COLLECTED=$(VICTOR_MOCK_LLM=1 python3 -m pytest --collect-only -q 2>&1 | tail -1)
    echo "$COLLECTED"
    exit 0
fi

RESULT=$(VICTOR_MOCK_LLM=1 python3 -m pytest -q 2>&1 | tail -1)
echo "$RESULT"

# Also drop a per-file breakdown so a doc author can see where the count
# actually comes from, the same way the audit caught the metric_conflation
# miscount (claimed +20, actually +5).
echo ""
echo "Per-file breakdown:"
VICTOR_MOCK_LLM=1 python3 -m pytest --collect-only -q 2>&1 | grep "::" | sed -E 's/::.*//' | sort | uniq -c | sort -rn
