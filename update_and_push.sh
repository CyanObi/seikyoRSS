#!/bin/bash
# update_and_push.sh

cd /home/yoshikazu-obikawa/dev/seikyoRSS
source .venv/bin/activate

# 1. スクレイピング実行
python3 seikyo_scraper.py

# 2. GitHubへ送信
git add .
git commit -m "Auto update: $(date +'%Y-%m-%d %H:%M')"
if git push origin main; then
    echo "成功: 1分後にシャットダウンします。"
    sudo shutdown -h +1
else
    echo "失敗: 調査のため起動を継続します。"
fi