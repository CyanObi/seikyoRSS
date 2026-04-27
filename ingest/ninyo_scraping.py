import requests
from bs4 import BeautifulSoup
import json
import asyncio
import os
import shutil
import re
from datetime import datetime
from playwright.async_api import async_playwright
from feedgen.feed import FeedGenerator

# --- 【Path Settings】絶対パスで固定 ---
BASE_DIR = "/home/yoshikazu-obikawa/dev/seikyoRSS"
IMAGE_DIR = os.path.join(BASE_DIR, "images")
INGEST_DIR = os.path.join(BASE_DIR, "ingest") # LLMインジェスト用フォルダ
RSS_FILE = os.path.join(BASE_DIR, "seikyo_news.xml")
JSON_FILE = os.path.join(BASE_DIR, "latest_articles.json")

# --- Configuration ---
USER_ID = "cyanobi.2.29@gmail.com"
PASSWORD = "B0eceJ*kz%"
GITHUB_BASE_URL = "https://cyanobi.github.io/seikyoRSS/"

# 【特別編】ターゲット：大白蓮華
CATEGORIES = {
    "大白蓮華": "https://www.seikyoonline.com/add_contents/daibyakurenge/"
}

# ターゲット日付・キーワード設定（任用試験特別編）
TARGET_YEAR = 2026
TARGET_MONTH = 4
TARGET_DAY = 1
KEYWORD = "任用試験のために"
FILE_DATE = "20260401_exam_special"

all_scraped_data = []

async def fetch_article_body(browser_context, url):
    """記事詳細ページから本文を抽出する"""
    detail_page = await browser_context.new_page()
    body_text = ""
    try:
        # URLの正規化
        target_url = url
        if target_url.startswith("//"):
            target_url = "https:" + target_url
        elif target_url.startswith("/"):
            target_url = "https://www.seikyoonline.com" + target_url
        
        print(f"    🔗 詳細ページへアクセス中: {target_url}")
        
        # 読み込み待機を 'load' (全リソース完了) に設定
        await detail_page.goto(target_url, wait_until="load", timeout=60000)
        
        # ログイン画面に飛ばされていないかチェック
        page_title = await detail_page.title()
        if "ログイン" in page_title or "Auth" in page_title:
            print("    ❌ ログインセッションが切れたため、ログイン画面にリダイレクトされました。")
            return ""

        # まず記事のメインコンテナが出るのを待つ
        try:
            await detail_page.wait_for_selector(".phase2_outer", timeout=15000)
        except:
            pass

        # 次に本文要素(rubyno)が出るのを待つ
        try:
            await detail_page.wait_for_selector(".rubyno", timeout=15000)
        except Exception:
            print(f"    ⚠️ タイムアウト: .rubyno が見つかりません (現在のページ: {page_title})")
            
        # JSによるルビ処理の安定化を待機
        await asyncio.sleep(5)
        
        # evaluateを使用してDOMから直接テキストをかき集める
        elements_data = await detail_page.evaluate('''() => {
            const container = document.querySelector('.phase2_outer') || document.body;
            const rubynos = container.querySelectorAll('.rubyno');
            return Array.from(rubynos).map(el => ({
                tag: el.tagName,
                className: el.className,
                text: el.textContent.trim()
            }));
        }''')
        
        texts = []
        for item in elements_data:
            clean_text = item['text']
            if not clean_text or "音声はこちら" in clean_text:
                continue
                
            # インジェスト向けフォーマット整形
            if "subtitle1" in item['className']:
                texts.append(f"\n【{clean_text}】")
            elif item['tag'] == 'LI':
                texts.append(f"・{clean_text}")
            else:
                texts.append(clean_text)
        
        # 重複行をマージして結合
        final_lines = []
        for line in texts:
            if not final_lines or line != final_lines[-1]:
                final_lines.append(line)
        
        body_text = "\n".join(final_lines).strip()
        
    except Exception as e:
        print(f"    ⚠️ 本文解析エラー: {e}")
    finally:
        await detail_page.close()
    return body_text

def is_target_date(text):
    """日付文字列がターゲットに合致するか判定"""
    if not text: return False
    nums = re.findall(r'\d+', text)
    if len(nums) >= 3:
        try:
            y, m, d = int(nums[0]), int(nums[1]), int(nums[2])
            if y == TARGET_YEAR and m == TARGET_MONTH and d == TARGET_DAY:
                return True
        except: pass
    return False

