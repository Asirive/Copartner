// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
};
use tauri_plugin_global_shortcut::{Code, Modifiers, ShortcutState};

#[tauri::command]
fn resize_window(window: tauri::Window, height: u32) -> Result<(), String> {
    let monitor = window.current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("No monitor found")?;
    let size = monitor.size();
    
    window.set_size(tauri::Size::Physical(tauri::PhysicalSize {
        width: size.width,
        height,
    })).map_err(|e| e.to_string())?;
    
    window.set_position(tauri::Position::Physical(tauri::PhysicalPosition {
        x: 0,
        y: 0,
    })).map_err(|e| e.to_string())?;
    
    Ok(())
}

#[tauri::command]
fn set_bar_mode(window: tauri::Window) -> Result<(), String> {
    resize_window(window, 40)
}

#[tauri::command]
fn set_dashboard_mode(window: tauri::Window) -> Result<(), String> {
    let monitor = window.current_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("No monitor found")?;
    let size = monitor.size();
    
    window.set_size(tauri::Size::Physical(tauri::PhysicalSize {
        width: size.width,
        height: 600,
    })).map_err(|e| e.to_string())?;
    
    window.set_position(tauri::Position::Physical(tauri::PhysicalPosition {
        x: 0,
        y: 0,
    })).map_err(|e| e.to_string())?;
    
    window.set_focus().map_err(|e| e.to_string())?;
    
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_shortcuts(["ctrl+space"])
                .unwrap()
                .with_handler(|app, shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        if shortcut.matches(Modifiers::CONTROL, Code::Space) {
                            if let Some(window) = app.get_webview_window("main") {
                                let is_visible = window.is_visible().unwrap_or(false);
                                if is_visible {
                                    window.hide().unwrap();
                                } else {
                                    window.show().unwrap();
                                    window.set_focus().unwrap();
                                }
                            }
                        }
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            resize_window,
            set_bar_mode,
            set_dashboard_mode
        ])
        .setup(|app| {
            // Set initial window to full monitor width
            if let Some(window) = app.get_webview_window("main") {
                if let Ok(Some(monitor)) = window.current_monitor() {
                    let size = monitor.size();
                    let _ = window.set_size(tauri::Size::Physical(tauri::PhysicalSize {
                        width: size.width,
                        height: 40,
                    }));
                    let _ = window.set_position(tauri::Position::Physical(tauri::PhysicalPosition {
                        x: 0,
                        y: 0,
                    }));
                }
            }

            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let show_i = MenuItem::with_id(app, "show", "Show", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &quit_i])?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        std::process::exit(0);
                    }
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            window.show().unwrap();
                            window.set_focus().unwrap();
                        }
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
