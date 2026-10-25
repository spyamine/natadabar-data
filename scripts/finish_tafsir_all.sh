#!/bin/sh
# Phase A: tier-1 tafsir (already scraping) -> build, verify, upload, push.
# Phase B: scrape tier-2/3 tafsir in chunks -> build, verify, upload, push.
cd ~/Developer/natadabar-data || exit 1
wait_scrapers() { while pgrep -f "xargs -P 10" >/dev/null || pgrep -f "scraper.py" >/dev/null; do sleep 60; done; }
publish() {  # $1 = queue file, $2 = commit message
    ( cd scripts && python3 build_islamweb.py $(cut -d' ' -f1 ../work/$1 | tr '\n' ' ') > ../work/logs/build_$1.log 2>&1; python3 verify.py >> ../work/logs/build_$1.log 2>&1 )
    gh release upload library-v1 -R spyamine/natadabar-data --clobber dist/*.deflate dist/manifest.json
    cp dist/manifest.json catalog/manifest.json
    python3 scripts/build_catalog.py && python3 scripts/export_app_catalog.py
    git add -A && git commit -qm "$2

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Fm4hPEgzczmqoCwwY3C9vt" && git push -q origin HEAD
}
wait_scrapers
publish islamweb_queue3.txt "Publish tier-1 tafsir and ahkam al-Quran databases with ayah indexes"
echo "PHASE A DONE"
cat work/tafsir_jobs2.txt | xargs -P 10 -L 1 scripts/run_islamweb_range.sh
wait_scrapers
publish islamweb_queue4.txt "Publish tier-2/3 tafsir databases with ayah indexes"
echo FINISHED
