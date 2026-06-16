#!/usr/bin/env bash
# 把 sidecar 打成自包含二进制（PyInstaller spike）。
# 用法：bash build.sh [onefile|onedir]   默认 onefile
#
# 产物：dist/rbcp-sidecar（onefile）或 dist/rbcp-sidecar-dir/（onedir）。
# Tauri 壳通过 tauri.conf.json 的 externalBin 把它当 sidecar spawn。
set -euo pipefail
cd "$(dirname "$0")"
REPO_ROOT="$(cd ../.. && pwd)"   # 仓库根：真实 app/ 引擎所在（不再 vendored）

MODE="${1:-onefile}"

if [[ ! -d .venv ]]; then
  uv venv --python 3.13 .venv
fi
uv pip install --python .venv/bin/python pyinstaller >/dev/null

# --paths 指仓库根 → 打真实 app/digest + app/extract.contracts（纯标准库闭包，不拉 fastapi/pydoll）。
# digest() 内 lazy import orchestrator，PyInstaller 静态分析抓不到 → 三个 --hidden-import 补上。
HIDDEN=(--hidden-import app.digest.orchestrator --hidden-import app.digest.anchor --hidden-import app.digest.llm)

if [[ "$MODE" == "onedir" ]]; then
  .venv/bin/pyinstaller --onedir --name rbcp-sidecar-dir \
    --paths "$REPO_ROOT" "${HIDDEN[@]}" \
    --clean --noconfirm rbcp_sidecar.py
  echo "built: dist/rbcp-sidecar-dir/  (cold-start ~30ms, ~20MB folder — 推荐：每次请求 spawn)"
else
  .venv/bin/pyinstaller --onefile --name rbcp-sidecar \
    --paths "$REPO_ROOT" "${HIDDEN[@]}" \
    --clean --noconfirm rbcp_sidecar.py
  echo "built: dist/rbcp-sidecar  (cold-start ~365ms, ~9MB single-file — 分发简单但每次自解压)"

  # Tauri externalBin 要单文件、命名带 target triple，且 binaries/ 是 gitignore 的构建产物
  # （不进库）。onefile 模式自动放到位，这样 `cargo tauri dev/build` 能直接找到 sidecar，
  # 不用手动 cp（之前缺这步导致 `resource path binaries/rbcp-sidecar-<triple> doesn't exist`）。
  TRIPLE=$(rustc -vV | sed -n 's/host: //p')
  mkdir -p ../src-tauri/binaries
  cp dist/rbcp-sidecar "../src-tauri/binaries/rbcp-sidecar-$TRIPLE"
  chmod +x "../src-tauri/binaries/rbcp-sidecar-$TRIPLE"
  echo "placed: src-tauri/binaries/rbcp-sidecar-$TRIPLE  →  现在可跑 cargo tauri dev"
fi
