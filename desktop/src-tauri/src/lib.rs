// Phase 13.0: минимальная Tauri-обёртка. Окно загружает уже
// настроенный URL Mini App (см. tauri.conf.json → app.windows[0].url).
// На этом уровне нативного кода нет — нужен только бутстрап Tauri.
// Native-плагины (notification, autostart, tray) будут добавляться
// прицельно под конкретные задачи.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
