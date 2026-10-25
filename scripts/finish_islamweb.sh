#!/bin/sh
# Wait for the islamweb queue to drain, then build, verify, upload and commit.
cd ~/Developer/natadabar-data || exit 1
while pgrep -f "xargs -P 4" >/dev/null || pgrep -f "islamweb-scraper" >/dev/null || pgrep -f "scraper.py" >/dev/null; do sleep 60; done
cd scripts || exit 1
python3 build_openiti.py $(cat ../work/openiti_rest.txt ../work/openiti_extra.txt 2>/dev/null) && python3 build_islamweb.py $(cat ../work/islamweb_queue*.txt | cut -d' ' -f1 | tr '\n' ' ') && python3 verify.py
cd ..
gh release upload library-v1 -R spyamine/natadabar-data --clobber dist/*.deflate dist/manifest.json
cp dist/manifest.json catalog/manifest.json
git add -A && git commit -qm "Add islamweb-sourced databases to library-v1 manifest

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Fm4hPEgzczmqoCwwY3C9vt" && git push -q origin HEAD
echo FINISHED
