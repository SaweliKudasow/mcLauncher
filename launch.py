#!/usr/bin/env python3
"""Простой офлайн-лаунчер Minecraft 1.8.9."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Callable
from urllib.request import urlopen

VERSION = "1.8.9"
MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

ProgressCallback = Callable[[str, float | None], None]


def mc_dir() -> Path:
    home = Path.home()
    if platform.system() == "Windows":
        return home / "AppData" / "Roaming" / ".minecraft"
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "minecraft"
    return home / ".minecraft"


def config_dir() -> Path:
    return Path(__file__).resolve().parent / ".launcher"


def os_name() -> str:
    return {"Windows": "windows", "Darwin": "osx", "Linux": "linux"}.get(platform.system(), "linux")


def download(
    url: str,
    dest: Path,
    sha1: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (sha1 is None or file_sha1(dest) == sha1):
        return
    if on_progress:
        on_progress(f"Скачиваю {dest.name}...", None)
    with urlopen(url) as resp:
        data = resp.read()
    if sha1 and hashlib.sha1(data).hexdigest() != sha1:
        raise RuntimeError(f"Неверная контрольная сумма: {dest.name}")
    dest.write_bytes(data)


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def library_allowed(rules: list | None) -> bool:
    if not rules:
        return True
    current_os = os_name()
    allowed = False
    for rule in rules:
        os_rule = rule.get("os")
        if os_rule and os_rule.get("name") and os_rule["name"] != current_os:
            continue
        if rule.get("action", "allow") == "allow":
            allowed = True
        else:
            allowed = False
    return allowed


def resolve_native_classifier(lib: dict) -> str | None:
    natives = lib.get("natives")
    if not natives:
        return None
    key = os_name()
    if key not in natives:
        return None
    classifier = natives[key]
    if "${arch}" in classifier:
        is64 = platform.machine().endswith("64") or platform.architecture()[0] == "64bit"
        classifier = classifier.replace("${arch}", "64" if is64 else "32")
    return classifier


def offline_uuid(username: str) -> str:
    return str(uuid.uuid3(uuid.NAMESPACE_DNS, f"OfflinePlayer:{username}"))


def extract_natives(jar: Path, dest: Path, exclude: list[str] | None = None) -> None:
    exclude = exclude or []
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(jar) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            if any(name.startswith(prefix) for prefix in exclude):
                continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))


def get_version_json(on_progress: ProgressCallback | None = None) -> dict:
    if on_progress:
        on_progress("Получаю манифест версий...", 0.05)
    with urlopen(MANIFEST_URL) as resp:
        manifest = json.load(resp)
    version_url = next(v["url"] for v in manifest["versions"] if v["id"] == VERSION)
    with urlopen(version_url) as resp:
        return json.load(resp)


def prepare(
    version: dict,
    root: Path,
    on_progress: ProgressCallback | None = None,
) -> tuple[Path, list[Path]]:
    def report(msg: str, pct: float | None = None) -> None:
        if on_progress:
            on_progress(msg, pct)

    version_dir = root / "versions" / VERSION
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / f"{VERSION}.json").write_text(json.dumps(version, indent=2))

    report("Скачиваю клиент...", 0.1)
    client = version["downloads"]["client"]
    client_jar = version_dir / f"{VERSION}.jar"
    download(client["url"], client_jar, client.get("sha1"), on_progress)

    libs_dir = root / "libraries"
    classpath: list[Path] = []
    native_jars: list[tuple[Path, list[str]]] = []

    allowed_libs = [lib for lib in version["libraries"] if library_allowed(lib.get("rules"))]
    total_libs = max(len(allowed_libs), 1)

    report("Скачиваю библиотеки...", 0.15)
    for i, lib in enumerate(allowed_libs):
        downloads = lib.get("downloads", {})
        artifact = downloads.get("artifact")
        if artifact:
            path = libs_dir / artifact["path"]
            download(artifact["url"], path, artifact.get("sha1"), on_progress)
            classpath.append(path)

        classifier = resolve_native_classifier(lib)
        if classifier:
            native = downloads.get("classifiers", {}).get(classifier)
            if native:
                path = libs_dir / native["path"]
                download(native["url"], path, native.get("sha1"), on_progress)
                native_jars.append((path, lib.get("extract", {}).get("exclude", [])))

        report(f"Библиотеки: {i + 1}/{total_libs}", 0.15 + 0.25 * (i + 1) / total_libs)

    classpath.append(client_jar)

    natives_dir = version_dir / "natives"
    if natives_dir.exists():
        shutil.rmtree(natives_dir)
    natives_dir.mkdir()
    report("Распаковываю natives...", 0.45)
    for jar, exclude in native_jars:
        extract_natives(jar, natives_dir, exclude)

    assets_dir = root / "assets"
    asset_index = version["assetIndex"]
    index_path = assets_dir / "indexes" / f"{asset_index['id']}.json"
    download(asset_index["url"], index_path, asset_index.get("sha1"), on_progress)

    report("Скачиваю ресурсы...", 0.5)
    index = json.loads(index_path.read_text())
    objects_dir = assets_dir / "objects"
    objects = list(index["objects"].values())
    total_assets = max(len(objects), 1)
    downloaded = 0

    for obj in objects:
        h = obj["hash"]
        dest = objects_dir / h[:2] / h
        if not dest.exists():
            download(f"https://resources.download.minecraft.net/{h[:2]}/{h}", dest, h, on_progress)
        downloaded += 1
        if downloaded % 50 == 0 or downloaded == total_assets:
            report(
                f"Ресурсы: {downloaded}/{total_assets}",
                0.5 + 0.45 * downloaded / total_assets,
            )

    report("Подготовка завершена", 1.0)
    return natives_dir, classpath


def find_java() -> str | None:
    return shutil.which("java")


def launch(
    username: str,
    root: Path,
    natives_dir: Path,
    classpath: list[Path],
    version: dict,
    memory_gb: int = 2,
    wait: bool = False,
) -> subprocess.Popen | None:
    java = find_java()
    if not java:
        raise RuntimeError("Java не найдена. Установите JDK 8.")

    cp = os.pathsep.join(str(p) for p in classpath)
    args = [
        java,
        f"-Djava.library.path={natives_dir}",
        f"-Xmx{memory_gb}G",
        "-cp",
        cp,
        version["mainClass"],
        "--username", username,
        "--version", VERSION,
        "--gameDir", str(root),
        "--assetsDir", str(root / "assets"),
        "--assetIndex", version["assetIndex"]["id"],
        "--uuid", offline_uuid(username),
        "--accessToken", "0",
        "--userProperties", "{}",
        "--userType", "legacy",
    ]

    if wait:
        subprocess.run(args, cwd=root)
        return None
    return subprocess.Popen(args, cwd=root)


def load_settings() -> dict:
    path = config_dir() / "settings.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"username": "Player", "memory_gb": 2}


def save_settings(username: str, memory_gb: int) -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    path = config_dir() / "settings.json"
    path.write_text(
        json.dumps({"username": username, "memory_gb": memory_gb}, indent=2),
        encoding="utf-8",
    )


def run_cli(username: str, memory_gb: int = 2) -> None:
    root = mc_dir()
    root.mkdir(parents=True, exist_ok=True)
    print(f"Папка Minecraft: {root}")
    version = get_version_json()
    natives_dir, classpath = prepare(version, root)
    print(f"\nЗапускаю Minecraft {VERSION} для {username}...\n")
    launch(username, root, natives_dir, classpath, version, memory_gb, wait=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Офлайн-лаунчер Minecraft 1.8.9")
    parser.add_argument("username", nargs="?", help="Имя игрока (только CLI)")
    parser.add_argument("--cli", action="store_true", help="Запуск в консольном режиме")
    parser.add_argument("--memory", type=int, default=2, help="ОЗУ в ГБ (по умолчанию 2)")
    args = parser.parse_args()

    if args.cli or args.username:
        run_cli(args.username or "Player", args.memory)
    else:
        from gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
