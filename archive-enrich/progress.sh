#!/bin/bash
DB="${ARCHIVE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}/metadata/catalog.sqlite"
done=$(/opt/homebrew/bin/python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute(\"SELECT count(*) FROM enrichments WHERE model LIKE 'hub:%lite'\").fetchone()[0])")
pct=$(/opt/homebrew/bin/python3 -c "print(f'{$done/5745*100:.1f}')")
echo "── Enrichissement Vault (hub local) ──"
echo "  faits   : $done / 5745  ($pct%)"
echo "  process : $(pgrep -f enrich_hub.py >/dev/null && echo 'TOURNE ✓' || echo 'arrêté ✗')"
echo "  dernier :"; tail -2 /tmp/enrich_hub.log | sed 's/^/    /'
