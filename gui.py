"""Современный графический интерфейс лаунчера Minecraft."""

import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

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

# ── Палитра ──────────────────────────────────────────────────────────────────
BG = "#0c0c10"
SURFACE = "#16161f"
SURFACE_2 = "#1e1e2a"
BORDER = "#2a2a3a"
ACCENT = "#44bd32"
ACCENT_HOVER = "#3da829"
ACCENT_DIM = "#2d6b24"
TEXT = "#f0f0f5"
TEXT_MUTED = "#7a7a90"
ERROR = "#e74c3c"


class LauncherApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("mcLauncher")
        self.geometry("480x620")
        self.minsize(440, 580)
        self.configure(fg_color=BG)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        self._running = False
        self._settings = load_settings()

        self._build_ui()
        self._check_java()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Верхняя декоративная полоса
        accent_bar = ctk.CTkFrame(self, height=4, fg_color=ACCENT, corner_radius=0)
        accent_bar.pack(fill="x")

        main = ctk.CTkFrame(self, fg_color=BG)
        main.pack(fill="both", expand=True, padx=32, pady=(28, 24))

        # Логотип / заголовок
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 32))

        ctk.CTkLabel(
            header,
            text="⛏",
            font=ctk.CTkFont(size=42),
        ).pack()

        ctk.CTkLabel(
            header,
            text="mcLauncher",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=TEXT,
        ).pack(pady=(4, 0))

        version_badge = ctk.CTkLabel(
            header,
            text=f"  Minecraft {VERSION}  ",
            font=ctk.CTkFont(size=12),
            text_color=ACCENT,
            fg_color=ACCENT_DIM,
            corner_radius=12,
        )
        version_badge.pack(pady=(10, 0))

        # Карточка с настройками
        card = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=(0, 20))

        card_inner = ctk.CTkFrame(card, fg_color="transparent")
        card_inner.pack(fill="x", padx=24, pady=24)

        ctk.CTkLabel(
            card_inner,
            text="Имя игрока",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_MUTED,
            anchor="w",
        ).pack(fill="x")

        self.username_entry = ctk.CTkEntry(
            card_inner,
            height=44,
            font=ctk.CTkFont(size=15),
            fg_color=SURFACE_2,
            border_color=BORDER,
            text_color=TEXT,
            placeholder_text="Введите никнейм...",
            corner_radius=10,
        )
        self.username_entry.pack(fill="x", pady=(8, 20))
        self.username_entry.insert(0, self._settings.get("username", "Player"))

        mem_row = ctk.CTkFrame(card_inner, fg_color="transparent")
        mem_row.pack(fill="x")

        ctk.CTkLabel(
            mem_row,
            text="Оперативная память",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_MUTED,
        ).pack(side="left")

        self.mem_label = ctk.CTkLabel(
            mem_row,
            text=f"{self._settings.get('memory_gb', 2)} ГБ",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ACCENT,
        )
        self.mem_label.pack(side="right")

        self.mem_slider = ctk.CTkSlider(
            card_inner,
            from_=1,
            to=8,
            number_of_steps=7,
            height=18,
            fg_color=SURFACE_2,
            progress_color=ACCENT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            command=self._on_memory_change,
        )
        self.mem_slider.pack(fill="x", pady=(8, 0))
        self.mem_slider.set(self._settings.get("memory_gb", 2))

        # Статус Java
        self.java_label = ctk.CTkLabel(
            main,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
        )
        self.java_label.pack(fill="x", pady=(0, 12))

        # Кнопка запуска
        self.play_btn = ctk.CTkButton(
            main,
            text="▶  ИГРАТЬ",
            height=52,
            font=ctk.CTkFont(size=17, weight="bold"),
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            corner_radius=12,
            command=self._on_play,
        )
        self.play_btn.pack(fill="x", pady=(0, 20))

        # Прогресс
        progress_frame = ctk.CTkFrame(main, fg_color="transparent")
        progress_frame.pack(fill="x")

        self.status_label = ctk.CTkLabel(
            progress_frame,
            text="Готов к запуску",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 6))

        self.progress = ctk.CTkProgressBar(
            progress_frame,
            height=6,
            fg_color=SURFACE_2,
            progress_color=ACCENT,
            corner_radius=3,
        )
        self.progress.pack(fill="x")
        self.progress.set(0)

        # Путь к .minecraft
        ctk.CTkLabel(
            main,
            text=str(mc_dir()),
            font=ctk.CTkFont(size=10),
            text_color="#4a4a5a",
            wraplength=400,
        ).pack(side="bottom", pady=(16, 0))

    # ── Логика ───────────────────────────────────────────────────────────────

    def _check_java(self) -> None:
        java = find_java()
        if java:
            self.java_label.configure(text=f"✓  Java: {java}", text_color=ACCENT)
        else:
            self.java_label.configure(
                text="✗  Java не найдена — установите JDK 8",
                text_color=ERROR,
            )
            self.play_btn.configure(state="disabled", fg_color="#333")

    def _on_memory_change(self, value: float) -> None:
        gb = int(round(value))
        self.mem_label.configure(text=f"{gb} ГБ")

    def _set_busy(self, busy: bool) -> None:
        self._running = busy
        state = "disabled" if busy else "normal"
        self.play_btn.configure(state=state)
        self.username_entry.configure(state=state)
        if not busy and find_java():
            self.play_btn.configure(fg_color=ACCENT)

    def _update_progress(self, message: str, pct: float | None) -> None:
        self.after(0, lambda: self._apply_progress(message, pct))

    def _apply_progress(self, message: str, pct: float | None) -> None:
        self.status_label.configure(text=message)
        if pct is not None:
            self.progress.set(pct)

    def _on_play(self) -> None:
        if self._running:
            return

        username = self.username_entry.get().strip()
        if not username:
            messagebox.showwarning("mcLauncher", "Введите имя игрока.")
            return

        if not find_java():
            messagebox.showerror("mcLauncher", "Java не найдена.\nУстановите JDK 8 и перезапустите лаунчер.")
            return

        memory_gb = int(round(self.mem_slider.get()))
        save_settings(username, memory_gb)
        self._set_busy(True)
        self.progress.set(0)
        self.play_btn.configure(text="⏳  ПОДГОТОВКА...")

        thread = threading.Thread(
            target=self._launch_thread,
            args=(username, memory_gb),
            daemon=True,
        )
        thread.start()

    def _launch_thread(self, username: str, memory_gb: int) -> None:
        try:
            root = mc_dir()
            root.mkdir(parents=True, exist_ok=True)

            version = get_version_json(on_progress=self._update_progress)
            natives_dir, classpath = prepare(version, root, on_progress=self._update_progress)

            self._update_progress(f"Запускаю Minecraft для {username}...", 1.0)
            launch(username, root, natives_dir, classpath, version, memory_gb)

            self.after(0, lambda: self._on_launch_success(username))
        except Exception as exc:
            self.after(0, lambda: self._on_launch_error(str(exc)))

    def _on_launch_success(self, username: str) -> None:
        self._set_busy(False)
        self.play_btn.configure(text="▶  ИГРАТЬ")
        self.status_label.configure(text=f"Minecraft запущен — {username}", text_color=ACCENT)
        self.progress.set(1)

    def _on_launch_error(self, error: str) -> None:
        self._set_busy(False)
        self.play_btn.configure(text="▶  ИГРАТЬ")
        self.status_label.configure(text="Ошибка запуска", text_color=ERROR)
        self.progress.set(0)
        messagebox.showerror("mcLauncher", error)


def main() -> None:
    app = LauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
