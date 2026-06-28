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

## 🚀 自动 push 到 GitHub（**新功能**）

`./run.sh` 跑完后**自动**把结果推到 GitHub。你可以通过固定链接获取最新测速列表，配置到其他工具里。

### 固定链接（不变，永久可用）

```
https://raw.githubusercontent.com/wangxb-github/fork-iptv-api/master/live/result.m3u
https://cdn.jsdelivr.net/gh/wangxb-github/fork-iptv-api@master/live/result.m3u
```

- **raw** 链接：GitHub 直链，~几秒延迟
- **jsdelivr** 链接：CDN 加速，**有 12 小时缓存**（需要最新数据时用 raw）

其他可用文件：`live/result.txt`、`live/ipv4/result.m3u`、`live/ipv4/result.txt`、`live/ipv6/result.{m3u,txt}`。

### 工作原理

1. 本地测速完成后，run.sh 调用 push.sh
2. push.sh 把 `output/result.m3u` 等 6 个文件复制到 `live/` 目录
3. 自动 `git add live/ + commit + push`（commit message 含日期 + 接口数）
4. 你就能从固定 URL 拿到最新列表

### 配置 push（可选）

`push_config.ini` 控制：
- `target_branch` 推哪个分支（默认 `master`）
- `git_user_name` / `git_user_email` 提交者（必须和 SSH key 关联的 GitHub 账号一致）
- `publish_files` 要发布的文件列表（管道分隔）
- `auto_pull` push 前自动拉取远端
- `auto_rollback` push 失败时自动回滚 commit

跳过 push：`SKIP_PUSH=1 ./run.sh`

---

## 跑

```bash
cd /Users/wangxiaobin/Documents/work/github/fork-iptv-api
./run.sh         # 完整测速，约 60 分钟，**跑完自动 push 到 GitHub**
./run.sh quick   # 不测速，10 秒出结果，跑完自动 push
```

`./run.sh` 自动做的事：
1. 从 CCSH 拉取当天最新频道模板（每天 04:00 CCSH 自动更新），写入 `config/demo.txt`
2. 跑 Guovin 主程序，本地 Mac 严格测速，输出多格式结果
3. **自动 push 结果到 GitHub**（无变化时不 push）

## 输出

### 本地（`output/`，已加入 .gitignore，不上传）

6 个文件：`result.{txt,m3u}`、`ipv4/result.{txt,m3u}`、`ipv6/result.{txt,m3u}`。把 `output/result.m3u` 拖进播放器（VLC/IINA/TVBox/PotPlayer）即可。

### 远端（`live/`，推送到 GitHub）

通过固定链接（见上）访问。

## 改配置

| 想改什么 | 改哪里 |
|---|---|
| 频道列表 | `config/demo.txt`（默认全量 685 频道） |
| 测速严格度 | `config/user_config.ini`（`min_resolution` / `min_speed`） |
| 分类放宽到 720p | `config/user_config.ini` 的 `category_min_resolution_overrides` |
| 加本地接口（白名单） | `config/local.txt`：`频道名,URL$!` |
| 屏蔽关键字 | `config/blacklist.txt` |
| 订阅源 | `config/subscribe.txt`（默认指向 CCSH live.txt） |
| 跳过低质量分类 | `fetch_demo.py` 顶部的 `EXCLUDED_GENRES` |
| Push 配置 | `push_config.ini`（分支、提交者、发布文件） |

改完再跑 `./run.sh` 生效。

## 故障排查

- **结果空**：严格模式过滤太多 → 把 `min_speed` / `min_resolution` 调低
- **跑太久**：把 `speed_test_limit` 调大（默认 10），或关掉 `open_filter_resolution`
- **Push 失败**：检查 SSH key 是否配置（`ssh -T git@github.com`）
- **想回滚默认配置**：`git checkout config/config.ini`（注：原版 `config.ini.bak` 已清理）

## 更新工具

```bash
git pull   # 冲突时保留 config/user_config.ini 和 config/subscribe.txt
```
