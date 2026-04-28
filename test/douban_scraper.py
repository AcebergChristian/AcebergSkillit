import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

url = "https://movie.douban.com/top250"
resp = requests.get(url, headers=headers)
resp.encoding = "utf-8"

soup = BeautifulSoup(resp.text, "html.parser")
items = soup.select(".item")

for item in items:
    title = item.select_one(".title").text
    rating = item.select_one(".rating_num").text
    print(f"{title} - {rating}")
