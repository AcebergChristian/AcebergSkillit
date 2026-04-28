import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

# 获取新浪新闻首页
url = "https://news.sina.com.cn/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

response = requests.get(url, headers=headers, timeout=10)
response.encoding = 'utf-8'

soup = BeautifulSoup(response.text, 'html.parser')

# 提取新闻数据
news_list = []
articles = soup.select('a[target="_blank"]')

for article in articles:
    title = article.get_text(strip=True)
    href = article.get('href', '')
    if title and len(title) > 5 and href.startswith('http'):
        news_list.append({
            '标题': title,
            '链接': href,
            '抓取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

# 去重并限制条数
seen = set()
unique_news = []
for item in news_list:
    if item['标题'] not in seen and len(unique_news) < 20:
        seen.add(item['标题'])
        unique_news.append(item)

# 保存到Excel
df = pd.DataFrame(unique_news)
df.to_excel('sina_news_today.xlsx', index=False)
print(f"成功导出 {len(unique_news)} 条新浪新闻到 sina_news_today.xlsx")
