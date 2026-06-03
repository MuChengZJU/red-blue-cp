# 在 WSL 上自部署 + 手机/Mac 远程访问

> 目标：在 Windows 的 WSL2 里跑起 RBCP 的 WebUI，手机和 Mac 经 Tailscale 私有网访问；
> 下载的 Markdown 经群晖（Synology Drive）同步回 Mac，用 Obsidian 类工具管理。

## ⚠️ 安全前提（先读）

当前 WebUI **绑 `0.0.0.0:8000` 且无任何鉴权**（`app/web/routes.py`）。任何能访问到这个端口的人，
都能用你的百炼 API Key 跑任务（花你的钱）、读你整个知识库、用你的小红书 cookie。

所以本指南**只走私有网（Tailscale）**，不暴露公网。**在加上鉴权之前，绝对不要用 FRP / 端口映射把它挂到公网。**

---

## 前提条件

- Windows 11（22H2 及以上，支持 WSL2 镜像网络）+ 已装 WSL2
- 一个百炼（DashScope）API Key
- 手机、Mac、Windows 都能装 Tailscale（同一账号）
- 可选：Chrome/Edge（仅"博主全量 / 评论"用，靠 pydoll 驱动浏览器；WSLg 提供图形界面）
- 可选：系统 `ffmpeg`（仅小红书视频走"音频直链失败回退下载"兜底时用到，常规字幕/直链路径用不到）

---

## 步骤

### 1. 开 WSL2 镜像网络（让 WSL 服务在 Windows 各网卡上可达）

在 Windows 用户目录建/改 `C:\Users\<你的Windows用户名>\.wslconfig`：

```ini
[wsl2]
networkingMode=mirrored
```

PowerShell 里重启 WSL 使其生效：

```powershell
wsl --shutdown
```

重新打开 WSL。镜像网络下，WSL 里监听 `0.0.0.0:8000` 的服务会出现在 Windows 的所有 IP（含后面 Tailscale 的 IP）上。

### 2. 装 uv（Python 包管理器）

WSL 终端里：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# 重开终端，或 source 一下让 PATH 生效
source ~/.bashrc 2>/dev/null || source ~/.zshrc 2>/dev/null || true
uv --version
```

### 3. 装 RBCP

**路径 A：从 PyPI 装（等 v0.3 发布后）**

```bash
uv tool install red-blue-cp
rbcp --help
```

**路径 B：从源码装（现在、PyPI 还没发布时）**

```bash
git clone https://github.com/MuChengZJU/red-blue-cp.git
cd red-blue-cp
uv sync
# 之后命令前都加 uv run，例如：uv run rbcp --help
```

可选系统依赖（按需）：

```bash
sudo apt update && sudo apt install -y ffmpeg   # 仅小红书视频兜底路径用
```

### 4. 配置 `.env`

源码目录里（或 `~/.config/rbcp/.env`，配置发现顺序：环境变量 > `~/.config/rbcp/.env` > 当前目录 `.env`）：

```bash
cp .env.example .env
```

编辑 `.env`，至少填：

```bash
DASHSCOPE_API_KEY=sk-你的百炼key

# 关键：输出目录指到 Windows 本地盘，方便群晖同步（见第 8 步）
RBCP_OUTPUT_DIR=/mnt/c/Users/<你的Windows用户名>/transcript
```

> 为什么输出到 `/mnt/c`：群晖 Synology Drive 客户端跑在 Windows，盯本地盘符最稳；
> 若让它盯 `\\wsl.localhost\` 网络路径，实时同步往往不可靠。WSL 写 `/mnt/c` 略慢，但 Markdown 是小文本，忽略不计。

### 5. 启动服务

```bash
# 路径 A（PyPI 装的）
rbcp serve
# 路径 B（源码）
uv run rbcp serve
```

看到 uvicorn 起在 `0.0.0.0:8000` 即可。先在 WSL 本机验证：`curl -s localhost:8000 | head`。

### 6. 开机自启（systemd，推荐）

确认 WSL 启用了 systemd —— `/etc/wsl.conf`：

```ini
[boot]
systemd=true
```

（改完需 `wsl --shutdown` 重启 WSL。）

建用户级服务 `~/.config/systemd/user/rbcp.service`：

```ini
[Unit]
Description=Red Blue CP WebUI
After=network.target

[Service]
# 源码方式示例；PyPI 方式把 ExecStart 换成 /home/<user>/.local/bin/rbcp serve
WorkingDirectory=%h/red-blue-cp
ExecStart=%h/.local/bin/uv run rbcp serve
Restart=on-failure

[Install]
WantedBy=default.target
```

启用：

```bash
systemctl --user daemon-reload
systemctl --user enable --now rbcp
loginctl enable-linger "$USER"   # 没登录也保持运行
systemctl --user status rbcp
```

> 嫌 systemd 麻烦，先用 `nohup uv run rbcp serve >~/rbcp.log 2>&1 &` 起一个临时进程跑通也行。

### 7. Tailscale 远程访问

1. **Windows 主机**装 Tailscale（官网下载 Windows 客户端），登录你的账号，`tailscale up`。
2. 查 Windows 的 tailnet IP（PowerShell）：`tailscale ip -4` → 形如 `100.x.y.z`。
3. **手机 / Mac** 装 Tailscale，登录同一账号。
4. 手机/Mac 浏览器打开 `http://100.x.y.z:8000` —— 应能看到 WebUI，粘链接即可。

> 镜像网络下 Windows 的 Tailscale IP 即可直达 WSL 的 8000。若打不开，见下方排错。

### 8. 群晖同步 Markdown 到 Mac

1. Windows 上装 **Synology Drive Client**，把第 4 步的目录 `C:\Users\<你的Windows用户名>\transcript` 设为同步任务，同步到 NAS。
2. Mac 上装 Synology Drive Client，把 NAS 上那个文件夹同步下来。
3. Mac 端用 Obsidian 直接打开同步下来的本地目录即可。

### 9. 小红书登录（仅"带评论 / 博主全量"需要）

```bash
uv run rbcp login    # 弹浏览器扫码，cookie 存本地复用
```

单篇公开笔记的正文转录不需要登录；评论和博主全量需要。

### 10. 验证（真链路）

- 手机经 Tailscale 打开 WebUI，粘一条 B 站或小红书链接 → 几分钟后 status=done。
- 去 Mac 的 Obsidian 看同步过来的 `.md`。

---

## 排错

**手机/Mac 打不开 `100.x.y.z:8000`**

1. 确认 WSL 里服务在跑、本机 `curl localhost:8000` 通。
2. 确认 `.wslconfig` 的 `networkingMode=mirrored` 已生效（`wsl --shutdown` 重启过）。
3. Windows 防火墙放行 8000（入站规则）。
4. 仍不行 → 退回端口转发：在 Windows PowerShell（管理员）：
   ```powershell
   netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$(wsl hostname -I)
   ```
   （非镜像网络下 WSL IP 每次重启会变，需重配；镜像网络不需要这步。）
5. 实在不行，可改为在 WSL 内直接装 Tailscale，让 WSL 自己有 tailnet IP。

**报缺 API Key** → `.env` 没被读到。确认 `.env` 在启动目录或 `~/.config/rbcp/.env`。
