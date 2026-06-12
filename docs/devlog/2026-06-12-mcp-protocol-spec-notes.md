# MCP 协议精确规范笔记 —— stdio server 最小实现

**日期**：2026-06-12  
**来源**：官方规范 https://modelcontextprotocol.io/specification/2025-11-25 + Claude Code 文档  
**说明**：所有内容均经官方文档验证，标注 ⭐ 为关键规范要求，🔍 为推断或实践建议。

---

## 1. stdio transport 消息帧格式

**✅ 规范（文献：[Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)）**

- **格式**：newline-delimited JSON（每行一个 JSON-RPC 消息）
- **分隔符**：`\n` 换行符（每条消息必须以 `\n` 结尾）
- ⭐ **禁止**：消息内不允许内嵌换行符（必须是单行 JSON，整个消息契约为一行）
- **编码**：UTF-8

### 示例消息序列

```
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25",...}}\n
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-11-25",...}}\n
{"jsonrpc":"2.0","method":"notifications/initialized"}\n
```

### 不是 Content-Length 帧

规范**完全没有**提及 Content-Length header 或二进制帧定界。stdio transport 就是纯 newline-delimited。

---

## 2. 最小握手序列与初始化

### 2.1 客户端 `initialize` 请求

**最小版本**（server 专注于声明 tools 能力）：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-11-25",
    "capabilities": {},
    "clientInfo": {
      "name": "claude-code-cli",
      "version": "1.0.0"
    }
  }
}
```

**字段说明**：
- `protocolVersion` ⭐：当前有效版本是 `"2025-11-25"`（规范日期，是 TypeScript schema 的版本号）。其他已知版本：`"2025-03-26"`, `"2024-11-05"`。客户端应发送**当前支持的最新版本**。
- `capabilities` 🔍：客户端声明自己的能力（如 `sampling`, `roots`）。对于最小的 server 测试，留空对象 `{}` 即可。
- `clientInfo` ⭐：必须包含 `name` 和 `version`；`title`, `description` 等字段可选。

### 2.2 Server `initialize` 响应

**最小版本**（声明 tools 能力）：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-11-25",
    "capabilities": {
      "tools": {
        "listChanged": true
      }
    },
    "serverInfo": {
      "name": "my-stdio-server",
      "version": "0.1.0"
    }
  }
}
```

**字段说明**：
- `protocolVersion` ⭐：**必须与客户端请求中的版本相同**。如果 server 不支持客户端的版本，返回自己支持的**最新**版本（版本协商见下）。
- `capabilities` ⭐：声明 server 提供什么功能：
  - `tools`：表示暴露工具。子字段 `listChanged` = `true` 表示当工具列表变化时会发 `notifications/tools/list_changed` 通知。
  - 其他可选：`resources`, `prompts`, `logging`, `tasks`, `completions` 等。最小 server 只需 `tools`。
- `serverInfo` ⭐：必须包含 `name` 和 `version`；`description`, `title` 等可选。

### 2.3 版本协商规则

📖 **[Lifecycle 文档](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle#version-negotiation)**

1. 客户端发送它**支持的最新版本**
2. Server：
   - 如果支持该版本 → 响应**相同版本**
   - 如果不支持 → 响应自己支持的**最新版本**（并期望客户端检查、可能断开）
3. 客户端：如果响应中的版本自己不支持 → 应该断开连接

**例子**：
- 客户端说 `"2025-11-25"`，server 只支持 `"2025-03-26"` → server 回应 `"2025-03-26"`，客户端决定是否断开
- 双方都支持 `"2025-11-25"` → 响应 `"2025-11-25"`，握手成功

### 2.4 `notifications/initialized` 通知

握手成功后，客户端**必须**发送此通知，server 才能收到正常请求：

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```

⭐ **时序要求**：
- 客户端在收到 `initialize` 响应后，发 `notifications/initialized`
- Server 在收到 `initialized` 前，**只允许**处理 `ping` 和 logging 请求
- `initialized` 后才能正常处理 `tools/list`, `tools/call` 等业务请求

---

## 3. `tools/list` 请求与响应结构

### 3.1 客户端请求

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {
    "cursor": null
  }
}
```

- `cursor` 可选（分页）；最小实现忽略即可

### 3.2 Server 响应

**最小完整示例**：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "add_numbers",
        "description": "Add two numbers together",
        "inputSchema": {
          "type": "object",
          "properties": {
            "a": {
              "type": "number",
              "description": "First number"
            },
            "b": {
              "type": "number",
              "description": "Second number"
            }
          },
          "required": ["a", "b"]
        }
      }
    ]
  }
}
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 工具唯一标识（1-128 字符，仅 `[a-z0-9A-Z_.-]`） |
| `description` | string | ✅ | 人类可读的描述 |
| `inputSchema` | JSON Schema object | ✅ | 工具参数的 JSON Schema（**不是** `input_schema` 下划线）|
| `title` | string | | 显示名称 |
| `outputSchema` | JSON Schema object | | 返回值的 schema（可选） |
| `icons` | array | | 图标列表（可选） |

