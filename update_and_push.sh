#!/bin/bash
# update_and_push.sh

cd /home/yoshikazu-obikawa/dev/seikyoRSS
source .venv/bin/activate

# スクレイピング実行
python3 seikyo_scraper.py

# GitHubへ送信
git add .
git commit -m "Auto update: $(date +'%Y-%m-%d %H:%M')"
git push origin main

# --- 修正ポイント ---
# sudo shutdown -h +1  <-- この行を削除するか、先頭に # をつけて無効化します
echo "更新完了。ラズパイは引き続き稼働中です。"
