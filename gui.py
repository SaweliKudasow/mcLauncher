"""Графический интерфейс лаунчера Minecraft."""

from __future__ import annotations

import os
import platform
import sys
import threading
import traceback
import tkinter as tk
from tkinter import messagebox

from launch import (
    VERSION,
    find_java,
    get_version_json,
    launch,
    load_settings,
    mc_dir,
    prepare,
    save_settings,
)

if platform.system() == "Darwin":
    os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")


class LauncherLogic:
    def __init__(self) -> None:
        self._running = False
        self._settings = load_settings()

    def check_java(self) -> tuple[bool, str]:
        java = find_java()
        if java:
            return True, f"Java: {java}"
        return False, "Java не найдена — установите JDK 8"

    def on_play(
        self,
        username: str,
        memory_gb: int,
        on_progress,
        on_success,
        on_error,
        on_busy,
    ) -> None:
        if self._running:
            return

        username = username.strip()
        if not username:
            messagebox.showwarning("mcLauncher", "Введите имя игрока.")
            return

        if not find_java():
            messagebox.showerror(
                "mcLauncher",
                "Java не найдена.\nУстановите JDK 8 и перезапустите лаунчер.",
            )
            return

        save_settings(username, memory_gb)
        self._running = True
        on_busy(True)

        def worker() -> None:
            try:
                root = mc_dir()
                root.mkdir(parents=True, exist_ok=True)
                version = get_version_json(on_progress=on_progress)
                natives_dir, classpath = prepare(version, root, on_progress=on_progress)
                on_progress(f"Запускаю Minecraft для {username}...", 1.0)
                launch(username, root, natives_dir, classpath, version, memory_gb)
                on_success(username)
            except Exception as exc:
                on_error(str(exc))
            finally:
                self._running = False

        threading.Thread(target=worker, daemon=True).start()


class LauncherApp(tk.Tk):
    """Минимальный GUI на tkinter — максимальная совместимость с macOS."""

    def __init__(self) -> None:
        super().__init__()
        self.logic = LauncherLogic()

        self.title(f"mcLauncher — Minecraft {VERSION}")
        self.geometry("420x480")
        self.resizable(False, False)

        self._build_ui()
        self._apply_java_status()

    def _build_ui(self) -> None:
        pad = {"padx": 20, "pady": 8}

        tk.Label(self, text="mcLauncher", font=("Helvetica", 22, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", **pad
        )
        tk.Label(self, text=f"Версия: Minecraft {VERSION}", font=("Helvetica", 12)).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=20
        )

        tk.Label(self, text="Имя игрока:", font=("Helvetica", 12)).grid(
            row=2, column=0, columnspan=2, sticky="w", **pad
        )
        self.username_entry = tk.Entry(self, width=36, font=("Helvetica", 14))
        self.username_entry.grid(row=3, column=0, columnspan=2, sticky="we", padx=20)
        self.username_entry.insert(0, self.logic._settings.get("username", "Player"))

        tk.Label(self, text="ОЗУ (ГБ):", font=("Helvetica", 12)).grid(
            row=4, column=0, sticky="w", **pad
        )
        self.mem_var = tk.IntVar(value=self.logic._settings.get("memory_gb", 2))
        self.mem_spin = tk.Spinbox(
            self,
            from_=1,
            to=8,
            width=5,
            textvariable=self.mem_var,
            font=("Helvetica", 14),
        )
        self.mem_spin.grid(row=4, column=1, sticky="e", padx=20, pady=8)

        self.java_label = tk.Label(self, text="", font=("Helvetica", 11), anchor="w")
        self.java_label.grid(row=5, column=0, columnspan=2, sticky="we", padx=20, pady=4)

        self.play_btn = tk.Button(
            self,
            text="ИГРАТЬ",
            font=("Helvetica", 14, "bold"),
            width=20,
            height=2,
            command=self._on_play,
        )
        self.play_btn.grid(row=6, column=0, columnspan=2, pady=16)

        self.status_label = tk.Label(
            self,
            text="Готов к запуску",
            font=("Helvetica", 11),
            anchor="w",
        )
        self.status_label.grid(row=7, column=0, columnspan=2, sticky="we", padx=20)

        tk.Label(
            self,
            text=str(mc_dir()),
            font=("Helvetica", 9),
            fg="gray",
            wraplength=380,
            justify="left",
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=20, pady=(12, 16))

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

    def _apply_java_status(self) -> None:
        ok, text = self.logic.check_java()
        self.java_label.configure(text=("✓ " if ok else "✗ ") + text)
        if not ok:
            self.play_btn.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.play_btn.configure(state=state, text="ПОДГОТОВКА..." if busy else "ИГРАТЬ")
        self.username_entry.configure(state=state)
        self.mem_spin.configure(state=state)

    def _update_progress(self, message: str, pct: float | None) -> None:
        self.after(0, lambda: self._apply_progress(message, pct))

    def _apply_progress(self, message: str, pct: float | None) -> None:
        if pct is not None:
            message = f"{message} ({int(pct * 100)}%)"
        self.status_label.configure(text=message)

    def _on_play(self) -> None:
        try:
            memory_gb = int(self.mem_var.get())
        except (ValueError, tk.TclError):
            memory_gb = 2

        self.logic.on_play(
            self.username_entry.get(),
            memory_gb,
            self._update_progress,
            self._on_launch_success,
            self._on_launch_error,
            self._set_busy,
        )

    def _on_launch_success(self, username: str) -> None:
        self._set_busy(False)
        self.status_label.configure(text=f"Minecraft запущен — {username}")

    def _on_launch_error(self, error: str) -> None:
        self._set_busy(False)
        self.status_label.configure(text="Ошибка запуска")
        messagebox.showerror("mcLauncher", error)


def _show_fatal_error(error: BaseException) -> None:
    root = tk.Tk()
    root.title("mcLauncher — ошибка")
    root.geometry("520x320")

    tk.Label(
        root,
        text="Не удалось открыть окно лаунчера:",
        font=("Helvetica", 13, "bold"),
    ).pack(anchor="w", padx=16, pady=(16, 8))

    text = tk.Text(root, wrap="word", height=12, font=("Menlo", 11))
    text.pack(fill="both", expand=True, padx=16, pady=8)
    text.insert("1.0", "".join(traceback.format_exception(type(error), error, error.__traceback__)))
    text.configure(state="disabled")

    tk.Button(root, text="Закрыть", command=root.destroy).pack(pady=12)
    root.mainloop()


def main() -> None:
    print("mcLauncher GUI: tkinter", file=sys.stderr)
    try:
        app = LauncherApp()
        app.mainloop()
    except Exception as exc:
        _show_fatal_error(exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