### 3.3 关键细节

- ⭐ **字段名是 `inputSchema`**（驼峰式），**不是** `input_schema`（下划线）
- inputSchema 必须是合法的 JSON Schema 对象（defaults to 2020-12）
- 工具无参数时，使用 `{"type": "object", "additionalProperties": false}` 最佳实践

---

## 4. `tools/call` 请求与响应

### 4.1 客户端请求

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "add_numbers",
    "arguments": {
      "a": 5,
      "b": 3
    }
  }
}
```

- `name`：工具名（必须存在）
- `arguments`：工具参数对象（必须符合 inputSchema）

### 4.2 Server 成功响应

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "The sum of 5 and 3 is 8"
      }
    ],
    "isError": false
  }
}
```

### 4.3 Server 业务错误响应（工具执行失败）

**参数验证错误 / 业务逻辑错误** → 用 `result` + `isError: true`：

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Error: Input values must be positive numbers"
      }
    ],
    "isError": true
  }
}
```

⭐ **protocol vs business errors**：
- **Protocol errors**（JSON-RPC `error` field）：用于请求格式错误、找不到工具、malformed schema 等
- **Tool execution errors**（`isError: true` in result）：用于工具执行时的业务错误（LLM 可自动重试）

### 4.4 content 数组结构

content 可包含多个条目，支持多种类型：

```json
{
  "content": [
    {
      "type": "text",
      "text": "Result summary"
    },
    {
      "type": "image",
      "data": "base64-encoded-data",
      "mimeType": "image/png"
    },
    {
      "type": "resource_link",
      "uri": "file:///path/to/file",
      "name": "filename",
      "description": "optional"
    }
  ],
  "isError": false
}
```

最小实现：单个 text content 足够。

---

## 5. Server 必须处理的方法与通知

### 5.1 必处理的请求方法

| 方法 | 说明 | 响应 |
|------|------|------|
| `initialize` | 握手 | `{protocolVersion, capabilities, serverInfo}` |
| `ping` | 心跳检测 | `{}` (空对象) |
| `tools/list` | 列举工具 | `{tools: [...]}` |
| `tools/call` | 执行工具 | `{content: [...], isError: false\|true}` |

### 5.2 必处理的通知（无响应）

| 通知 | 说明 |
|------|------|
| `notifications/initialized` | 客户端就绪（握手完成后） |
| `notifications/cancelled` | 请求被客户端取消（可选处理） |

### 5.3 未知方法处理

**JSON-RPC 标准**：未知方法应返回错误：

```json
{
  "jsonrpc": "2.0",
  "id": 999,
  "error": {
    "code": -32601,
    "message": "Method not found"
  }
}
```

- `code: -32601` 是标准错误码（Method not found）
- 不要忽略请求！客户端期望得到错误响应

### 5.4 未知通知处理

- 对 notification（无 id 的消息），如果方法未知 → 直接忽略（因为 notification 无响应）
- 但**最好记个日志**便于调试

---

## 6. stdout / stderr 纪律

**✅ 规范要求**（[Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#stdio)）：

| 流 | 用途 | 规则 |
|------|------|------|
| **stdout** | JSON-RPC 消息 | ⭐ **只输出合法的 newline-delimited JSON-RPC 消息**。任何其他内容（日志、调试信息）都会破坏协议！ |
| **stderr** | 日志输出 | ✅ 任意文本皆可。客户端可忽略、转发或捕获，但**不会作为协议消息解析**。 |

**实现建议**：
```python
# ✅ 正确
import sys, json

