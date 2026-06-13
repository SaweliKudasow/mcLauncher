"""Простой GUI лаунчера (только кнопки — на Mac tkinter рисует лишь их)."""

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog

from launch import VERSION, find_java, get_version_json, launch, mc_dir, prepare


def main() -> None:
    root = tk.Tk()
    root.title(f"mcLauncher — Minecraft {VERSION}")
    root.resizable(False, False)

    nick, mem = "Player", 2
    style = {"width": 24, "height": 2, "font": ("Helvetica", 14)}

    def set_title(msg: str = "") -> None:
        root.title(f"mcLauncher {VERSION}" + (f" — {msg}" if msg else ""))

    def change_nick() -> None:
        nonlocal nick
        v = simpledialog.askstring("Ник", "Имя игрока:", initialvalue=nick, parent=root)
        if v and v.strip():
            nick = v.strip()
            nick_btn.config(text=f"Ник: {nick}")

    def change_mem() -> None:
        nonlocal mem
        v = simpledialog.askinteger("Память", "ОЗУ в ГБ (1–8):", initialvalue=mem, minvalue=1, maxvalue=8, parent=root)
        if v:
            mem = v
            mem_btn.config(text=f"ОЗУ: {mem} ГБ")

    def play() -> None:
        if not find_java():
            messagebox.showerror("mcLauncher", "Java не найдена (нужна JDK 8)")
            return
        play_btn.config(state="disabled")
        set_title("Загрузка...")

        def job() -> None:
            try:
                game = mc_dir()
                game.mkdir(parents=True, exist_ok=True)
                ver = get_version_json()
                natives, cp = prepare(ver, game)
                launch(nick, game, natives, cp, ver, mem)
                root.after(0, lambda: set_title("Запущено"))
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("mcLauncher", str(e)))
            finally:
                root.after(0, lambda: play_btn.config(state="normal"))

        threading.Thread(target=job, daemon=True).start()

    nick_btn = tk.Button(root, text=f"Ник: {nick}", command=change_nick, **style)
    nick_btn.pack(padx=20, pady=10)

    mem_btn = tk.Button(root, text=f"ОЗУ: {mem} ГБ", command=change_mem, **style)
    mem_btn.pack(padx=20, pady=10)

    play_btn = tk.Button(root, text="Играть", command=play, **style)
    play_btn.pack(padx=20, pady=10)

    root.mainloop()


if __name__ == "__main__":
    main()
