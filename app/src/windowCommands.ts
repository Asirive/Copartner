import { invoke } from "@tauri-apps/api/core";

export async function setBarMode(): Promise<void> {
  await invoke("set_bar_mode");
}

export async function setCollapsedMode(): Promise<void> {
  await invoke("set_collapsed_mode");
}

export async function setDashboardMode(): Promise<void> {
  await invoke("set_dashboard_mode");
}

export async function resizeWindow(height: number): Promise<void> {
  await invoke("resize_window", { height });
}
