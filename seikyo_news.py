import asyncio
import sys
import os
from datetime import datetime
from playwright.async_api import async_playwright
from feedgen.feed import FeedGenerator

# --- 設定情報 ---
USER_ID = "cyanobi.2.29@gmail.com"
PASSWORD = "B0eceJ*kz%"

# カテゴリとURLの定義（おびさん提供リスト）
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

# 実行時の日付を「YYYY年M月D日」形式で取得（0埋めなし）
now = datetime.now()
TARGET_DATE = f"{now.year}年{now.month}月{now.day}日"

async def scrape_category(page, category_name, url, fg):
    """
    指定されたカテゴリのページから本日の記事を抽出してRSSフィードに追加する
    """
    print(f"📂 [巡回] {category_name} にアクセス中...")
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        # 記事ブロック(p2o_text系)をすべて取得
        # 大白蓮華など構造が違う可能性があるため、広範なセレクタを設定
        blocks = await page.query_selector_all("div.p2o_text, div.p2o_text_photo, div.news_list_block, div.daibyakurenge_list_block, .article-item")
        
        local_count = 0
        for block in blocks:
            # 1. 記事リンクの取得
            link_el = await block.query_selector("a[href*='article']")
            if not link_el:
                continue
            
            raw_href = await link_el.get_attribute("href")
            
            # 2. 日付の確認
            date_el = await block.query_selector(".ts_days, .date")
            if date_el:
                date_text = await date_el.inner_text()
            else:
                full_text = await block.inner_text()
                if TARGET_DATE in full_text:
                    date_text = TARGET_DATE
                else:
                    continue

            if TARGET_DATE not in date_text:
                continue

            # 3. タイトルの取得
            title_el = await block.query_selector(".under, h3, .shosai-title, .title")
            title = await title_el.inner_text() if title_el else "タイトル不明"

            # URLの完全化
            full_url = f"https:{raw_href}" if raw_href.startswith("//") else raw_href
            if not full_url.startswith("http"):
                full_url = f"https://www.seikyoonline.com{raw_href}"

            # 重複登録の防止 (URLをIDとしてチェック)
            # 複数のカテゴリに同じ記事がある場合があるため
            fe = fg.add_entry()
            fe.title(f"[{category_name}] {title.strip()}")
            fe.link(href=full_url)
            fe.description(f"カテゴリ: {category_name} / 公開日: {date_text.strip()}")
            fe.id(full_url)
            
            local_count += 1
            print(f"  [+] {title.strip()[:30]}...")

        return local_count

    except Exception as e:
        print(f"  ⚠️ {category_name} の取得中にエラー: {e}")
        return 0

async def main():
    async with async_playwright() as p:
        print(f"\n🚀 [1/5] ブラウザ起動...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # --- ログインフェーズ ---
            print(f"🔑 [2/5] ログイン実行中...")
            await page.goto("https://www.seikyoonline.com/auth/login", wait_until="networkidle")
            await page.fill("input[placeholder*='SOKA ID']", USER_ID)
            await page.fill("input[placeholder*='パスワード']", PASSWORD)
            await page.click("button:has-text('ログイン')")
            await page.wait_for_load_state("networkidle")
            print("✅ ログイン成功。")

            # --- RSSフィードの初期化 ---
            fg = FeedGenerator()
            fg.title(f"聖教新聞 本日の総合ニュース ({TARGET_DATE})")
            fg.link(href="https://www.seikyoonline.com/")
            fg.description(f"{TARGET_DATE} の各カテゴリ更新情報")

            # --- 全カテゴリ巡回フェーズ ---
            print(f"🔄 [3/5] 全カテゴリを巡回して記事を収集します（ターゲット: {TARGET_DATE}）")
            total_count = 0
            for name, url in CATEGORIES.items():
                count = await scrape_category(page, name, url, fg)
                total_count += count

            print(f"\n📊 [4/5] 収集結果: 合計 {total_count} 件の記事を取得しました。")

            # --- 保存フェーズ ---
            if total_count > 0:
                print(f"💾 [5/5] RSSファイル保存中...")
                output_file = 'seikyo_news.xml'
                fg.rss_file(output_file)
                print(f"✨ 完了: {os.getcwd()}/{output_file}")
            else:
                print("⚠️ 本日の記事が1件も見つからなかったため、RSSは更新しません。")

        except Exception as e:
            print(f"❌ 致命的なエラー: {e}")
        finally:
            await browser.close()
            print("🔌 ブラウザ終了。\n")

if __name__ == "__main__":
    asyncio.run(main())
