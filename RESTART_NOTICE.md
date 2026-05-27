🔴 IMPORTANT: You must fully restart `npm run dev` for the taskbar/window icon to update. Tauri caches icons at build time.

Run these commands in PowerShell:

```powershell
# 1. Kill any lingering processes
Get-Process python, node, cargo | Stop-Process -Force

# 2. Wait a moment
Start-Sleep 2

# 3. Start fresh
cd C:\Users\Haziq\Documents\SNAP-C1\Copartner\app
npm run dev
```

The in-app avatars should update immediately on next save/build. The window/taskbar icon needs the full restart above.
