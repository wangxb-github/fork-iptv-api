#!/bin/bash
# 自动 push 脚本：把 output/ 下的最新结果复制到 live/，commit 并 push 到 GitHub
# 用法：./push.sh
#      或被 run.sh 在测速完成后自动调用

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 读取配置
CONFIG_FILE="$SCRIPT_DIR/push_config.ini"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ 找不到 $CONFIG_FILE" >&2
    exit 1
fi

get_config() {
    grep "^$1" "$CONFIG_FILE" | head -1 | sed 's/^[^=]*=[[:space:]]*//' | sed 's/[[:space:]]*$//'
}

TARGET_BRANCH=$(get_config "target_branch")
GIT_USER_NAME=$(get_config "git_user_name")
GIT_USER_EMAIL=$(get_config "git_user_email")
MSG_TEMPLATE=$(get_config "commit_message_template")
PUBLISH_DIR=$(get_config "publish_dir")
AUTO_PULL=$(get_config "auto_pull")
AUTO_ROLLBACK=$(get_config "auto_rollback")

# 收集 publish_files（多行值）
PUBLISH_FILES=()
# publish_files 是单行管道分隔格式：file1|file2|file3
_raw_files=$(grep "^publish_files" "$CONFIG_FILE" | head -1 | sed 's/^[^=]*=[[:space:]]*//' | sed 's/[[:space:]]*$//')
if [ -n "$_raw_files" ]; then
    IFS='|' read -ra PUBLISH_FILES <<< "$_raw_files"
fi

if [ ${#PUBLISH_FILES[@]} -eq 0 ]; then
    echo "❌ 配置文件中 publish_files 为空" >&2
    exit 1
fi

echo "=========================================="
echo "  📤 自动 push 到 GitHub"
echo "=========================================="
echo "目标分支: $TARGET_BRANCH"
echo "发布目录: $PUBLISH_DIR/"
echo "文件数:   ${#PUBLISH_FILES[@]}"
echo ""

# 检查 git 状态
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ 当前目录不是 git 仓库" >&2
    exit 1
fi

# 创建发布目录
mkdir -p "$PUBLISH_DIR"

# 1. 复制结果文件到 publish_dir
echo "📋 复制结果文件..."
total_count=0
for src in "${PUBLISH_FILES[@]}"; do
    src_path="output/$src"
    dst_path="$PUBLISH_DIR/$(basename "$(dirname "$src")")/$(basename "$src")"
    # 处理 ipv4/ipv6 子目录：保留子目录结构
    src_dir=$(dirname "$src")
    if [ "$src_dir" != "." ]; then
        dst_path="$PUBLISH_DIR/$src"
        mkdir -p "$(dirname "$dst_path")"
    else
        dst_path="$PUBLISH_DIR/$src"
    fi

    if [ ! -f "$src_path" ]; then
        echo "  ⚠️  跳过（不存在）: $src_path"
        continue
    fi
    cp -f "$src_path" "$dst_path"
    # 数接口数（仅对 m3u/txt）
    # 用 awk 避免 grep -c 无匹配时退出码 1 触发算术表达式错误
    if [[ "$src" == *.m3u ]]; then
        c=$(awk '/^http/ {n++} END{print n+0}' "$dst_path")
    else
        c=$(awk -F',' 'NF==2 && $2 ~ /^http/ {n++} END{print n+0}' "$dst_path")
    fi
    total_count=$((total_count + c))
    echo "  ✅ $src_path → $dst_path ($c)"
done
echo "  → 总接口数: $total_count"
echo ""

# 2. 检测是否有变化
if [ -z "$(git status --porcelain "$PUBLISH_DIR/" 2>/dev/null)" ]; then
    echo "ℹ️  无变化（live/ 目录与上次一致），无需 push"
    exit 0
fi

echo "📝 检测到 live/ 有变化，准备 commit + push"

# 3. 拉取远端（避免冲突）
if [ "$AUTO_PULL" = "True" ] || [ "$AUTO_PULL" = "true" ]; then
    echo "🔄 拉取远端最新..."
    if ! git pull --rebase --autostash origin "$TARGET_BRANCH" 2>&1 | tail -5; then
        echo "  ⚠️  pull 失败（可能远端无更新或网络问题），继续..."
    fi
    echo ""
fi

# 4. 配置 git 作者
git config user.name "$GIT_USER_NAME"
git config user.email "$GIT_USER_EMAIL"

# 5. 生成 commit message
NOW_DATE=$(date '+%Y-%m-%d')
NOW_TIME=$(date '+%H:%M:%S')
COMMIT_MSG=$(echo "$MSG_TEMPLATE" | sed "s/{date}/$NOW_DATE/g; s/{time}/$NOW_TIME/g; s/{count}/$total_count/g; s/{branch}/$TARGET_BRANCH/g")

# 6. commit
echo "💾 Commit: $COMMIT_MSG"
git add "$PUBLISH_DIR/"
if ! git commit -m "$COMMIT_MSG" 2>&1 | tail -5; then
    echo "❌ commit 失败" >&2
    exit 1
fi
echo ""

# 7. push
echo "🚀 Push 到 origin/$TARGET_BRANCH..."
if git push origin "$TARGET_BRANCH" 2>&1 | tail -10; then
    echo ""
    echo "✅ Push 成功！"
    echo ""
    echo "固定链接（其他工具可读取）："
    REPO=$(get_config "repository")
    echo "  https://raw.githubusercontent.com/$REPO/$TARGET_BRANCH/$PUBLISH_DIR/result.m3u"
    echo "  https://cdn.jsdelivr.net/gh/$REPO@$TARGET_BRANCH/$PUBLISH_DIR/result.m3u"
else
    echo ""
    echo "❌ Push 失败"
    if [ "$AUTO_ROLLBACK" = "True" ] || [ "$AUTO_ROLLBACK" = "true" ]; then
        echo "🔙 回滚 commit..."
        git reset --soft HEAD~1
        git reset HEAD "$PUBLISH_DIR/"
        echo "  ✅ 已回滚（live/ 文件保留本地）"
    fi
    exit 1
fi