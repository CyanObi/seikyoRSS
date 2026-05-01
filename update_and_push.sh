#!/bin/bash
# ---------------------------------------------------------
# Seikyo RSS - Pure GitHub Sync Script
# ---------------------------------------------------------

# 1. 実行ディレクトリの確定
cd /home/yoshikazu-obikawa/dev/seikyo_backup

# 2. 仮想環境の有効化
source .venv/bin/activate

# 3. 取得実行（ここで 15 items 取得される！）
python3 seikyo_scraper.py

# 4. GitHubへ最新の状態をプッシュ
/usr/bin/git add .
/usr/bin/git commit -m "Auto update: $(date +'%Y-%m-%d %H:%M')"
/usr/bin/git push origin main

echo "✅ 取得完了。GitHubへの反映も成功しました。"