def send_message(msg):
    """发送 JSON-RPC 消息到 stdout"""
    print(json.dumps(msg))  # 自动加 \n
    sys.stdout.flush()      # 立即发送

def log(msg):
    """日志写 stderr"""
    print(f"[LOG] {msg}", file=sys.stderr)
```

**常见错误**：
- ❌ `print(f"DEBUG: {data}")` 到 stdout（会污染协议流）
- ❌ 在 JSON 消息前后加额外文本

---

## 7. Claude Code 侧：`.mcp.json` 与注册

### 7.1 Claude Code 命令

**添加本地 stdio server**：

```bash
claude mcp add <server-name> -- <command> [args...]
```

**例子**：

```bash
# 添加一个 Python server
claude mcp add my-stdio-server -- python /path/to/server.py

# 添加一个用 node 启动的 server
claude mcp add my-stdio-server -- node /path/to/server.js
```

**验证连接**：

```bash
claude mcp list
```

输出示例：
```
✓ Connected: my-stdio-server
✗ Failed to connect: other-server
```

### 7.2 `.mcp.json` 结构

在项目根目录创建 `.mcp.json`（project-scoped，可检入 git）：

```json
{
  "mcpServers": {
    "my-stdio-server": {
      "type": "stdio",
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

**字段说明**：
- `type`: `"stdio"` 用于本地进程，`"http"` 用于远程 URL
- `command`: 执行的程序名或路径
- `args`: 命令行参数数组
- `env`: 可选，环境变量映射 `{"KEY": "value"}`

### 7.3 快速验证连接

**方式 1**（终端）：

```bash
cd /project/root
claude mcp list
```

**方式 2**（session 内）：

```bash
/mcp
```

会显示所有 server 及其状态。

### 7.4 权限与 approval

- 第一次使用 project-scoped server 时，Claude Code 会提示用户 approve（防止克隆的仓库偷偷启动进程）
- 用户同意后才能使用

---

## 8. 完整交互时序示意

```
Client (Claude Code)        Server (Python 脚本)
         |                         |
         |--- initialize --------> |
         |                         | (验证版本)
         |<-- result ------------- |
         |                         |
         |--- initialized -------> |
         | (notification)          |
         |                         |
         |--- tools/list --------> |
         |<-- result ------------- |
         |    [tool1, tool2, ...]  |
         |                         |
         |--- tools/call -------> |
         | name: "add_numbers"    |
         | arguments: {a:5, b:3}  |
         |<-- result ------------ |
         |    content: [...]      |
         |    isError: false      |
         |                         |
    ... (more calls) ...           |
         |                         |
         |--- ping ---------> (optional heartbeat)
         |<-- result -------       |
         |                         |
    (session ends)                 |
         |--- close stdin ---> |
         |                    (server exits)
```

---

## 9. 参考实现骨架（Python）

```python
#!/usr/bin/env python3
import json
import sys

def send_message(msg: dict):
    """Send JSON-RPC message to stdout"""
    print(json.dumps(msg), flush=True)

def read_message() -> dict:
    """Read one line from stdin as JSON-RPC message"""
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line.strip())

def handle_initialize(req_id, params):
    """Handle initialize request"""
    send_message({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2025-11-25",
            "capabilities": {
                "tools": {
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": "my-stdio-server",
                "version": "0.1.0"
            }
        }
    })

def handle_tools_list(req_id):
    """Handle tools/list request"""
    send_message({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": [
                {
                    "name": "add",
                    "description": "Add two numbers",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"}
                        },
                        "required": ["a", "b"]
                    }
                }
            ]
        }
    })

def handle_tools_call(req_id, params):
    """Handle tools/call request"""
    name = params.get("name")
    args = params.get("arguments", {})
    
    if name == "add":
        result = args["a"] + args["b"]
        send_message({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"Result: {result}"
                    }
                ],
                "isError": False
            }
        })
    else:
        # Protocol error: unknown tool
        send_message({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32602,
                "message": f"Unknown tool: {name}"
            }
        })

def handle_ping(req_id):
    """Handle ping request"""
    send_message({
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {}
    })

def main():
    initialized = False
    
    while True:
        msg = read_message()
        if not msg:
            break
        
        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params", {})
        
        # Handle requests (with id)
        if req_id is not None:
            if method == "initialize":
                handle_initialize(req_id, params)
                initialized = True
            elif method == "ping":
                handle_ping(req_id)
            elif not initialized:
                # Before initialized, only ping allowed
                send_message({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32002,
                        "message": "Server not initialized"
                    }
                })
            elif method == "tools/list":
                handle_tools_list(req_id)
            elif method == "tools/call":
                handle_tools_call(req_id, params)
            else:
                # Unknown method
                send_message({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                })
        
        # Handle notifications (no id)
        else:
            if method == "notifications/initialized":
                # Client is ready
                print(f"[SERVER] Client initialized", file=sys.stderr)
            elif method == "notifications/cancelled":
                # Request was cancelled by client (ignore for now)
                pass

if __name__ == "__main__":
    main()
```

---

## 10. 常见错误和陷阱

| 错误 | 症状 | 修复 |
|------|------|------|
| stdout 混入日志 | 客户端无法解析协议 | 所有日志写 stderr，stdout 仅输出 JSON-RPC 消息 |
| 忘记发 `initialized` notification | 客户端超时或拒绝 | 初始化成功后立即发 `notifications/initialized` |
| 消息末尾没有 `\n` | 客户端卡死（等待换行） | 用 `print()` 或 `flush()` + 确保 `\n` |
| inputSchema 用下划线 `input_schema` | 客户端报错或列表为空 | 驼峰式 `inputSchema`（查规范） |
| protocolVersion 版本号格式错误 | 版本协商失败 | 使用日期格式 `"YYYY-MM-DD"` 形式的版本号，如 `"2025-11-25"` |
| 未知方法没有返回错误 | 客户端超时 | 返回 `-32601` 错误响应，不要忽略 |

---

## 11. 文献引用

| 概念 | 官方文档链接 |
|------|------|
| 完整规范主页 | https://modelcontextprotocol.io/specification/2025-11-25 |
| Transport (stdio) | https://modelcontextprotocol.io/specification/2025-11-25/basic/transports |
| Lifecycle (握手) | https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle |
| Tools | https://modelcontextprotocol.io/specification/2025-11-25/server/tools |
| Ping | https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/ping |
| Claude Code MCP 快速开始 | https://code.claude.com/docs/en/mcp-quickstart.md |
| Claude Code MCP 完整参考 | https://code.claude.com/docs/en/mcp.md |

---

## 总结：最小可运行 server 的必要清单

- [ ] stdin 逐行读取 JSON-RPC 消息
- [ ] stdout 逐行输出 newline-delimited JSON-RPC 消息（`\n` 必有）
- [ ] stderr 用于日志（不影响协议）
- [ ] 实现 `initialize` → 返回 `protocolVersion`, `capabilities`, `serverInfo`
- [ ] 实现 `ping` → 返回空结果 `{}`
- [ ] 实现 `tools/list` → 返回工具数组（`inputSchema` 驼峰式）
- [ ] 实现 `tools/call` → 返回 `{content: [...], isError: bool}`
- [ ] 处理 `notifications/initialized` → 准备接收业务请求
- [ ] 未知方法 → 返回 `-32601` 错误
- [ ] 未知 notification → 忽略（或记日志）

---

**最后核验（2026-06-12）**：规范版本 `2025-11-25`，Claude Code 文档已更新至 v1.5+ 版本。本笔记所有字段名、错误码、方法名均与官方文档一致。
