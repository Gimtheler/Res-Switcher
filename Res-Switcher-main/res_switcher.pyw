import os
import sys
import json
import threading
import keyboard
import win32api
import win32con
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw
import pystray

CONFIG_FILE = "res_settings.json"


def get_active_monitors():
    monitors = []
    i = 0
    while True:
        try:
            device = win32api.EnumDisplayDevices(None, i)
            if device.StateFlags & win32con.DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
                try:
                    monitor_device = win32api.EnumDisplayDevices(device.DeviceName, 0)
                    monitor_name = monitor_device.DeviceString or device.DeviceString
                except:
                    monitor_name = device.DeviceString
                label = f"{device.DeviceName} — {monitor_name}"
                monitors.append((device.DeviceName, label))
            i += 1
        except:
            break
    return monitors


def get_supported_resolutions(device_name=None):
    res_set = set()
    i = 0
    while True:
        try:
            ds = win32api.EnumDisplaySettings(device_name, i)
            res_set.add((ds.PelsWidth, ds.PelsHeight))
            i += 1
        except:
            break
    return [f"{w}x{h}" for w, h in sorted(res_set, key=lambda x: x[0] * x[1])]


class ResolutionSwitcher:
    def __init__(self):
        self.enabled = True
        self.config = self.load_config()
        self.icon = None
        self.hotkey_hook = None
        self.monitors = get_active_monitors()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        return None

    def save_config(self, monitor_device, r1, r2, hotkey):
        self.config = {
            "monitor": monitor_device,
            "r1": r1,
            "r2": r2,
            "hotkey": hotkey
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=2)
        self.refresh_hotkey()

    def refresh_hotkey(self):
        if self.hotkey_hook:
            keyboard.unhook_all()
        if self.config:
            self.hotkey_hook = keyboard.add_hotkey(self.config["hotkey"], self.toggle_res)

    def toggle_res(self):
        if not self.enabled or not self.config:
            return

        monitor = self.config.get("monitor")
        curr = win32api.EnumDisplaySettings(monitor, win32con.ENUM_CURRENT_SETTINGS)
        c_w, c_h = curr.PelsWidth, curr.PelsHeight
        r1, r2 = self.config["r1"], self.config["r2"]

        target = r2 if (c_w == r1[0] and c_h == r1[1]) else r1

        dm = win32api.EnumDisplaySettings(monitor, win32con.ENUM_CURRENT_SETTINGS)
        dm.PelsWidth = target[0]
        dm.PelsHeight = target[1]
        dm.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
        result = win32api.ChangeDisplaySettingsEx(monitor, dm, 0)
        if result != win32con.DISP_CHANGE_SUCCESSFUL:
            print(f"[WARN] ChangeDisplaySettingsEx returned {result}")

    def open_settings(self):
        root = tk.Tk()
        root.title("Res Switcher — Settings")
        root.geometry("380x460")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        self.monitors = get_active_monitors()
        monitor_labels = [m[1] for m in self.monitors]
        monitor_devices = [m[0] for m in self.monitors]

        tk.Label(root, text="Monitor:", anchor="w").pack(fill="x", padx=15, pady=(12, 0))
        monitor_var = tk.StringVar()
        c_monitor = ttk.Combobox(root, textvariable=monitor_var, values=monitor_labels, state="readonly", width=45)
        default_mon = 0
        if self.config and self.config.get("monitor"):
            try:
                default_mon = monitor_devices.index(self.config["monitor"])
            except ValueError:
                default_mon = 0
        c_monitor.current(default_mon)
        c_monitor.pack(padx=15)

        def get_selected_device():
            idx = c_monitor.current()
            return monitor_devices[idx] if idx >= 0 else None

        def refresh_res_lists(*_):
            dev = get_selected_device()
            resolutions = get_supported_resolutions(dev)
            for cb in (c1, c2):
                cb["values"] = resolutions
            if c1.get() not in resolutions:
                c1.current(len(resolutions) // 2)
            if c2.get() not in resolutions:
                c2.current(len(resolutions) - 1)

        tk.Label(root, text="Res A  (e.g. your standard res):", anchor="w").pack(fill="x", padx=15, pady=(10, 0))
        c1_var = tk.StringVar()
        c1 = ttk.Combobox(root, textvariable=c1_var, width=20)
        c1.pack(padx=15, anchor="w")

        tk.Label(root, text="Res B  (e.g. your drop / alt res):", anchor="w").pack(fill="x", padx=15, pady=(10, 0))
        c2_var = tk.StringVar()
        c2 = ttk.Combobox(root, textvariable=c2_var, width=20)
        c2.pack(padx=15, anchor="w")

        tk.Label(root, text="  Custom: type any WxH directly into the box above", fg="grey", font=("Segoe UI", 8)).pack(anchor="w", padx=15)

        initial_res = get_supported_resolutions(get_selected_device())
        c1["values"] = initial_res
        c2["values"] = initial_res

        if self.config:
            c1.set(f"{self.config['r1'][0]}x{self.config['r1'][1]}")
            c2.set(f"{self.config['r2'][0]}x{self.config['r2'][1]}")
        else:
            c1.current(len(initial_res) // 2)
            c2.current(len(initial_res) - 1)

        c_monitor.bind("<<ComboboxSelected>>", refresh_res_lists)

        tk.Label(root, text="Hotkey:", anchor="w").pack(fill="x", padx=15, pady=(14, 0))
        captured_key = tk.StringVar(value=self.config["hotkey"] if self.config else "Click to set")
        btn_key = tk.Button(root, textvariable=captured_key, width=22, relief="groove")

        def start_record():
            captured_key.set("PRESS ANY KEY...")
            root.bind("<Key>", lambda e: (captured_key.set(e.keysym.lower()), root.unbind("<Key>")))

        btn_key.config(command=start_record)
        btn_key.pack(padx=15, anchor="w")

        status_var = tk.StringVar()
        tk.Label(root, textvariable=status_var, fg="red", font=("Segoe UI", 8)).pack(pady=(4, 0))

        def parse_res(text):
            try:
                w, h = map(int, text.lower().split("x"))
                return [w, h]
            except Exception:
                return None

        def save():
            r1 = parse_res(c1.get())
            r2 = parse_res(c2.get())
            if not r1:
                status_var.set("Res A is invalid. Use format: 1920x1080")
                return
            if not r2:
                status_var.set("Res B is invalid. Use format: 1280x720")
                return
            if captured_key.get() in ("Click to set", "PRESS ANY KEY..."):
                status_var.set("Please set a hotkey first.")
                return
            self.save_config(get_selected_device(), r1, r2, captured_key.get())
            root.destroy()

        tk.Button(
            root, text="Save & Run in Background",
            bg="#28a745", fg="white", font=("Segoe UI", 9, "bold"),
            command=save
        ).pack(pady=14)

        root.mainloop()

    def create_tray(self):
        img = Image.new("RGB", (64, 64), color=(30, 30, 30))
        d = ImageDraw.Draw(img)
        d.rectangle([10, 18, 54, 46], fill=(0, 120, 215))
        d.rectangle([26, 44, 38, 52], fill=(0, 120, 215))
        d.rectangle([20, 50, 44, 54], fill=(0, 120, 215))

        def on_toggle(icon, item):
            self.enabled = not self.enabled

        def open_settings_thread():
            threading.Thread(target=self.open_settings, daemon=True).start()

        menu = pystray.Menu(
            pystray.MenuItem("Settings", lambda icon, item: open_settings_thread()),
            pystray.MenuItem("Enabled", on_toggle, checked=lambda item: self.enabled),
            pystray.MenuItem("Exit", lambda icon, item: (self.icon.stop(), os._exit(0)))
        )

        self.icon = pystray.Icon("ResSwitcher", img, "Resolution Switcher", menu)
        self.icon.run()


if __name__ == "__main__":
    app = ResolutionSwitcher()

    if not app.config:
        app.open_settings()

    app.refresh_hotkey()
    app.create_tray()