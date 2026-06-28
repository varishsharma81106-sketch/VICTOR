#!/usr/bin/env bash
# verify_doc_counts.sh
#
# Generates the real, current test count directly from pytest and checks
# it against the marked "current state" claim in VICTOR_WHAT_IS_BUILT.md.
#
# This exists because the "192 tests" claim in WHAT_IS_BUILT.md (v5.0) was
# hand-typed arithmetic (167 + 20 + 5) instead of a real count, and the +20
# was wrong (test_metric_conflation.py actually has 5 tests, not 20). The
# real number — 177 — was sitting one `pytest --collect-only` away the
# whole time.
#
# Only checks the number wrapped in <!-- CURRENT_TEST_COUNT --> markers in
# the "One-Line State" section — NOT every number in the document, since
# the Results Log legitimately contains historical deltas (142 -> 167 -> 177)
# that should stay as-is.
#
# Usage:
#   ./scripts/verify_doc_counts.sh
#
# Exit code 0 if the doc matches reality, 1 if it's drifted.

set -euo pipefail

cd "$(dirname "$0")/.."

DOC="VICTOR_WHAT_IS_BUILT.md"

REAL_COUNT=$(VICTOR_MOCK_LLM=1 python3 -m pytest --collect-only -q 2>/dev/null | tail -1 | grep -oE '^[0-9]+')

if [ -z "$REAL_COUNT" ]; then
    echo "ERROR: couldn't collect tests — is pytest installed and the repo importable?"
    exit 2
fi

DOC_COUNT=$(grep -oE '<!-- CURRENT_TEST_COUNT -->[0-9]+<!-- /CURRENT_TEST_COUNT -->' "$DOC" \
    | grep -oE '[0-9]+' | head -1 || true)

if [ -z "$DOC_COUNT" ]; then
    echo "ERROR: no <!-- CURRENT_TEST_COUNT --> marker found in $DOC."
    echo "Add one to the One-Line State paragraph, e.g.:"
    echo '  (<!-- CURRENT_TEST_COUNT -->177<!-- /CURRENT_TEST_COUNT --> tests)'
    exit 2
fi

echo "Real test count (pytest --collect-only): $REAL_COUNT"
echo "Current-state claim in $DOC:              $DOC_COUNT"

if [ "$DOC_COUNT" != "$REAL_COUNT" ]; then
    echo ""
    echo "FAIL: $DOC claims $DOC_COUNT tests, but pytest collects $REAL_COUNT."
    echo "Update the marked line before committing."
    exit 1
fi

echo ""
echo "OK: $DOC's current-state test count matches reality."

