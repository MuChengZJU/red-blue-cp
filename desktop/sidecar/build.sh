#!/usr/bin/env bash
# 把 sidecar 打成自包含二进制（PyInstaller spike）。
# 用法：bash build.sh [onefile|onedir]   默认 onefile
#
# 产物：dist/rbcp-sidecar（onefile）或 dist/rbcp-sidecar-dir/（onedir）。
# Tauri 壳通过 tauri.conf.json 的 externalBin 把它当 sidecar spawn。
set -euo pipefail
cd "$(dirname "$0")"

MODE="${1:-onefile}"

if [[ ! -d .venv ]]; then
  uv venv --python 3.13 .venv
fi
uv pip install --python .venv/bin/python pyinstaller >/dev/null

if [[ "$MODE" == "onedir" ]]; then
  .venv/bin/pyinstaller --onedir --name rbcp-sidecar-dir \
    --add-data "_engine:_engine" --collect-submodules app \
    --clean --noconfirm rbcp_sidecar.py
  echo "built: dist/rbcp-sidecar-dir/  (cold-start ~30ms, ~20MB folder — 推荐：每次请求 spawn)"
else
  .venv/bin/pyinstaller --onefile --name rbcp-sidecar \
    --add-data "_engine:_engine" --collect-submodules app \
    --clean --noconfirm rbcp_sidecar.py
  echo "built: dist/rbcp-sidecar  (cold-start ~365ms, ~9MB single-file — 分发简单但每次自解压)"
fi
