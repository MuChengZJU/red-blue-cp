// RBCP Desktop 壳：spawn 常驻 `rbcp-serve` sidecar（仅绑 127.0.0.1 + 随机端口 + token），
// 读它 stdout 首行 {"port","token"} 存进 State，前端经 get_api_config 拿到后调本地 HTTP API。
// 退出时 kill sidecar；单实例（二次启动聚焦旧窗、不起第二个 serve）。

use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use tauri::{Manager, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ApiConfig {
    port: u16,
    token: String,
}

/// 进程内状态：serve 的连接信息 + 子进程句柄（退出时 kill）。
#[derive(Default)]
struct ApiState {
    config: Mutex<Option<ApiConfig>>,
    child: Mutex<Option<CommandChild>>,
}

/// 前端启动时调它拿 serve 的 port/token；serve 没起来则 Err。
#[tauri::command]
fn get_api_config(state: State<ApiState>) -> Result<ApiConfig, String> {
    state
        .config
        .lock()
        .unwrap()
        .clone()
        .ok_or_else(|| "本地服务尚未就绪（serve 启动失败或超时）".to_string())
}

/// spawn sidecar，阻塞读到 {"port","token"} 为止（带超时），返回 (config, child, 剩余事件流)。
/// 后台异步起 sidecar：**绝不阻塞主线程**（block_on 在 setup 会冻住 macOS 窗口、点不动）。
/// 立即存 child；读到 stdout 的 {port,token} 再存 config（get_api_config 在此前返回 Err，前端轮询等）。
async fn run_serve(handle: tauri::AppHandle) {
    let spawned = handle
        .shell()
        .sidecar("rbcp-serve")
        .and_then(|c| c.spawn());
    let (mut rx, child) = match spawned {
        Ok(v) => v,
        Err(e) => {
            eprintln!("启动 rbcp-serve 失败: {e}");
            return;
        }
    };
    // 立即存 child（退出时好 kill），即使还没拿到 port/token。
    *handle.state::<ApiState>().child.lock().unwrap() = Some(child);

    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => {
                let s = String::from_utf8_lossy(&line);
                if let Ok(cfg) = serde_json::from_str::<ApiConfig>(s.trim()) {
                    *handle.state::<ApiState>().config.lock().unwrap() = Some(cfg);
                }
            }
            CommandEvent::Stderr(line) => {
                eprintln!("[rbcp-serve] {}", String::from_utf8_lossy(&line));
            }
            CommandEvent::Terminated(payload) => {
                eprintln!("[rbcp-serve] 退出: {:?}", payload);
                break;
            }
            _ => {}
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // single-instance 必须最先注册：二次启动聚焦旧窗口，自己退出（不会再 spawn serve）。
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.set_focus();
                let _ = win.unminimize();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(ApiState::default())
        .invoke_handler(tauri::generate_handler![get_api_config])
        .setup(|app| {
            // 后台异步起 serve，setup 立即返回 → 窗口马上可交互（不再被 block_on 冻住）。
            tauri::async_runtime::spawn(run_serve(app.handle().clone()));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // App 退出：kill sidecar，不留僵尸 serve 占端口。
            if let tauri::RunEvent::ExitRequested { .. } = event {
                if let Some(child) = app_handle.state::<ApiState>().child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
