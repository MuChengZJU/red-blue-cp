#!/usr/bin/env bash
# 把 rbcp-serve（桌面常驻 serve）打成自包含单文件二进制，放进 Tauri externalBin。
#
# 产物：dist/rbcp-serve → src-tauri/binaries/rbcp-serve-<triple>。
# serve 每个 App 会话只 spawn 一次，onefile 的自解压（~365ms）只付一次，故用 onefile
# （单文件适配 Tauri externalBin，省去 onedir 文件夹的处理）。
set -euo pipefail
cd "$(dirname "$0")"
REPO_ROOT="$(cd ../.. && pwd)"

if [[ ! -d .venv ]]; then
  uv venv --python 3.13 .venv
fi
# serve 需要项目全部运行依赖（fastapi/uvicorn/jinja2/typer/requests/...）+ pyinstaller。
uv pip install --python .venv/bin/python -e "$REPO_ROOT" pyinstaller >/dev/null

# uvicorn 的动态 import PyInstaller 静态分析抓不到 → 补 hidden-import（spike 验过的 4 个）。
# 两处 Jinja2 模板都要打进包：app/web/templates（WebUI 页面）+ app/extract/templates
# （Markdown 渲染 note.md.j2，markdown.py 按 __file__ 相对加载，漏了会 TemplateNotFound）。
# pydoll 桌面端不用，排除以缩小包。
.venv/bin/pyinstaller --onefile --name rbcp-serve \
  --paths "$REPO_ROOT" \
  --add-data "$REPO_ROOT/app/web/templates:app/web/templates" \
  --add-data "$REPO_ROOT/app/extract/templates:app/extract/templates" \
  --hidden-import uvicorn.loops.auto \
  --hidden-import uvicorn.protocols.http.auto \
  --hidden-import uvicorn.protocols.websockets.auto \
  --hidden-import uvicorn.lifespan.on \
  --exclude-module pydoll \
  --clean --noconfirm serve_entry.py

# Tauri externalBin 要单文件、命名带 target triple；binaries/ 是 gitignore 的构建产物（不进库）。
TRIPLE=$(rustc -vV | sed -n 's/host: //p')
mkdir -p ../src-tauri/binaries
cp dist/rbcp-serve "../src-tauri/binaries/rbcp-serve-$TRIPLE"
chmod +x "../src-tauri/binaries/rbcp-serve-$TRIPLE"
echo "placed: src-tauri/binaries/rbcp-serve-$TRIPLE  →  现在可跑 cargo tauri dev/build"
