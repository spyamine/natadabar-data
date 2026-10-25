#!/bin/sh
# usage: run_islamweb.sh <bk_no> <db_name>   (logs to work/logs/<db_name>.log)
cd ~/Developer/islamweb-scraper || exit 1
python3 scraper.py "$1" "$2" >> ~/Developer/natadabar-data/work/logs/"$2".log 2>&1
python3 scraper.py "$1" "$2" --build-fts >> ~/Developer/natadabar-data/work/logs/"$2".log 2>&1
