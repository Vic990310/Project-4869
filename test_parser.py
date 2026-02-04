
from utils.parser import parse_title

title = "1190 消失于恋谷桥的恋人（鸟取周游篇） - 1080P·简日MP4 [2026/01/25]"
parsed = parse_title(title)
print(f"Title: {title}")
print(f"Parsed: {parsed}")

title2 = "Movie 27 100万美元的五棱星 - 4K·简日MKV"
parsed2 = parse_title(title2)
print(f"Title: {title2}")
print(f"Parsed: {parsed2}")
