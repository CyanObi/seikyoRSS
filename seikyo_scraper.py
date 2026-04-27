import requests
from bs4 import BeautifulSoup
import json
import datetime
import asyncio
import os
import shutil
from datetime import datetime
from playwright.async_api import async_playwright
from feedgen.feed import FeedGenerator

# --- 【パス設定】絶対パスで固定 ---
BASE_DIR = "/home/yoshikazu-obikawa/dev/seikyoRSS"
IMAGE_DIR = os.path.join(BASE_DIR, "images")
INGEST_DIR = os.path.join(BASE_DIR, "ingest") # LLMインジェスト用フォルダ
RSS_FILE = os.path.join(BASE_DIR, "seikyo_news.xml")
JSON_FILE = os.path.join(BASE_DIR, "latest_articles.json")

# --- 設定情報 ---
USER_ID = "cyanobi.2.29@gmail.com"
PASSWORD = "B0eceJ*kz%"
GITHUB_BASE_URL = "https://cyanobi.github.io/seikyoRSS/"

CATEGORIES = {
    "報道・連載": "https://www.seikyoonline.com/news/",
    "池田大作先生": "https://www.seikyoonline.com/president/",
    "体験・教学": "https://www.seikyoonline.com/experience_kyougaku/",
    "生活・文化": "https://www.seikyoonline.com/lifestyle/",
    "投稿": "https://www.seikyoonline.com/toukou/",
    "漫画": "https://www.seikyoonline.com/comic/",
    "デジタル特集": "https://www.seikyoonline.com/digital/",
    "ユース特集": "https://www.seikyoonline.com/youth/",
} 

now = datetime.now()
TARGET_DATE = f"{now.year}年{now.month}月{now.day}日"
FILE_DATE = now.strftime("%Y%m%d")

# 全ての取得データを保持するリスト
all_scraped_data = []

async def fetch_article_body(browser_context, url):
    """記事詳細ページから本文を抽出する"""
    detail_page = await browser_context.new_page()
    body_text = ""
    try:
        # ネットワークが安定するまで待機
        await detail_page.goto(url, wait_until="networkidle", timeout=30000)
        # JSによる動的生成を待つ
        await asyncio.sleep(2)
        
        # 提示されたHTML構造に基づき、p.rubyno を確実に取得
        selectors = [
            "p.rubyno",
            "div.phase2_outer p",
            "div.article-content-text p",
            "div.article-content p",
            ".shosai-text p"
        ]
        
        texts = []
        for selector in selectors:
            elements = await detail_page.query_selector_all(selector)
            if elements:
                for el in elements:
                    t = await el.inner_text()
                    if t.strip() and t.strip() not in texts:
                        if len(t.strip()) > 5:
                            texts.append(t.strip())
                if texts: break

        body_text = "\n\n".join(texts)
        
    except Exception as e:
        print(f"    ⚠️ 本文取得失敗 ({url}): {e}")
    finally:
        await detail_page.close()
    return body_text

async def scrape_category(context, category_name, url, fg):
    page = await context.new_page()
    print(f"📂 [巡回] {category_name} にアクセス中...")
    try:
        await page.goto(url, wait_until="networkidle", timeout=45000)
        await page.evaluate("window.scrollBy(0, 1000)")
        await asyncio.sleep(3) 

        blocks = await page.query_selector_all("div.p2o_text, div.p2o_text_photo, div.news_list_block, div.daibyakurenge_list_block, .article-item, .list_item")

        local_count = 0
        for block in blocks:
            link_el = await block.query_selector("a[href*='article']")
            if not link_el: continue
            raw_href = await link_el.get_attribute("href")
            
            date_el = await block.query_selector(".ts_days, .date")
            date_text = await date_el.inner_text() if date_el else await block.inner_text()
            if TARGET_DATE not in date_text: continue

            title_el = await block.query_selector(".under, h3, .shosai-title, .title")
            title = await title_el.inner_text() if title_el else "タイトル不明"
            title = title.strip()

            img_el = await block.query_selector("img")
            final_img_url = None
            if img_el:
                src_url = None
                for attr in ["data-src", "src", "data-original"]:
                    val = await img_el.get_attribute(attr)
                    if val and all(x not in val.lower() for x in ["new", "common", "spacer", "logo"]):
                        src_url = val
                        break
                
                if src_url:
                    if src_url.startswith("//"): src_url = f"https:{src_url}"
                    elif src_url.startswith("/"): src_url = f"https://www.seikyoonline.com{src_url}"

                    try:
                        img_name = src_url.split("/")[-1].split("?")[0]
                        if not img_name.endswith((".jpg", ".png", ".jpeg")): img_name += ".jpg"
                        img_path = os.path.join(IMAGE_DIR, img_name)
                        
                        img_res = await page.request.get(src_url)
                        if img_res.status == 200:
                            with open(img_path, "wb") as f:
                                f.write(await img_res.body())
                            if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                                final_img_url = f"{GITHUB_BASE_URL}images/{img_name}"
                    except: pass

            full_url = f"https:{raw_href}" if raw_href.startswith("//") else raw_href
            if not full_url.startswith("http"): full_url = f"https://www.seikyoonline.com{raw_href}"

            print(f"   📖 本文抽出中: {title[:15]}...")
            article_body = await fetch_article_body(context, full_url)
            
            # --- RSSフィード用エントリ追加 (本文がなくてもRSSには追加) ---
            summary = "\n".join(article_body.split("\n")[:10])

            fe = fg.add_entry()
            fe.title(f"[{category_name}] {title}")
            fe.link(href=full_url)
            fe.id(full_url)
            
            desc_html = f"カテゴリ: {category_name} / 公開日: {date_text.strip()}<br><br>"
            if final_img_url:
                desc_html = f'<img src="{final_img_url}" style="max-width:100%;"><br>' + desc_html
            
            if summary:
                desc_html += f"<b>【記事概要】</b><br>{summary.replace(chr(10), '<br>')}"
            
            fe.description(desc_html)
            if final_img_url:
                fe.enclosure(final_img_url, 0, 'image/jpeg')
            
            # 全データをリストに蓄積 (後でインジェスト用にフィルタリング)
            all_scraped_data.append({
                "title": title,
                "category": category_name,
                "url": full_url,
                "body": article_body,
                "date": date_text.strip(),
                "scraped_at": datetime.now().isoformat()
            })

            local_count += 1
            print(f"  [+] 取得: {title[:15]}...")

        return local_count
    except Exception as e:
        print(f"  ⚠️ {category_name} エラー: {e}")
        return 0
    finally:
        await page.close()

