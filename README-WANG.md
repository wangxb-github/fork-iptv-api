# 我的 IPTV 配置

基于 Guovin/iptv-api + CCSH/IPTV。每天从 CCSH 拉 ~1300 个候选接口，在本地 Mac 严格测速（1080p + 1MB/s），输出多格式结果。

**完全不自动运行**，想用就手动跑。

---

## ⏱️ 执行时间（实测）

| 模式 | 命令 | 耗时 | 测速接口数 | 通过数 | 适用场景 |
|---|---|---|---|---|---|
| 完整（685 频道全模板） | `./run.sh` | **~60 分钟** | 4331 | **429** | 想看全部：央视/卫视/各省/电影/电视剧/体育/解说/儿童/动漫 |
| 精简（74 频道默认模板） | `./run.sh` | ~17 分钟 | 1300 | 142 | 只看电视台，30+ 频道即可 |
| 快速（不测速） | `./run.sh quick` | **10 秒** | 0（全保留） | ~1500 | 验证脚本/查频道名/调试用 |

> 💡 想覆盖电影/电视剧/动漫等非电视台，必须用 685 频道的全量模板。耗时从 17 分钟增加到 60 分钟，但通过接口数从 142 提升到 **429**（3 倍）。

---

## 跑

```bash
cd /Users/wangxiaobin/Documents/work/github/iptv-api
./run.sh         # 完整测速，约 60 分钟（实测）
./run.sh quick   # 不测速，10 秒出结果
```

`./run.sh` 自动做两件事：
1. 从 CCSH 拉取当天最新频道模板（每天 04:00 CCSH 自动更新），写入 `config/demo.txt`
2. 跑 Guovin 主程序，本地 Mac 严格测速，输出多格式结果

## 输出

`output/` 下有 6 个文件。把 `output/result.m3u` 拖进播放器（VLC/IINA/TVBox/PotPlayer）即可。

其他文件：`result.txt`（txt 格式）、`ipv4/result.{m3u,txt}`、`ipv6/result.{m3u,txt}`。

## 改配置

| 想改什么 | 改哪里 |
|---|---|
| 频道列表 | `config/demo.txt`（默认全量 685 频道；想精简就恢复成原版 74 频道） |
| 测速严格度 | `config/user_config.ini`（`min_resolution` / `min_speed`） |
| 加本地接口（白名单） | `config/local.txt`：`频道名,URL$!` |
| 屏蔽关键字 | `config/blacklist.txt` |
| 订阅源 | `config/subscribe.txt`（默认指向 CCSH live.txt） |
| 跳过低质量分类 | `fetch_demo.py` 顶部的 `EXCLUDED_GENRES`（默认已排除 MTV/直播中国 等） |

改完再跑 `./run.sh` 生效。

## 故障排查

- **结果空**：严格模式过滤太多 → 把 `min_speed` / `min_resolution` 调低
- **跑太久**：把 `speed_test_limit` 调大（默认 10），或关掉 `open_filter_resolution`
- **想只看电视台不跑电影**：把 `fetch_demo.py` 的 `EXCLUDED_GENRES` 加上 `电影/电视剧/综艺频道/解说频道/儿童频道/NewTV`，并恢复默认 demo.txt
- **想回滚默认配置**：`cp config/config.ini.bak config/config.ini`

## 更新工具

```bash
git pull   # 冲突时保留 config/user_config.ini 和 config/subscribe.txt
```