#!/bin/sh
# Wait for the tafsir scrape, then build (with ayah index), verify, upload, export catalog and push.
cd ~/Developer/natadabar-data || exit 1
while pgrep -f "xargs -P 10" >/dev/null || pgrep -f "scraper.py" >/dev/null; do sleep 60; done
cd scripts || exit 1
python3 build_islamweb.py $(cut -d' ' -f1 ../work/islamweb_queue3.txt | tr '\n' ' ') > ../work/logs/tafsir_build.log 2>&1
python3 verify.py >> ../work/logs/tafsir_build.log 2>&1
cd ..
gh release upload library-v1 -R spyamine/natadabar-data --clobber dist/*.deflate dist/manifest.json
cp dist/manifest.json catalog/manifest.json
python3 scripts/build_catalog.py && python3 scripts/export_app_catalog.py
git add -A && git commit -qm "Publish tier-1 tafsir and ahkam al-Quran databases with ayah indexes

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Fm4hPEgzczmqoCwwY3C9vt" && git push -q origin HEAD
echo FINISHED
