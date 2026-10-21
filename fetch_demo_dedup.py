#!/usr/bin/env python3
"""
fetch_demo_dedup.py - demo.txt 去重与归一化（后处理）

运行顺序：
    python fetch_demo.py          # 从 CCSH 同步基础分类
    python fetch_demo_extra.py    # 从 imDazui/suxuang 追加新频道
    python fetch_demo_dedup.py    # 本脚本：合并重复分类 + 补缺失 + 生成 alias

**关键设计**：
- demo.txt 必须保留**订阅源会用到的所有可能频道名**（否则 URL 匹配不上）
- 同一电视台的不同名字（繁体/简体/后缀）通过 `config/alias.txt` 归一到主名
- 这样 demo.txt 完整覆盖（避免丢 URL），result.txt 输出去重（避免重复频道）

本脚本只做**安全改动**：
1. 合并重复分类（5 对 → 5 个唯一名，频道做 union）
2. 补 Al Jazeera / 半岛 / France 24 / DW 等缺失频道 → 国际台
3. 扫描 demo.txt 找出"重复别名"对，追加到 config/alias.txt
   例如: demo.txt 里同时有 `凤凰中文` 和 `凤凰中文台`，会生成
        `凤凰中文,凤凰中文台,凤凰中文高清,凤凰卫视台,凤凰资讯,...`
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
ALIAS_PATH = os.path.join(SCRIPT_DIR, "config", "alias.txt")


# ============================
# 1) 重复分类合并
# ============================
CATEGORY_MERGE = {
    "内蒙频道": "内蒙古频道",
    "港澳台频道": "港澳台",
    "港澳代理": "港澳台",
    "NewTV频道": "NewTV",
    "国际频道": "国际台",
    "春晚": "春晚频道",
}


# ============================
# 2) 补缺失频道（imDazui 国外源）
# ============================
MISSING_TO_ADD = {
    "国际台": [
        "半岛电视台", "半岛电视台英文", "半岛新闻",
        "AlJazeera", "AlJazeeraEnglish",
        "France24English", "France24French", "France24Arabic",
        "DeutscheWelle", "TV5Monde",
        "BloombergOriginals", "BloombergAsia",
        "CartoonNetwork", "NatGeoWild", "NatGeoPeople",
        "Eurosport1", "Eurosport2",
    ],
}


# ============================
# 3) 显式别名映射（写死的高 ROI 映射）
# ============================
# 当 demo.txt 里同时出现 key 和 value 时，将 key 加为 value 的 alias
# 这样无论订阅源用 key 还是 value 都能匹配到 value（result.txt 用 value）
EXPLICIT_ALIAS = {
    # ---- TVB ----
    "TVB无线新闻（备用）": "TVB无线新闻",
    "TVB翡翠台（备用）": "TVB翡翠台",
    "TVB翡翠台1080P": "TVB翡翠台",
    "TVBPearl": "TVB明珠台",
    "TVBPlus": "TVBPlus",  # keep
    "TVB無線星河": "TVB无线星河",
    "TVBS亞洲": "TVBS亚洲",
    "TVBS新聞台": "TVBS新闻台",
    "TVBS精采台": "TVBS精彩台",
    "NOWNEWS": "NOW新闻",
    # ---- 八大 ----
    "GTV八大戲劇HD": "八大戏剧",
    "GTV八大第1台HD": "八大第一台",
    "GTV八大綜合台HD": "八大综合台",
    "八大戲劇": "八大戏剧",
    "八大第一": "八大第一台",
    "八大綜合": "八大综合",
    # ---- 三立 ----
    "SET三立戲劇": "三立戏剧",
    "三立台灣": "三立台湾",
    "三立新聞": "三立新闻",
    "三立綜合": "三立综合",
    "三立都會": "三立都会",
    # ---- 中天 ----
    "中天亞洲": "中天亚洲",
    "中天娱乐台": "中天娱乐",
    "中天新闻台": "中天新闻",
    "中天综合台": "中天综合",
    # ---- 靖天/纬来/AMC/HBO/CINEMA/ELEVEN/HISTORY ----
    "靖天電影": "靖天电影",
    "AMC電影台": "AMC电影台",
    "HITs電影頻道": "HITS电影频道",
    "HISTORY頻道": "HISTORY频道",
    "CINEMA-頻道": "CINEMA频道",
    "ELEVEN體育1": "ELEVEN体育1",
    "ELEVEN體育2": "ELEVEN体育2",
    "ELEVEN體育3": "ELEVEN体育3",
    # ---- Discovery/GOODTV/Mo/Nick ----
    "Discovery探索頻道": "Discovery探索",
    "Discovery探索亞洲": "Discovery探索亚洲",
    "GOODTV好消息HD": "GOODTV好消息",
    "GOODTV復興禱告": "GOODTV复兴祷告",
    "GOODTV經典音樂河HD": "GOODTV经典音乐河",
    "GOODTV道在人間HD": "GOODTV道在人间",
    "Mo綜合": "Mo综合",
    "Nick綜合": "Nick综合",
    # ---- 凤凰 ----
    "凤凰中文台": "凤凰中文",
    "凤凰资讯台": "凤凰资讯",
    "凤凰中文高清": "凤凰中文",
    "凤凰资讯高清": "凤凰资讯",
    "凤凰香港高清": "凤凰香港",
    "凤凰卫视台": "凤凰卫视",
    "凤凰香港台": "凤凰香港",
}


# ============================
# 主流程
# ============================
def read_demo() -> "OrderedDict[str, list[str]]":
    genres = OrderedDict()
    current = None
    with open(DEMO_PATH, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\r\n").strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith(",#genre#"):
                current = line.replace(",#genre#", "").strip()
                genres.setdefault(current, [])
                continue
            if current is not None:
                genres[current].append(line)
    return genres


def write_demo(genres: "OrderedDict[str, list[str]]") -> None:
    backup = DEMO_PATH + ".bak"
    if os.path.exists(DEMO_PATH):
        import shutil
        shutil.copy2(DEMO_PATH, backup)

    with open(DEMO_PATH, "w", encoding="utf-8") as f:
        f.write("# 此文件由 fetch_demo.py + fetch_demo_extra.py + fetch_demo_dedup.py 自动维护\n")
        f.write("# fetch_demo.py: 从 CCSH 拉取基础分类\n")
        f.write("# fetch_demo_extra.py: 从 imDazui / suxuang 等源追加新频道到合适分类\n")
        f.write("# fetch_demo_dedup.py: 合并重复分类 + 补缺失 + 生成 alias\n")
        f.write("# 同一电视台的多个名字（繁简/后缀）通过 config/alias.txt 归一到主名\n\n")

        for genre, chans in genres.items():
            seen = set()
            unique_chans = []
            for c in chans:
                if c not in seen:
                    seen.add(c)
                    unique_chans.append(c)
            if not unique_chans:
                continue
            f.write(f"{genre},#genre#\n")
            for name in unique_chans:
                f.write(f"{name}\n")
            f.write("\n")

    print(f"💾 已写入 {DEMO_PATH}")
    if os.path.exists(backup):
        os.remove(backup)


def merge_categories(genres: "OrderedDict[str, list[str]]") -> dict[str, int]:
    additions = {target: 0 for target in set(CATEGORY_MERGE.values())}
    for old, new in CATEGORY_MERGE.items():
        if old in genres and old != new:
            if new not in genres:
                genres[new] = []
            before = len(genres[new])
            genres[new].extend(genres[old])
            additions[new] += len(genres[new]) - before
            del genres[old]
    return additions


def add_missing(genres: "OrderedDict[str, list[str]]") -> dict[str, int]:
    additions = {}
    for genre, names in MISSING_TO_ADD.items():
        if genre not in genres:
            genres[genre] = []
        before = len(genres[genre])
        existing = set(genres[genre])
        for n in names:
            if n not in existing:
                genres[genre].append(n)
                existing.add(n)
        additions[genre] = len(genres[genre]) - before
    return additions


def append_alias_entries(new_aliases: list[tuple[str, set[str]]]) -> int:
    """追加 alias 条目到 config/alias.txt
    new_aliases: [(primary_name, {alias1, alias2}), ...]
    返回实际追加条数
    """
    if not new_aliases or not os.path.exists(ALIAS_PATH):
        return 0

    new_alias_dict: dict[str, set[str]] = {}
    for primary, aliases in new_aliases:
        if primary and aliases:
            new_alias_dict[primary] = set(aliases)

    with open(ALIAS_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    modified_lines = []
    added = 0
    handled_primaries = set()

    for line in lines:
        stripped = line.rstrip("\r\n")
        if not stripped or stripped.startswith("#") or "," not in stripped:
            modified_lines.append(line)
            continue
        parts = stripped.split(",")
        primary = parts[0].strip()
        existing_aliases = [p.strip() for p in parts[1:] if p.strip()]
        existing_set = set(existing_aliases)
        handled_primaries.add(primary)

        if primary in new_alias_dict:
            new_set = new_alias_dict[primary] - existing_set - {primary}
            if new_set:
                updated_aliases = existing_aliases + sorted(new_set)
                modified_lines.append(f"{primary},{','.join(updated_aliases)}\n")
                added += 1
                continue
        modified_lines.append(line)

    # Primaries not in existing file:
    for primary, aliases in new_alias_dict.items():
        if primary not in handled_primaries:
            unique_aliases = sorted(aliases - {primary})
            if unique_aliases:
                modified_lines.append(f"{primary},{','.join(unique_aliases)}\n")
                added += 1

    if added > 0:
        with open(ALIAS_PATH, "w", encoding="utf-8") as f:
            f.writelines(modified_lines)
        print(f"💾 已更新 {ALIAS_PATH}（追加 {added} 个 primary 条目）")

    return added


def build_alias_from_demo(genres: "OrderedDict[str, list[str]]") -> list[tuple[str, set[str]]]:
    """扫描 demo.txt，根据 EXPLICIT_ALIAS 找出可生成的 alias 条目
    只有当 primary 和 alias 在 demo.txt 同一分类下同时存在，才生成 alias
    """
    # 构建 {category: set(names)} 索引
    cat_to_names: dict[str, set[str]] = {}
    for cat, chans in genres.items():
        cat_to_names[cat] = set(chans)

    # 收集 primary → aliases
    primary_to_aliases: dict[str, set[str]] = {}
    for cat, names in cat_to_names.items():
        for alias_key, primary in EXPLICIT_ALIAS.items():
            if alias_key == primary:
                continue  # skip self-mapping
            if alias_key in names and primary in names:
                primary_to_aliases.setdefault(primary, set()).add(alias_key)

    return [(p, a) for p, a in primary_to_aliases.items()]


def main():
    print(f"📂 读取 {DEMO_PATH} ...")
    genres = read_demo()
    initial_total = sum(len(v) for v in genres.values())
    initial_cats = len(genres)
    print(f"   当前: {initial_cats} 分类, {initial_total} 频道\n")

    # Step 1: 合并重复分类
    print("🔧 Step 1: 合并重复分类 ...")
    added = merge_categories(genres)
    for cat, n in added.items():
        if n:
            print(f"   ✓ {cat}: 合并新增 {n} 频道")
    print(f"   当前: {len(genres)} 分类\n")

    # Step 2: 补缺失
    print("🔧 Step 2: 补缺失频道（Al Jazeera / 半岛 / France 24 / DW 等）...")
    additions = add_missing(genres)
    for cat, n in additions.items():
        if n:
            print(f"   ✓ {cat}: 新增 {n} 频道")
    print()

    # Step 3: 生成 alias 条目
    print("🔧 Step 3: 扫描 demo.txt 生成 alias 条目 ...")
    new_aliases = build_alias_from_demo(genres)
    if new_aliases:
        for primary, aliases in new_aliases:
            print(f"   ✓ {primary}: +{len(aliases)} 别名")
    added_alias = append_alias_entries(new_aliases)
    print(f"   共追加 {added_alias} 个 primary 别名条目到 config/alias.txt\n")

    # 写回
    write_demo(genres)

    # 验证
    final = read_demo()
    final_total = sum(len(v) for v in final.values())
    final_cats = len(final)
    print()
    print(f"✅ 完成: {initial_cats} 分类 → {final_cats} 分类; {initial_total} 频道 → {final_total} 频道")
    delta = final_total - initial_total
    if delta < 0:
        print(f"   净减少 {abs(delta)} 频道（仅合并分类，不删除别名）")
    elif delta > 0:
        print(f"   净增加 {delta} 频道（补缺失为主）")
    else:
        print(f"   频道总数不变")

    print()
    print(f"📊 最终分类速览（前 20）:")
    for g, chans in list(final.items())[:20]:
        marker = " ← 合并过" if g in CATEGORY_MERGE.values() else ""
        print(f"   {len(chans):>4}  {g}{marker}")


if __name__ == "__main__":
    main()