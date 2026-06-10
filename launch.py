#!/usr/bin/env python3
"""Простой офлайн-лаунчер Minecraft 1.8.9."""

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
from urllib.request import urlopen

VERSION = "1.8.9"
MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def mc_dir() -> Path:
    home = Path.home()
    if platform.system() == "Windows":
        return home / "AppData" / "Roaming" / ".minecraft"
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "minecraft"
    return home / ".minecraft"


def os_name() -> str:
    return {"Windows": "windows", "Darwin": "osx", "Linux": "linux"}.get(platform.system(), "linux")


def download(url: str, dest: Path, sha1: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (sha1 is None or file_sha1(dest) == sha1):
        return
    print(f"  скачиваю {dest.name}...")
    with urlopen(url) as resp:
        data = resp.read()
    if sha1 and hashlib.sha1(data).hexdigest() != sha1:
        raise RuntimeError(f"неверная контрольная сумма: {dest.name}")
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


def get_version_json() -> dict:
    print("получаю манифест версий...")
    with urlopen(MANIFEST_URL) as resp:
        manifest = json.load(resp)
    version_url = next(v["url"] for v in manifest["versions"] if v["id"] == VERSION)
    with urlopen(version_url) as resp:
        return json.load(resp)


def prepare(version: dict, root: Path) -> tuple[Path, list[Path]]:
    version_dir = root / "versions" / VERSION
    version_dir.mkdir(parents=True, exist_ok=True)
    (version_dir / f"{VERSION}.json").write_text(json.dumps(version, indent=2))

    client = version["downloads"]["client"]
    client_jar = version_dir / f"{VERSION}.jar"
    download(client["url"], client_jar, client.get("sha1"))

    libs_dir = root / "libraries"
    classpath: list[Path] = []
    native_jars: list[tuple[Path, list[str]]] = []

    print("скачиваю библиотеки...")
    for lib in version["libraries"]:
        if not library_allowed(lib.get("rules")):
            continue

        downloads = lib.get("downloads", {})
        artifact = downloads.get("artifact")
        if artifact:
            path = libs_dir / artifact["path"]
            download(artifact["url"], path, artifact.get("sha1"))
            classpath.append(path)

        classifier = resolve_native_classifier(lib)
        if classifier:
            native = downloads.get("classifiers", {}).get(classifier)
            if native:
                path = libs_dir / native["path"]
                download(native["url"], path, native.get("sha1"))
                native_jars.append((path, lib.get("extract", {}).get("exclude", [])))

    classpath.append(client_jar)

    natives_dir = version_dir / "natives"
    if natives_dir.exists():
        shutil.rmtree(natives_dir)
    natives_dir.mkdir()
    print("распаковываю natives...")
    for jar, exclude in native_jars:
        extract_natives(jar, natives_dir, exclude)

    assets_dir = root / "assets"
    asset_index = version["assetIndex"]
    index_path = assets_dir / "indexes" / f"{asset_index['id']}.json"
    download(asset_index["url"], index_path, asset_index.get("sha1"))

    print("скачиваю ресурсы (это может занять время)...")
    index = json.loads(index_path.read_text())
    objects_dir = assets_dir / "objects"
    for obj in index["objects"].values():
        h = obj["hash"]
        dest = objects_dir / h[:2] / h
        if dest.exists():
            continue
        download(f"https://resources.download.minecraft.net/{h[:2]}/{h}", dest, h)

    return natives_dir, classpath


def launch(username: str, root: Path, natives_dir: Path, classpath: list[Path], version: dict) -> None:
    java = shutil.which("java")
    if not java:
        sys.exit("Java не найдена. Установите JDK 8.")

    cp = os.pathsep.join(str(p) for p in classpath)
    args = [
        java,
        f"-Djava.library.path={natives_dir}",
        "-Xmx2G",
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

    print(f"\nзапускаю Minecraft {VERSION} для {username}...\n")
    subprocess.run(args, cwd=root)


if __name__ == "__main__":
    username = sys.argv[1] if len(sys.argv) > 1 else "Player"
    root = mc_dir()
    root.mkdir(parents=True, exist_ok=True)

    print(f"папка Minecraft: {root}")
    version = get_version_json()
    natives_dir, classpath = prepare(version, root)
    launch(username, root, natives_dir, classpath, version)