async def main():
    if os.path.exists(IMAGE_DIR):
        shutil.rmtree(IMAGE_DIR)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(INGEST_DIR, exist_ok=True) 

    async with async_playwright() as p:
        print(f"\n🚀 [1/5] ブラウザ起動...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1200},
            locale="ja-JP",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()

        try:
            print(f"🔍 [2/5] ログイン状態の確認...")
            login_url = "https://www.seikyoonline.com/auth/login"
            await page.goto(login_url, wait_until="networkidle")
            
            login_input_selector = "input[placeholder*='SOKA ID'], input[type='text'], input#username"
            login_needed = await page.query_selector(login_input_selector)

            if login_needed:
                print(f"🔑 ログイン画面を検知。実行中...")
                await page.fill(login_input_selector, USER_ID)
                await page.fill("input[placeholder*='パスワード'], input[type='password'], input#password", PASSWORD)
                
                login_button = await page.query_selector("button:has-text('ログイン'), input[type='submit'], .loginButton")
                if login_button:
                    await login_button.click()
                    print("⏳ ログイン処理完了を待機中...")
                    await asyncio.sleep(5)
                else:
                    print("⚠️ ログインボタンが見つかりません。")
            else:
                print("✅ 自動ログイン済み。ログイン工程を省略します。")

            fg = FeedGenerator()
            fg.title(f"聖教新聞 本日のニュース")
            fg.link(href=GITHUB_BASE_URL)
            fg.description(f"{TARGET_DATE} 総合RSSフィード")
            fg.language('ja')

            print(f"🔄 [3/5] カテゴリ巡回（ターゲット: {TARGET_DATE}）")
            total_count = 0
            for name, url in CATEGORIES.items():
                total_count += await scrape_category(context, name, url, fg)

            print(f"\n📊 [4/5] 収集完了: {total_count} 件")

            if total_count > 0:
                print(f"💾 [5/5] 各種保存処理...")
                
                # 1. RSS保存 (全ての記事を保持)
                fg.rss_file(RSS_FILE)
                
                # --- インジェスト用データのフィルタリング (本文があるものだけ抽出) ---
                ingest_data_list = [item for item in all_scraped_data if item['body'].strip()]
                
                # 2. Ingest用JSON書き出し
                with open(JSON_FILE, 'w', encoding='utf-8') as f:
                    json.dump(ingest_data_list, f, ensure_ascii=False, indent=4)
                
                # 3. Ingest用テキストファイルの出力 (本文があるもののみ)
                ingest_txt_path = os.path.join(INGEST_DIR, f"{FILE_DATE}_seikyo_ingest.txt")
                with open(ingest_txt_path, 'w', encoding='utf-8') as f:
                    for item in ingest_data_list:
                        f.write(f"--- ARTICLE_START ---\n")
                        f.write(f"TITLE: {item['title']}\n")
                        f.write(f"DATE: {item['date']}\n")
                        f.write(f"CATEGORY: {item['category']}\n")
                        f.write(f"URL: {item['url']}\n")
                        f.write(f"--- BODY ---\n")
                        f.write(f"{item['body']}\n")
                        f.write(f"--- ARTICLE_END ---\n\n")

                print(f"✨ 完了: RSS(全記事), JSON/TXT(本文あり記事のみ) を更新しました。")
                print(f"📂 インジェスト対象外(本文なし): {total_count - len(ingest_data_list)} 件")
            else:
                print("⚠️ 本日の記事がないため更新スキップ。")

        except Exception as e:
            print(f"❌ エラー: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())