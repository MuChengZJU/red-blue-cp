// RBCP Desktop 壳：spawn 常驻 `rbcp-serve` sidecar（仅绑 127.0.0.1 + 随机端口 + token），
// 读它 stdout 首行 {"port","token"} 存进 State，前端经 get_api_config 拿到后调本地 HTTP API。
// 退出时 kill sidecar；单实例（二次启动聚焦旧窗、不起第二个 serve）。

use std::sync::Mutex;
use std::time::Duration;

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
fn start_serve(
    app: &tauri::AppHandle,
) -> Result<
    (
        Option<ApiConfig>,
        CommandChild,
        tauri::async_runtime::Receiver<CommandEvent>,
    ),
    String,
> {
    let (mut rx, child) = app
        .shell()
        .sidecar("rbcp-serve")
        .map_err(|e| format!("定位 rbcp-serve 失败: {e}"))?
        .spawn()
        .map_err(|e| format!("启动 rbcp-serve 失败: {e}"))?;

    // 阻塞读首个能解析成 ApiConfig 的 stdout 行；20s 超时防 serve 卡死时 App 永远打不开。
    let config = tauri::async_runtime::block_on(async {
        let read = async {
            while let Some(event) = rx.recv().await {
                match event {
                    CommandEvent::Stdout(line) => {
                        let s = String::from_utf8_lossy(&line);
                        if let Ok(cfg) = serde_json::from_str::<ApiConfig>(s.trim()) {
                            return Some(cfg);
                        }
                    }
                    CommandEvent::Terminated(payload) => {
                        eprintln!("[rbcp-serve] 启动阶段就退出了: {:?}", payload);
                        return None;
                    }
                    _ => {}
                }
            }
            None
        };
        match tokio::time::timeout(Duration::from_secs(20), read).await {
            Ok(cfg) => cfg,
            Err(_) => {
                eprintln!("[rbcp-serve] 等待 port/token 超时（20s）");
                None
            }
        }
    });

    Ok((config, child, rx))
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
            let handle = app.handle().clone();
            match start_serve(&handle) {
                Ok((config, child, mut rx)) => {
                    let state = app.state::<ApiState>();
                    *state.config.lock().unwrap() = config;
                    *state.child.lock().unwrap() = Some(child);
                    // 继续 drain 事件流（否则子进程 stdout 缓冲写满会卡）。
                    tauri::async_runtime::spawn(async move {
                        while let Some(event) = rx.recv().await {
                            match event {
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
                    });
                }
                Err(e) => {
                    eprintln!("启动本地服务失败: {e}");
                }
            }
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
