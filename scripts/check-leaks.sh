#!/usr/bin/env bash
# 扫描仓库文档里是否泄漏作者个人 / 环境信息。
#
# 用法：
#   bash scripts/check-leaks.sh
#
# Exit 0 = 无残留；Exit 1 = 有残留（适合接 pre-commit hook）。
#
# 敏感词清单维护在 .leak-patterns.local（不进 git）。
# 模板见 .leak-patterns.example：复制 .example 为 .local 后填实际敏感词。

set -e

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

PATTERN_FILE=".leak-patterns.local"

if [ ! -f "$PATTERN_FILE" ]; then
  echo "⚠ 未找到 $PATTERN_FILE"
  echo "  请复制模板：cp .leak-patterns.example $PATTERN_FILE"
  echo "  然后编辑 $PATTERN_FILE 填入实际要屏蔽的敏感词。"
  exit 0  # 不强制，避免新 clone 用户必须配
fi

# 读取非空、非注释行（bash 3.2 兼容写法，不用 mapfile）
PATTERNS=()
while IFS= read -r line; do
  PATTERNS+=("$line")
done < <(grep -v '^[[:space:]]*#' "$PATTERN_FILE" | grep -v '^[[:space:]]*$')

if [ ${#PATTERNS[@]} -eq 0 ]; then
  echo "⚠ $PATTERN_FILE 里没有敏感词，跳过扫描"
  exit 0
fi

regex=$(IFS='|'; echo "${PATTERNS[*]}")

# 只扫 git 会纳入的文件（tracked + 未被 .gitignore 忽略的 untracked）——开源泄漏门只关心进库的文件。
# 这天然跳过 .venv / build / dist / target / gen / node_modules / _sandbox 等构建&临时产物
# （它们含机器绝对路径但永不进库，扫它们是误报）。再排除 _reference（上游参考）/ scripts / 敏感词清单本身。
files=$(git ls-files --cached --others --exclude-standard \
  | grep -iE '\.(md|toml|html|j2|py|txt|yaml|yml)$' \
  | grep -vE '(^|/)(_reference|scripts)/' \
  | grep -vE '(^|/)\.leak-patterns' || true)

found=""
if [ -n "$files" ]; then
  found=$(printf '%s\n' "$files" | tr '\n' '\0' | xargs -0 grep -nE "$regex" 2>/dev/null || true)
fi

if [ -n "$found" ]; then
  echo "✗ 发现敏感信息泄漏，请清理后再 commit："
  echo ""
  echo "$found"
  echo ""
  echo "维护敏感词清单：编辑 $PATTERN_FILE"
  exit 1
fi

echo "✓ 无敏感信息残留"
exit 0
