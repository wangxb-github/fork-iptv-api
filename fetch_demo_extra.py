#!/usr/bin/env python3
"""
从附加订阅源（imDazui / suxuang 等）拉取新增频道，扩展 demo.txt
- 不覆盖 fetch_demo.py 从 CCSH 同步的基础分类
- 只追加新频道到合适的分类
- 由 ./run.sh 在 fetch_demo.py 之后自动调用
"""
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections import OrderedDict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_PATH = os.path.join(SCRIPT_DIR, "config", "demo.txt")
UA = "iptv-api-fetch-demo-extra/1.0"


def cache_bust(url: str) -> str:
    """Append nocache=<ts> to force jsDelivr origin fetch"""
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}nocache={int(time.time())}"


def fetch(url: str, timeout: int = 30) -> str:
    """通过 curl 拉取（避免 Python urllib 对中文 URL 的编码问题）"""
    encoded = urllib.parse.quote(url, safe=":/?&=#@!$%'()*+,;~")  # 保留结构性字符
    busted = cache_bust(url)
    try:
        out = subprocess.check_output(
            ["curl", "-sLm", str(timeout), "-A", UA, busted],
            stderr=subprocess.DEVNULL,
        )
        return out.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        print(f"   ⚠️  拉取失败: {url[:80]}... ({e})", file=sys.stderr)
        return ""


def normalize_category(name: str) -> str:
    """去掉分类名前缀的 emoji 和装饰（'☘️上海频道' → '上海频道'），
    折叠空白，让 suxuang 的 group-title 能匹配 demo.txt 里的分类。"""
    # 去透前后空白
    name = name.strip()
    # 去透开头的 emoji 和符号 + 空格（如果还有 emoji, punctuation, 或 space/flex）
    name = re.sub(r"^[\U0001F300-\U0001F9FF\U00002600-\U000027BF\u2728\u2705\u2702-\u27B0\u26A1\u2728\u2B50\u2B55\u2934\u2935\u2B05-\u2B07\u2B1B\u2B1C\u2B50\u2B55\u231A\u231B\u23E9-\u23F3\u23F8-\u23FA\ufe0f\s\ufe0f]+",
                  "", name, flags=re.UNICODE).strip()
    # 折叠中间多个空白为一个
    name = re.sub(r"\s+", "", name)
    return name



def parse_m3u(content: str) -> list[tuple[str, str]]:
    """从 m3u 提取 (频道名, group-title)"""
    items = []
    current_group = ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("#EXTGRP"):
            current_group = line.split(":", 1)[-1].strip()
        elif line.startswith("#EXTINF"):
            # 解析 group-title="..." ,  频道名
            m = re.search(r'group-title="([^"]*)"', line)
            if m:
                current_group = m.group(1)
            if "," in line:
                name = line.rsplit(",", 1)[-1].strip()
                # 清理中括号尾部的分辨率标注 [720*404]
                name = re.sub(r"\[\d+\*\d+\].*$", "", name).strip()
                # 清理尾部 (720p) / (1080p) / [Not 24/7]
                name = re.sub(r"[\[(](?:720p|1080p|480p|576p|2160p|4K|NOT 24/7|WEB)[^]]*[\])]\s*$",
                              "", name, flags=re.IGNORECASE).strip()
                # 折叠多余空白（suxuang 的 "NewTV 东北热剧" 和 imDazui 的 "NewTV东北热剧" 统一）
                name = re.sub(r"\s+", "", name)
                if name:
                    items.append((name, current_group))
    return items


def parse_txt(content: str) -> list[tuple[str, str]]:
    """从 vbskycn 的 txt 格式提取 (频道名, genre)。
    格式: Name,#genre#  换行  ChannelName,URL"""
    items = []
    current_genre = ""
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # 分类标记: XXX频道,#genre#
        if line.endswith(",#genre#"):
            current_genre = line.replace(",#genre#", "").strip()
            continue
        # 频道行: ChannelName,URL
        if "," in line:
            name = line.split(",", 1)[0].strip()
            # 跳过时间戳
            if name[:8].isdigit():
                continue
            if name:
                items.append((name, current_genre))
    return items


