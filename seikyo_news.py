import asyncio
import sys
import os
import shutil
from datetime import datetime
from playwright.async_api import async_playwright
from feedgen.feed import FeedGenerator

# --- 設定情報 ---
USER_ID = "cyanobi.2.29@gmail.com"
PASSWORD = "B0eceJ*kz%"
# GitHub PagesのベースURL（画像をここから配信する）
GITHUB_BASE_URL = "https://cyanobi.github.io/seikyoRSS/"
IMAGE_DIR = "images"

CATEGORIES = {
    "報道・連載": "https://www.seikyoonline.com/news/",
    "池田大作先生": "https://www.seikyoonline.com/president/",
    "体験・教学": "https://www.seikyoonline.com/experience_kyougaku/",
    "生活・文化": "https://www.seikyoonline.com/lifestyle/",
    "投稿": "https://www.seikyoonline.com/toukou/",
    "漫画": "https://www.seikyoonline.com/comic/",
    "デジタル特集": "https://www.seikyoonline.com/digital/",
    "ユース特集": "https://www.seikyoonline.com/youth/",
    "大白蓮華": "https://www.seikyoonline.com/add_contents/daibyakurenge/"
}

now = datetime.now()
TARGET_DATE = f"{now.year}年{now.month}月{now.day}日"

async def scrape_category(page, category_name, url, fg):
    print(f"📂 [巡回] {category_name} にアクセス中...")
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.evaluate("window.scrollBy(0, 800)") # 画像読み込みのため少し深めにスクロール
        await asyncio.sleep(2) 

        blocks = await page.query_selector_all("div.p2o_text, div.p2o_text_photo, div.news_list_block, div.daibyakurenge_list_block, .article-item")
        
        local_count = 0
        for block in blocks:
            # 1. 記事リンク
            link_el = await block.query_selector("a[href*='article']")
            if not link_el: continue
            raw_href = await link_el.get_attribute("href")
            
            # 2. 日付チェック
            date_el = await block.query_selector(".ts_days, .date")
            date_text = await date_el.inner_text() if date_el else await block.inner_text()
            if TARGET_DATE not in date_text: continue

            # 3. タイトル
            title_el = await block.query_selector(".under, h3, .shosai-title, .title")
            title = await title_el.inner_text() if title_el else "タイトル不明"

            # 4. 画像URLの取得とダウンロード
            img_el = await block.query_selector("img")
            final_img_url = None
            
            if img_el:
                src_url = None
                for attr in ["data-src", "src", "data-original"]:
                    val = await img_el.get_attribute(attr)
                    if val and "new" not in val.lower() and "common" not in val.lower():
                        src_url = val
                        break
                
                if src_url:
                    # URL完全化
                    if src_url.startswith("//"): src_url = f"https:{src_url}"
                    elif src_url.startswith("/"): src_url = f"https://www.seikyoonline.com{src_url}"

                    try:
                        # ファイル名生成（重複回避のため記事IDなどを混ぜるのが理想だが簡易的にURLから抽出）
                        img_name = src_url.split("/")[-1].split("?")[0]
                        if not img_name.endswith((".jpg", ".png", ".jpeg")): img_name += ".jpg"
                        
                        img_path = os.path.join(IMAGE_DIR, img_name)
                        
                        # 画像保存
                        img_res = await page.request.get(src_url)
                        if img_res.status == 200:
                            with open(img_path, "wb") as f:
                                f.write(await img_res.body())
                            # XMLにはGitHub上のパスを記載
                            final_img_url = f"{GITHUB_BASE_URL}{IMAGE_DIR}/{img_name}"
                    except Exception as e:
                        print(f"    ⚠️ 画像DL失敗: {e}")

            # 記事URL完全化
            full_url = f"https:{raw_href}" if raw_href.startswith("//") else raw_href
            if not full_url.startswith("http"): full_url = f"https://www.seikyoonline.com{raw_href}"

            # 5. RSSエントリ作成
            fe = fg.add_entry()
            fe.title(f"[{category_name}] {title.strip()}")
            fe.link(href=full_url)
            fe.id(full_url)
            
            desc_text = f"カテゴリ: {category_name} / 公開日: {date_text.strip()}"
            if final_img_url:
                # GitHub PagesのURLをsrcに指定
                fe.description(f'<img src="{final_img_url}" style="max-width:100%;"><br>{desc_text}')
                fe.enclosure(final_img_url, 0, 'image/jpeg')
            else:
                fe.description(desc_text)
            
            local_count += 1
            print(f"  [+] {title.strip()[:30]}...")

        return local_count
    except Exception as e:
        print(f"  ⚠️ {category_name} エラー: {e}")
        return 0

async def main():
    # 画像ディレクトリの初期化（古い画像を消して最新のみにする）
    if os.path.exists(IMAGE_DIR):
        shutil.rmtree(IMAGE_DIR)
    os.makedirs(IMAGE_DIR, exist_ok=True)

    async with async_playwright() as p:
        print(f"\n🚀 [1/5] ブラウザ起動...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 1200})
        page = await context.new_page()

        try:
            print(f"🔑 [2/5] ログイン実行中...")
            await page.goto("https://www.seikyoonline.com/auth/login")
            await page.fill("input[placeholder*='SOKA ID']", USER_ID)
            await page.fill("input[placeholder*='パスワード']", PASSWORD)
            await page.click("button:has-text('ログイン')")
            await page.wait_for_load_state("networkidle")
            
            fg = FeedGenerator()
            fg.title(f"聖教新聞 本日のニュース ({TARGET_DATE})")
            fg.link(href=GITHUB_BASE_URL)
            fg.description(f"{TARGET_DATE} 総合RSSフィード")

            print(f"🔄 [3/5] カテゴリ巡回")
            total_count = 0
            for name, url in CATEGORIES.items():
                total_count += await scrape_category(page, name, url, fg)

            print(f"\n📊 [4/5] 収集完了: {total_count} 件")

            if total_count > 0:
                print(f"💾 [5/5] RSS保存...")
                fg.rss_file('seikyo_news.xml')
                print(f"✨ 完了: imagesフォルダとxmlを生成しました。")
            else:
                print("⚠️ 本日の記事なし。")

        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())