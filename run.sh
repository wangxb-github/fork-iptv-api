#!/bin/bash
# iptv-api 手动更新脚本
# 用途：拉取 CCSH/IPTV 每日更新的候选接口，在本地严格测速，输出多格式结果文件
# 预计耗时：10-30 分钟（取决于网络）
#
# 用法：
#   ./run.sh         # 默认：完整测速后输出所有格式
#   ./run.sh quick   # 快速模式：关闭测速，立即输出（不推荐）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# pipenv 路径（Homebrew Python 3.13 用户安装）
export PATH="$HOME/Library/Python/3.13/bin:$PATH"

MODE="${1:-full}"

echo "=========================================="
echo "  iptv-api 手动更新脚本"
echo "=========================================="
echo "模式: $MODE"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 同步频道模板（从 CCSH 拉取全量分类）
echo "📥 同步频道模板..."
pipenv run python fetch_demo.py 2>&1 | tail -5
echo ""

# 检查输出目录
mkdir -p output/ipv4 output/ipv6 output/log output/data/epg output/data

# 启动更新
if [ "$MODE" = "quick" ]; then
    echo "⚠️  快速模式：关闭测速，立即输出（结果未筛选质量）"
    pipenv run python -c "
import asyncio
from main import UpdateSource
from utils.config import config
from utils import speed as speed_mod

# 临时关闭测速、全量测速
config.config.set('Settings', 'open_speed_test', 'False')
config.config.set('Settings', 'open_full_speed_test', 'False')

# Monkey-patch get_sort_result: quick 模式下不应用任何过滤
# （函数默认参数在 def 时锁定为 True，修改模块变量不生效，只能整体替换函数）
_orig_get_sort_result = speed_mod.get_sort_result
def _patched_get_sort_result(results, supply=False, filter_speed=False,
                              filter_resolution=False, **kwargs):
    # 强制关闭所有过滤
    return _orig_get_sort_result.__wrapped__(results, supply=False, filter_speed=False,
                                              filter_resolution=False, **kwargs) if hasattr(_orig_get_sort_result, '__wrapped__') else _orig_get_sort_result(results)
import functools
@functools.wraps(_orig_get_sort_result)
def _wrap(results, *args, **kwargs):
    return _orig_get_sort_result(results, supply=False, filter_speed=False,
                                  filter_resolution=False, **kwargs)
speed_mod.get_sort_result = _wrap
# channel.py 内部 'from utils.speed import get_sort_result'，需要同步替换
import utils.channel
utils.channel.get_sort_result = _wrap

async def run():
    update_source = UpdateSource()
    await update_source.start()

asyncio.run(run())
"
else
    echo "🚀 开始拉取候选接口 + 本地严格测速..."
    echo "   最低分辨率: 1080p | 最低速率: 1.0 MB/s | 并发: 10"
    echo "   预计耗时: 30-90 分钟（取决于网络和模板频道数）"
    echo "   等待进度条更新... (Ctrl+C 可随时取消)"
    echo ""
    pipenv run python main.py
fi

echo ""
echo "=========================================="
echo "  后处理：修复 m3u 文件中的 EPG URL..."
echo "=========================================="
# m3u 默认指向本机 192.168.x:5180，外部播放器无法访问。
# 替换为 CCSH/IPTV 的公开 EPG 地址，播放器可直接拉取。
for m3u in output/result.m3u output/ipv4/result.m3u output/ipv6/result.m3u; do
    if [ -f "$m3u" ]; then
        sed -i.bak 's|tvg-url="http://[^"]*"|tvg-url="https://raw.githubusercontent.com/CCSH/IPTV/refs/heads/main/e.xml.gz"|g' "$m3u"
        rm -f "${m3u}.bak"
    fi
done
echo "✅ EPG URL 已统一为 CCSH 公开地址"

echo ""
echo "=========================================="
echo "  ✅ 完成！输出文件："
echo "=========================================="

# 列出生成的输出文件
for f in output/result.txt output/result.m3u \
         output/ipv4/result.txt output/ipv4/result.m3u \
         output/ipv6/result.txt output/ipv6/result.m3u; do
    if [ -f "$f" ]; then
        size=$(du -h "$f" | cut -f1)
        if [[ "$f" == *.txt ]]; then
            # txt 格式：统计 "频道名,http..." 行
            count=$(awk -F',' 'NF==2 && $2 ~ /^http/ {n++} END{print n+0}' "$f")
        else
            # m3u 格式：统计以 http 开头的接口行
            count=$(grep -c "^http" "$f")
        fi
        echo "  ✅ $f  ($size, $count 个接口)"
    else
        echo "  ⚠️  $f  (未生成)"
    fi
done

echo ""
echo "  日志文件:"
for f in output/log/result.log output/log/speed_test.log output/log/statistic.log; do
    if [ -f "$f" ]; then
        echo "  📋 $f"
    fi
done
echo ""
echo "👉 在播放器中加载 output/result.m3u 即可观看（如需 ipv4 单独版本: output/ipv4/result.m3u）"