# ============================
# 扩展源 → (url, format, 目标分类策略)
# ============================
# 策略分三类：
#   "category": 固定归入 demo.txt 的某个分类（用于 NewTV/港澳台/国际台）
#   "group_title": 用 m3u 自带的 group-title（用于 suxuang 带分组的 4K 频道）
#   "province": 启发式按省份归入对应省级分类（用于国内地方台）
# ============================
EXTRA_SOURCES = [
    # ---- NewTV/SiTV/华数/黑莓 轮播频道 → 归入 NewTV 分类 ----
    {
        "url": "https://cdn.jsdelivr.net/gh/imDazui/Tvlist-awesome-m3u-m3u8@master/m3u/轮播_华数.黑莓.NewTV.SiTV.CIBN.m3u",
        "format": "m3u",
        "strategy": "category",
        "category": "NewTV",
        "filter": lambda n: (n.startswith("NewTV") or n.startswith("SiTV")
                            or n.startswith("华数") or n.startswith("黑莓")
                            or n.startswith("CIBN")),
    },
    # ---- imDazui 港澳台 → 归入 港澳台 分类 ----
    {
        "url": "https://cdn.jsdelivr.net/gh/imDazui/Tvlist-awesome-m3u-m3u8@master/m3u/台湾香港澳门202506.m3u",
        "format": "m3u",
        "strategy": "category",
        "category": "港澳台",
    },
    # ---- imDazui 国外 → 归入 国际台 分类（仅取主流英文/华语频道，避开大量小语种） ----
    {
        "url": "https://cdn.jsdelivr.net/gh/imDazui/Tvlist-awesome-m3u-m3u8@master/m3u/国外电视台202409.m3u",
        "format": "m3u",
        "strategy": "category",
        "category": "国际台",
        # 提取知名英文/华语台（避免大量小语种/低质量台占位）
        "filter": lambda n: (re.match(r"^(\[)?(BBC|CNN|Fox|CNBC|NHK|Discovery|ESPN|NBC|CBS|ABC|Sky|Bloomberg|Al Jazeera|France|DW|ITV|Channel|Cartoon|MTV|Eurosport|Animax|Star Sports|Astro|RT)[^\]]*\]?",
                                     n, re.IGNORECASE)
                          or n.startswith("[美国]") or n.startswith("[英国]")
                          or n.startswith("[日本]") or n.startswith("[韩国]")
                          or "TVBS" in n or "TVB" in n or "凤凰" in n or "TVB8" in n),
    },
    # ---- suxuang/myIPTV → 用 m3u 自带的 group-title(4K频道/央视频道/...) ----
    {
        "url": "https://cdn.jsdelivr.net/gh/suxuang/myIPTV@main/ipv4.m3u",
        "format": "m3u",
        "strategy": "group_title",
        # 保留的 group-title → demo 中的目标分类映射
        "group_mapping": {
            "4K频道": "4K频道",     # 新建 "4K频道" 分类
            "央视频道": "央视频道",  # 已存在，自动加入
            "卫视频道": "卫视频道",
            "电影频道": "电影",     # 注: m3u 用 "电影频道"，demo 用 "电影"
            "电视剧频道": "电视剧",
            "综艺频道": "综艺频道",
            "体育频道": "体育频道",
            "港澳台": "港澳台",
            "国际": "国际台",
        },
    },
    # ---- imDazui 国内 1063 → 不全量加入，按省份启发式归入省级分类 ----
    # 不适合全量: 太多小县城台，反而稀释；只在 demo 没有的、且命名规则的少数
    # (暂不启用，留 hook 给未来需要时手动启用)
]


