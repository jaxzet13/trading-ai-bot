#!/bin/bash
# Run the per-sport study on each series as soon as its download finishes (download log line "SERIES: +N").
cd /home/user/trading-ai-bot
LOG=research/sports_study/download_log.txt
done_list="${DONE:-}"   # series already scored (pass DONE="KXNBAGAME ..." when restarting)
while true; do
  for s in $(grep -oE '^KX[A-Z0-9]+: \+[0-9]+' $LOG | cut -d: -f1); do
    case " $done_list " in *" $s "*) continue;; esac
    nice -n 10 python3 research/sports_study/study.py $s >> research/sports_study/study_log.txt 2>&1
    done_list="$done_list $s"
  done
  grep -q "download done" $LOG && [ "$(grep -cE '^KX[A-Z0-9]+: \+[0-9]+' $LOG)" -le "$(echo $done_list | wc -w)" ] && break
  sleep 30
done
echo "all studies done" >> research/sports_study/study_log.txt
