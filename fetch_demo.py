#!/usr/bin/env python3
"""
从 CCSH/IPTV 拉取最新分类和频道，生成全量 demo.txt
每天 CCSH 04:00 自动更新，这里只是把全部分类同步到本地 demo.txt
"""
import os
import sys
import urllib.request
from collections import OrderedDict

CCSH_LIVE_URL = "https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/live.txt"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "config", "demo.txt")

# 不需要的分类（质量差或非电视台）
EXCLUDED_GENRES = {
    "更新时间",        # 元信息行
    "MTV",            # CCSH 这里的 MTV 实为 DJ 舞曲、伤感歌曲
    "直播中国",       # 实为直播类内容，质量参差
    "iHOT",           # 空分类
    "埋堆堆",         # 空分类
    "音乐频道",       # 空分类
    "云南频道",       # 空分类
    "宁夏频道",       # 空分类
}


def fetch_live_txt() -> str:
    req = urllib.request.Request(CCSH_LIVE_URL, headers={"User-Agent": "iptv-api-fetch-demo/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(content: str) -> "OrderedDict[str, list[str]]":
    """按 #genre# 分类解析，返回 {分类名: [频道1, 频道2, ...]}"""
    genres: "OrderedDict[str, list[str]]" = OrderedDict()
    current = "其他"
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "#genre#" in line:
            current = line.replace(",#genre#", "").strip()
            genres.setdefault(current, [])
            continue
        # 跳过更新时间行（频道名是日期）
        if "," not in line:
            continue
        name, url = line.split(",", 1)
        name, url = name.strip(), url.strip()
        if not name or not url.startswith("http"):
            continue
        # 时间戳行：name 是 YYYYMMDD HH:MM
        if name[:8].isdigit():
            continue
        # 同分类去重
        if name not in genres[current]:
            genres[current].append(name)
    return genres


def main():
    print(f"📥 拉取 {CCSH_LIVE_URL} ...")
    try:
        content = fetch_live_txt()
    except Exception as e:
        print(f"❌ 拉取失败: {e}", file=sys.stderr)
        print("   保留现有 demo.txt 不动", file=sys.stderr)
        sys.exit(1)

    genres = parse(content)
    # 过滤掉低质量/空分类
    skipped = sum(1 for g in genres if g in EXCLUDED_GENRES)
    for g in EXCLUDED_GENRES:
        genres.pop(g, None)
    # 删除空分类
    genres = OrderedDict((g, chans) for g, chans in genres.items() if chans)
    total = sum(len(v) for v in genres.values())
    print(f"✅ 解析完成: 保留 {len(genres)} 个分类, 跳过 {skipped} 个低质量分类")
    print(f"   共 {total} 个不同频道")

    # 写 demo.txt
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("# 此文件由 fetch_demo.py 自动从 CCSH/IPTV 同步\n")
        f.write("# 每天 04:00 CCSH 会更新上游列表；本地由 ./run.sh 触发同步\n")
        f.write("# 已过滤低质量分类（MTV=DJ舞曲、直播中国等）\n")
        f.write("# 分类顺序按 CCSH 原顺序保留\n\n")
        for genre, chans in genres.items():
            if not chans:
                continue
            f.write(f"{genre},#genre#\n")
            for name in chans:
                f.write(f"{name}\n")
            f.write("\n")

    print(f"💾 已写入 {OUTPUT_PATH} ({len(genres)} 个分类, {total} 个频道)")
    print()
    print("📊 保留的分类:")
    for genre, chans in genres.items():
        if chans:
            print(f"   {len(chans):>4}  {genre}")
    print()
    print(f"⏭️  跳过的低质量分类: {', '.join(sorted(EXCLUDED_GENRES))}")


if __name__ == "__main__":
    main()
