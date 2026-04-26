import asyncio
import os
import shutil
from datetime import datetime
from playwright.async_api import async_playwright
from feedgen.feed import FeedGenerator

# --- 【パス設定】絶対パスで固定 ---
BASE_DIR = "/home/yoshikazu-obikawa/dev/seikyoRSS"
IMAGE_DIR = os.path.join(BASE_DIR, "images")
RSS_FILE = os.path.join(BASE_DIR, "seikyo_news.xml")

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
    "大白蓮華": "https://www.seikyoonline.com/add_contents/daibyakurenge/"
}

now = datetime.now()
TARGET_DATE = f"{now.year}年{now.month}月{now.day}日"

async def scrape_category(page, category_name, url, fg):
    print(f"📂 [巡回] {category_name} にアクセス中...")
    try:
        await page.goto(url, wait_until="networkidle", timeout=45000)
        # 画像読み込みのため少しスクロール
        await page.evaluate("window.scrollBy(0, 1000)")
        await asyncio.sleep(3) 

        # 取得対象のセレクタを広めに設定
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

            fe = fg.add_entry()
            fe.title(f"[{category_name}] {title.strip()}")
            fe.link(href=full_url)
            fe.id(full_url)
            
            desc_text = f"カテゴリ: {category_name} / 公開日: {date_text.strip()}"
            if final_img_url:
                fe.description(f'<img src="{final_img_url}" style="max-width:100%;"><br>{desc_text}')
                fe.enclosure(final_img_url, 0, 'image/jpeg')
            else:
                fe.description(desc_text)
            
            local_count += 1
            print(f"  [+] {title.strip()[:15]}... {'📸' if final_img_url else '📄'}")

        return local_count
    except Exception as e:
        print(f"  ⚠️ {category_name} エラー: {e}")
        return 0

async def main():
    if os.path.exists(IMAGE_DIR):
        shutil.rmtree(IMAGE_DIR)
    os.makedirs(IMAGE_DIR, exist_ok=True)

    async with async_playwright() as p:
        print(f"\n🚀 [1/5] ブラウザ起動...")
        browser = await p.chromium.launch(headless=True)
        # 言語とエージェントを設定
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1200},
            locale="ja-JP",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        # ★ここが抜けていました！
        page = await context.new_page()

        try:
            print(f"🔑 [2/5] ログイン実行中...")
            await page.goto("https://www.seikyoonline.com/auth/login", wait_until="networkidle")
            await page.fill("input[placeholder*='SOKA ID']", USER_ID)
            await page.fill("input[placeholder*='パスワード']", PASSWORD)
            await page.click("button:has-text('ログイン')")
            
	    # --- ここから修正・強化 ---
            print("⏳ ログイン処理完了を待機中...")
            # 1. ネットワークが静かになるまで待つ
            await page.wait_for_load_state("networkidle")
            # 2. 念のため、ログイン後のトップページにある特定の要素が出るまで待つ
            # （例: ログアウトボタンや、ユーザー名が表示される場所など）
            await asyncio.sleep(5) 
            
            # ログインが成功したか、スクリーンショットを撮って確認する（デバッグ用）
            # await page.screenshot(path="debug_after_login.png")
            # --- ここまで ---
            
            fg = FeedGenerator()
            fg.title(f"聖教新聞 本日のニュース")
            # GitHubではなく、FunnelのURLにする（もしFunnelが開通していれば）
            fg.link(href="https://[おびさんのFunnelドメイン]/")
            fg.description(f"{TARGET_DATE} 総合RSSフィード")
            # 言語設定を追加（Feedlyが解析しやすくなります）
            fg.language('ja')

            print(f"🔄 [3/5] カテゴリ巡回（ターゲット: {TARGET_DATE}）")
            total_count = 0
            for name, url in CATEGORIES.items():
                total_count += await scrape_category(page, name, url, fg)

            print(f"\n📊 [4/5] 収集完了: {total_count} 件")

            if total_count > 0:
                print(f"💾 [5/5] RSS保存...")
                fg.rss_file(RSS_FILE)
                print(f"✨ 完了: images/ と {RSS_FILE} を更新しました。")
            else:
                print("⚠️ 本日の記事がないため更新スキップ。")

        except Exception as e:
            print(f"❌ エラー: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
