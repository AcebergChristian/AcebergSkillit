#!/usr/bin/env python3
"""
Wellfound Silicon Valley Startups Scraper
Output: CSV + HTML report in current working directory
"""
import json, csv, time, sys, os, re, html
from datetime import datetime

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests")
    sys.exit(1)

# ========== 1. 尝试通过内部 API 获取（更快、更稳定）==========
def fetch_via_api():
    """尝试 wellfound 的 JSON API（非公开，但经常可用）"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://wellfound.com/startups/location/silicon-valley",
    }
    # 常见 API 端点（基于观察）
    urls = [
        "https://api.angel.co/1/startups?location=silicon-valley&per_page=20",
        "https://wellfound.com/api/v1/startups?location=silicon-valley&limit=20",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    return data, "api"
                elif isinstance(data, dict) and "startups" in data:
                    return data["startups"], "api"
        except:
            continue
    return None, None

# ========== 2. 降级使用 Selenium（API 失败时）==========
def fetch_via_selenium():
    """使用 Selenium + Chrome 无头模式渲染页面"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException
    except ImportError:
        print("Selenium 未安装，无法降级。请安装: pip install selenium")
        return None

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get("https://wellfound.com/startups/location/silicon-valley")
        # 等待卡片加载（最多 20 秒）
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test='startup-card'], .startup-card")))
        # 滚动以触发更多加载
        for _ in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        # 提取所有 startup 卡片
        cards = driver.find_elements(By.CSS_SELECTOR, "[data-test='startup-card'], .startup-card, .styles__startupCard___abc")
        startups = []
        for card in cards[:20]:
            try:
                name_el = card.find_element(By.CSS_SELECTOR, "h3, .startup-name, [class*='name']")
                name = name_el.text.strip()
            except:
                name = ""
            try:
                round_el = card.find_element(By.CSS_SELECTOR, "[class*='round'], [class*='funding'], [class*='stage']")
                round_text = round_el.text.strip()
            except:
                round_text = ""
            try:
                jobs_el = card.find_element(By.CSS_SELECTOR, "[class*='jobs'], [class*='positions'], [class*='hiring']")
                jobs_text = re.search(r'(\d+)', jobs_el.text)
                jobs = int(jobs_text.group(1)) if jobs_text else 0
            except:
                jobs = 0
            if name:
                startups.append({"name": name, "round": round_text, "jobs": jobs})
        return startups[:20] if startups else None
    except Exception as e:
        print(f"Selenium 抓取异常: {e}")
        return None
    finally:
        if driver:
            driver.quit()

# ========== 3. 主流程 ==========
def main():
    print("开始抓取 wellfound Silicon Valley startups...")
    starters, source = fetch_via_api()
    if not starters:
        print("API 方式失败，降级到 Selenium...")
        starters = fetch_via_selenium()
        source = "selenium" if starters else "failed"

    if not starters:
        print("所有抓取方式均失败。生成错误报告。")
        # 生成仅含错误信息的 HTML
        error_html = f"""<html><body><h2>抓取失败</h2>
<p>无法从 wellfound.com 获取数据。可能原因：</p>
<ul>
  <li>反爬机制拦截（CloudFlare/WAF）</li>
  <li>需要登录验证</li>
  <li>网络超时</li>
</ul>
<p>建议手动访问 <a href="https://wellfound.com/startups/location/silicon-valley">wellfound 页面</a> 查看。</p>
<p>时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</body></html>"""
        with open("wellfound_report.html", "w", encoding="utf-8") as f:
            f.write(error_html)
        print("已生成错误报告: wellfound_report.html")
        return

    # 标准化字段
    field_map = {"name": "公司名称", "round": "融资轮次", "jobs": "招聘职位数"}
    rows = []
    for s in starters:
        rows.append({
            field_map["name"]: s.get("name", ""),
            field_map["round"]: s.get("round", ""),
            field_map["jobs"]: s.get("jobs", 0)
        })

    # 写入 CSV
    csv_file = "wellfound_silicon_valley.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(field_map.values()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV 已写入: {csv_file}")

    # 生成 HTML 报告
    table_rows = ""
    for i, r in enumerate(rows, 1):
        jobs = r["招聘职位数"]
        jobs_str = str(jobs) if jobs else "未显示"
        table_rows += f"<tr><td>{i}</td><td>{html.escape(r['公司名称'])}</td><td>{html.escape(r['融资轮次'])}</td><td>{jobs_str}</td></tr>\n"
    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Wellfound Silicon Valley Startups</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ color: #333; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #ddd; }}
th {{ background: #4A90E2; color: white; }}
tr:hover {{ background: #f5f5f5; }}
.summary {{ margin: 1rem 0; color: #666; }}
.footer {{ margin-top: 1.5rem; font-size: 0.9em; color: #999; }}
</style></head>
<body>
<h1>🏢 Wellfound 硅谷初创公司 Top 20</h1>
<p class="summary">抓取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据来源: {source}</p>
<table>
<thead><tr><th>#</th><th>公司名称</th><th>融资轮次</th><th>招聘职位数</th></tr></thead>
<tbody>
{table_rows}
</tbody>
</table>
<p class="footer">数据由自动脚本从 wellfound.com 抓取，可能存在延迟或缺失。</p>
</body></html>"""
    with open("wellfound_report.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML 报告已写入: wellfound_report.html")

    # 终端预览
    print("\n===== 前 5 行预览 =====")
    for r in rows[:5]:
        print(f"{r['公司名称'][:30]:30s} | {r['融资轮次']:15s} | 职位数: {r['招聘职位数']}")
    print(f"共 {len(rows)} 条记录。")

if __name__ == "__main__":
    main()
