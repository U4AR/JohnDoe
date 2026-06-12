from __future__ import annotations

import shutil
from pathlib import Path


SEARCH_ROOTS = [
    Path.home() / "Downloads",
    Path.home() / "models",
    Path.home() / "Models",
    Path.home() / ".cache",
    Path.home() / ".cache" / "lm-studio",
    Path.home() / ".lmstudio",
    Path.home() / ".lmstudio-home",
    Path.home() / ".llamafile",
]


def main() -> None:
    add_lmstudio_home_pointer()
    server = shutil.which("llama-server") or shutil.which("llama-server.exe")
    cli = shutil.which("llama-cli") or shutil.which("llama-cli.exe")
    print(f"llama-server: {server or 'not found on PATH'}")
    print(f"llama-cli: {cli or 'not found on PATH'}")
    print()
    print("Likely Gemma-family GGUF models:")
    for model in find_models(limit=20):
        print(model)


def find_models(limit: int) -> list[Path]:
    found: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        try:
            for path in bounded_rglob(root, "*.gguf", max_dirs=3000):
                name = path.name.lower()
                if "gemma" in name or "4b" in name:
                    found.append(path)
                    if len(found) >= limit:
                        return found
        except OSError:
            continue
    return found


def add_lmstudio_home_pointer() -> None:
    pointer = Path.home() / ".lmstudio-home-pointer"
    if not pointer.exists():
        return
    try:
        target = Path(pointer.read_text(encoding="utf-8").strip())
    except OSError:
        return
    if target.exists() and target not in SEARCH_ROOTS:
        SEARCH_ROOTS.append(target)


def bounded_rglob(root: Path, pattern: str, max_dirs: int) -> list[Path]:
    results: list[Path] = []
    pending = [root]
    visited = 0
    while pending and visited < max_dirs:
        current = pending.pop()
        visited += 1
        try:
            for child in current.iterdir():
                if child.is_dir():
                    pending.append(child)
                elif child.match(pattern):
                    results.append(child)
        except OSError:
            continue
    return results


if __name__ == "__main__":
    main()
