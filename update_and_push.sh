#!/bin/bash

# 1. ログの記録（デバッグ用）
echo "--- RSS Update Start: $(date) ---" >> /home/yoshikazu-obikawa/dev/seikyoRSS/rss_log.txt

# 2. ディレクトリへ移動
cd /home/yoshikazu-obikawa/dev/seikyoRSS

# 3. 仮想環境を有効化してPython実行
# 画像取得機能が入った「完全版」を動かします
source .venv/bin/activate
python seikyo_news.py >> /home/yoshikazu-obikawa/dev/seikyoRSS/rss_log.txt 2>&1
deactivate

# 4. GitでGitHubへ送信
git add .
git commit -m "auto-update: RSS with images $(date +'%Y-%m-%d %H:%M')"
git push origin main >> /home/yoshikazu-obikawa/dev/seikyoRSS/rss_log.txt 2>&1

# 5. 終了ログ
echo "--- RSS Update End: $(date) ---" >> /home/yoshikazu-obikawa/dev/seikyoRSS/rss_log.txt

# 6. 安全なシャットダウン（SwitchBotが切れる前に自分から寝る）
# sudo shutdown -h now
