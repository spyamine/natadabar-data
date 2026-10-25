#!/bin/sh
# usage: run_islamweb_range.sh <bk_no> <db_name> <part> <start> <end>   -> output/<db_name>_p<part>.db
cd ~/Developer/islamweb-scraper || exit 1
python3 scraper.py "$1" "$2_p$3" --start "$4" --end "$5" >> ~/Developer/natadabar-data/work/logs/"$2"_p"$3".log 2>&1
