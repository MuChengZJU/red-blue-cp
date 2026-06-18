"""0.6 §A · 配置发现（M6a 地基）。

修硬伤：SPEC.md 教用户把 key 配到 ``~/.config/rbcp/.env``，但代码到处裸调
``load_dotenv()`` 只读当前目录、从不读那个路径 → 新用户首跑必断。这里用 platformdirs
实现跨平台的发现顺序，所有入口（cli / web）改调 ``load_config()``。

发现顺序（高 → 低；已存在的进程环境变量永不被覆盖）：
  1. 进程已有环境变量                      （最高，load_dotenv override=False 保证不覆盖）
  2. explicit_path / $RBCP_CONFIG_FILE
  3. 用户配置目录 / '.env'                  （platformdirs.user_config_dir('rbcp')）
       mac:   ~/Library/Application Support/rbcp/.env
       linux: ~/.config/rbcp/.env
       win:   %APPDATA%\\rbcp\\.env
  4. 当前目录 ./.env                        （开发兜底）

放在 app/（而非 app/extract/）：配置发现是 app 级基础设施，cli/web 都用；且对 digest
中立——digest 不读配置（provider 由壳层构造后注入），不会触碰 import-lint 的隔离规则。
"""

from __future__ import annotations

import os
from pathlib import Path

import platformdirs
from dotenv import load_dotenv

APP_NAME = "rbcp"


def config_dir() -> Path:
    """用户配置目录（platformdirs），并保证存在。写配置（如配置向导）用这个。"""
    path = Path(platformdirs.user_config_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_output_dir() -> Path:
    """知识库输出目录（~/transcript 默认）。

    用 ``or`` 而非 ``getenv(key, default)``：当 ``RBCP_OUTPUT_DIR`` 被设成**空串**
    （设置页存空值的历史脏数据）时，``getenv(key, default)`` 会返回 ""，
    ``Path("")`` 解析成当前工作目录——知识库会误落到 serve 的启动目录（违反红线#4）。
    空串在这里等同未设，回退默认目录。
    """
    return Path(os.getenv("RBCP_OUTPUT_DIR") or "~/transcript").expanduser()


def candidate_config_paths(explicit_path: str | None = None) -> list[Path]:
    """配置文件候选，按优先级从高到低（不含进程环境变量；纯查询，无副作用、不建目录）。"""
    candidates: list[Path] = []
    explicit = explicit_path or os.getenv("RBCP_CONFIG_FILE")
    if explicit:
        candidates.append(Path(explicit).expanduser())
    # 这里直接用 platformdirs.user_config_dir（不走 config_dir()，避免列举候选时建目录）
    candidates.append(Path(platformdirs.user_config_dir(APP_NAME)) / ".env")
    candidates.append(Path.cwd() / ".env")
    return candidates


def load_config(explicit_path: str | None = None) -> Path | None:
    """按发现顺序把 .env 载入 os.environ（已存在的环境变量永不覆盖）。

    返回命中的**最高优先级** .env 路径（没有任何文件命中则 None）。
    高优先级文件先 load（override=False），其 key 胜过低优先级文件；进程环境变量因已存在永不被替换。
    """
    primary: Path | None = None
    for path in candidate_config_paths(explicit_path):
        if path.is_file():
            load_dotenv(path, override=False)
            if primary is None:
                primary = path
    return primary
