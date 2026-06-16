// RBCP Desktop 壳：唯一职责 = spawn PyInstaller sidecar 跑引擎，把契约 JSON 透传给前端。
// 前端通过 invoke("run_digest", { text }) 调本命令。

use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

/// 把原文喂给 sidecar 二进制（externalBin: binaries/rbcp-sidecar），
/// 收集 stdout（契约 JSON 字符串）返回前端。失败返回 Err 字符串。
#[tauri::command]
async fn run_digest(app: tauri::AppHandle, text: String) -> Result<String, String> {
    let sidecar = app
        .shell()
        .sidecar("rbcp-sidecar")
        .map_err(|e| format!("sidecar 定位失败: {e}"))?
        .arg(text);

    let (mut rx, _child) = sidecar
        .spawn()
        .map_err(|e| format!("sidecar 启动失败: {e}"))?;

    let mut out = String::new();
    let mut err = String::new();
    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => out.push_str(&String::from_utf8_lossy(&line)),
            CommandEvent::Stderr(line) => err.push_str(&String::from_utf8_lossy(&line)),
            CommandEvent::Terminated(payload) => {
                if payload.code != Some(0) {
                    return Err(format!("sidecar 退出码 {:?}: {err}", payload.code));
                }
            }
            _ => {}
        }
    }
    if out.trim().is_empty() {
        return Err(format!("sidecar 无输出: {err}"));
    }
    Ok(out)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![run_digest])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