async def scrape_category(context, category_name, url, fg):
    page = await context.new_page()
    print(f"\n📂 [特別巡回] {category_name} にアクセス中...")
    try:
        target_url = "https:" + url if url.startswith("//") else url
        await page.goto(target_url, wait_until="networkidle", timeout=60000)
        
        print("  ⏳ 記事リストを深層までロード中...")
        for _ in range(8): 
            await page.evaluate("window.scrollBy(0, 2000)")
            await asyncio.sleep(1.5)

        # 構造に基づいてブロックを取得
        blocks = await page.query_selector_all(".sub_item li, div.daibyakurenge_list_block, .article-item, .list_item, li.clearfix")
        
        print(f"  🔍 {len(blocks)} 個のブロックを検知。条件をチェックします...")

        local_count = 0
        for block in blocks:
            # 1. リンク
            link_el = await block.query_selector("a[href*='article']")
            if not link_el: continue
            raw_href = await link_el.get_attribute("href")

            # 2. 日付 (ts_days)
            date_el = await block.query_selector(".ts_days, .date")
            date_text = await date_el.inner_text() if date_el else await block.inner_text()
            if not is_target_date(date_text):
                continue

            # 3. 表題 (under)
            title_el = await block.query_selector(".under, h3 span.rubyno, h3")
            title = await title_el.inner_text() if title_el else "タイトル不明"
            title = title.strip()

            # 4. キーワード
            if KEYWORD not in title:
                continue

            print(f"  ✅ マッチ: {title}")
            
            # URL正規化
            full_url = raw_href
            if full_url.startswith("//"): full_url = "https:" + full_url
            elif full_url.startswith("/"): full_url = "https://www.seikyoonline.com" + full_url

            # 5. 本文取得（粘り強い待機版）
            article_body = await fetch_article_body(context, full_url)
            
            body_len = len(article_body)
            if body_len < 20:
                print(f"    ⚪️ 本文が取得できませんでした (文字数: {body_len})")
                continue

            print(f"    [+] 取得完了 (文字数: {body_len})")

            # RSS用エントリ追加
            summary = "\n".join(article_body.split("\n")[:10])
            fe = fg.add_entry()
            fe.title(f"[{category_name}] {title}")
            fe.link(href=full_url)
            fe.id(full_url)
            fe.description(f"公開日: {date_text.strip()}<br><br>{summary.replace(chr(10), '<br>')}")
            
            # データ蓄積
            all_scraped_data.append({
                "title": title,
                "category": category_name,
                "url": full_url,
                "body": article_body,
                "date": date_text.strip(),
                "scraped_at": datetime.now().isoformat()
            })
            local_count += 1

        return local_count
    except Exception as e:
        print(f"  ⚠️ カテゴリ巡回エラー: {e}")
        return 0
    finally:
        await page.close()

async def main():
    if os.path.exists(IMAGE_DIR):
        shutil.rmtree(IMAGE_DIR)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(INGEST_DIR, exist_ok=True) 

    async with async_playwright() as p:
        print(f"🚀 [1/5] ブラウザ起動...")
        browser = await p.chromium.launch(headless=True)
        # コンテキスト作成時にクッキーやストレージを共有しやすくする
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1200},
            locale="ja-JP",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        try:
            print(f"🔍 [2/5] 認証工程...")
            await page.goto("https://www.seikyoonline.com/auth/login", wait_until="networkidle")
            login_needed = await page.query_selector("input[placeholder*='SOKA ID']")
            if login_needed:
                await page.fill("input[placeholder*='SOKA ID']", USER_ID)
                await page.fill("input[placeholder*='パスワード']", PASSWORD)
                await page.click("button:has-text('ログイン')")
                await asyncio.sleep(8) # 認証後のリダイレクトを長めに待つ
                print("  ✅ ログイン工程完了")
            else:
                print("  ✅ ログイン済み（セッション有効）")

            fg = FeedGenerator()
            fg.title(f"聖教新聞 特別編 ({TARGET_YEAR}/{TARGET_MONTH}/{TARGET_DAY})")
            fg.link(href=GITHUB_BASE_URL)
            fg.description(f"{KEYWORD} 特集データ")
            fg.language('ja')

            print(f"🔄 [3/5] 抽出開始（ターゲット: {KEYWORD}）...")
            total_count = 0
            for name, url in CATEGORIES.items():
                total_count += await scrape_category(context, name, url, fg)

            print(f"\n📊 [4/5] 抽出結果: {total_count} 件")

            if total_count > 0:
                print(f"💾 [5/5] ファイル出力...")
                fg.rss_file(RSS_FILE)
                
                with open(JSON_FILE, 'w', encoding='utf-8') as f:
                    json.dump(all_scraped_data, f, ensure_ascii=False, indent=4)
                
                ingest_txt_path = os.path.join(INGEST_DIR, f"{FILE_DATE}_ingest.txt")
                with open(ingest_txt_path, 'w', encoding='utf-8') as f:
                    for item in all_scraped_data:
                        f.write(f"--- ARTICLE_START ---\n")
                        f.write(f"TITLE: {item['title']}\n")
                        f.write(f"DATE: {item['date']}\n")
                        f.write(f"CATEGORY: {item['category']}\n")
                        f.write(f"URL: {item['url']}\n")
                        f.write(f"--- BODY ---\n")
                        f.write(f"{item['body']}\n")
                        f.write(f"--- ARTICLE_END ---\n\n")
                
                print(f"✨ 完了: インジェスト用ファイルを更新しました。")
                print(f"📂 保存先: {ingest_txt_path}")
            else:
                print("⚠️ 条件に合致する記事が見つかりませんでした。")

        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())