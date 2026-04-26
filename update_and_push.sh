#!/bin/bash
# update_and_push.sh

# 1. 確実に作業ディレクトリへ移動
cd /home/yoshikazu-obikawa/dev/seikyoRSS

# 2. 仮想環境の有効化（パスは環境に合わせてください）
source .venv/bin/activate

# 3. スクレイピング実行
python3 seikyo_scraper.py

# 4. Webサーバ（直送用）へのコピーも残しておくと便利です
cp seikyo_news.xml /var/www/html/seikyo_news.xml

# 5. GitHubへ送信
# gitコマンドもフルパス（/usr/bin/git）で書くとcronでより確実です
/usr/bin/git add .
/usr/bin/git commit -m "Auto update: $(date +'%Y-%m-%d %H:%M')"
/usr/bin/git push origin main

echo "更新とGitHubへの送信が完了しました。"