def read_existing_demo() -> "OrderedDict[str, set[str]]":
    """读现有 demo.txt → {分类: {频道名集合}}"""
    genres = OrderedDict()
    current = None
    with open(DEMO_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\r\n").strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith(",#genre#"):
                current = line.replace(",#genre#", "").strip()
                genres.setdefault(current, set())
                continue
            if current is not None:
                genres[current].add(line)
    return genres


def write_demo(genres: "OrderedDict[str, set[str]]", added: dict[str, list[str]]) -> None:
    """写回 demo.txt（保留原 CCSH 同步分类，新增追加在末尾）"""
    # 先备份
    backup = DEMO_PATH + ".bak"
    if os.path.exists(DEMO_PATH):
        import shutil
        shutil.copy2(DEMO_PATH, backup)

    existing_categories = list(genres.keys())
    with open(DEMO_PATH, "w", encoding="utf-8") as f:
        f.write("# 此文件由 fetch_demo.py + fetch_demo_extra.py 自动维护\n")
        f.write("# fetch_demo.py: 从 CCSH 拉取基础分类\n")
        f.write("# fetch_demo_extra.py: 从 imDazui / suxuang 等源追加新频道到合适分类\n")
        f.write("# 由 ./run.sh 在跑 main.py 前自动调用\n\n")

        # ---- 写原有分类（CCSH 同步来的）----
        for genre in existing_categories:
            chans = sorted(genres[genre], key=lambda x: (
                # 排序: 数字优先（CCTV1 < CCTV2 < ... < CCTV10）, 字母第二
                (int(re.match(r'^(\d+)', x).group(1)) if re.match(r'^\d', x) else 9999),
                x,
            ))
            if not chans:
                continue
            f.write(f"{genre},#genre#\n")
            for name in chans:
                f.write(f"{name}\n")
            f.write("\n")

        # ---- 追加：新增分类（demo.txt 原有的分类里被加进新频道的，单独列出）----
        # 注意: 上述 for 循环中 sort 后写出的就是已合并新频道后的内容
        # 这里只需写"全新分类"（demo.txt 原本没有的）
        # tracked via 'added' parameter

        new_only = {k: v for k, v in added.items() if k not in existing_categories}
        if new_only:
            f.write("\n# ===== 以下由 fetch_demo_extra.py 从附加源追加 =====\n\n")
            for genre in sorted(new_only.keys()):
                chans = sorted(set(new_only[genre]))
                if not chans:
                    continue
                f.write(f"{genre},#genre#\n")
                for name in chans:
                    f.write(f"{name}\n")
                f.write("\n")


    print(f"💾 已写入 {DEMO_PATH}")
    if os.path.exists(backup):
        os.remove(backup)


def main():
    print(f"📥 从 {len(EXTRA_SOURCES)} 个附加源拉取频道...")
    existing = read_existing_demo()
    all_known = set().union(*existing.values()) if existing else set()
    print(f"   demo.txt 现有 {len(existing)} 个分类, {len(all_known)} 个频道")

    added: "OrderedDict[str, list[str]]" = OrderedDict()
    for src in EXTRA_SOURCES:
        label = src["url"].rstrip("/").split("/")[-1][:40]
        print(f"   拉取: {label}")
        content = fetch(src["url"])
        if not content:
            continue
        items = parse_m3u(content) if src["format"] == "m3u" else parse_txt(content)

        # 按策略分组
        for name, group in items:
            if not name or name in all_known:
                continue

            flt = src.get("filter")
            if flt and not flt(name):
                continue

            target = None
            if src["strategy"] == "category":
                target = src["category"]
            elif src["strategy"] == "group_title":
                target = src.get("group_mapping", {}).get(group, group)
                # 归一化 category：去掉 suxuang 的 emoji 前缀 ☘️🔥 等
                target = normalize_category(target)
            if not target:
                continue

            added.setdefault(target, []).append(name)
            all_known.add(name)

    # 统计
    print()
    print(f"✅ 拉取完成: 共追加 {sum(len(v) for v in added.values())} 个新频道到 {len(added)} 个分类\n")
    if added:
        print(f"📊 分类统计:")
        for g in sorted(added.keys()):
            chans = sorted(set(added[g]))
            print(f"   {len(chans):>4}  {g}")
            # 显示前 3 个
            for c in chans[:3]:
                print(f"        - {c}")
            if len(chans) > 3:
                print(f"        ... (+{len(chans)-3})")
        print()

    # 合并到现有分类
    for g, names in added.items():
        existing.setdefault(g, set()).update(names)

    write_demo(existing, added)
    print()
    print("🎯 验证: 重新读取 demo.txt...")
    final = read_existing_demo()
    final_total = sum(len(v) for v in final.values())
    print(f"   共 {len(final)} 个分类, {final_total} 个频道")
    print(f"   新增: {final_total - len(all_known) + sum(len(v) for v in added.values())} 个频道")


if __name__ == "__main__":
    main()
