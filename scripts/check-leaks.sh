#!/usr/bin/env bash
# 扫描仓库文档里是否泄漏作者个人 / 环境信息。
# 用法：bash scripts/check-leaks.sh
# Exit 0 = 无残留；Exit 1 = 有残留（适合接 pre-commit hook）。

set -e

# 敏感关键词清单。新踩坑往这里加。
PATTERNS=(
  # 个人身份
  "作者"
  "muchengzju"
  "MCMBA"
  # 学术 / 工作环境
  "研究"
  "某高校"
  "导师"
  "合作者"
  "某实验室"
  "本地服务器"
  "***"
  # 时间 / 进度
  "下阶段"
  "结业"
  "近期"
  "近期"
  # 路径
  "~"
  "~"
)

EXCLUDE_DIRS=(
  "_reference"
  ".git"
  ".venv"
  ".pytest_cache"
  ".gstack"
  "node_modules"
  "scripts"  # 排除本脚本自己
)

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# 拼 grep 排除参数
exclude_args=()
for d in "${EXCLUDE_DIRS[@]}"; do
  exclude_args+=(--exclude-dir="$d")
done

# 拼正则
regex=$(IFS='|'; echo "${PATTERNS[*]}")

# 扫描
found=$(grep -rnE "$regex" \
  --include="*.md" \
  --include="*.toml" \
  --include="*.html" \
  --include="*.j2" \
  --include="*.py" \
  --include="*.txt" \
  --include="*.yaml" \
  --include="*.yml" \
  "${exclude_args[@]}" \
  . 2>/dev/null || true)

if [ -n "$found" ]; then
  echo "✗ 发现敏感信息泄漏，请清理后再 commit："
  echo ""
  echo "$found"
  echo ""
  echo "如需新增到白名单或扩展敏感词，编辑 scripts/check-leaks.sh"
  exit 1
fi

echo "✓ 无敏感信息残留"
exit 0
