"""Create the four asset directories in the target Git worktree."""
from pathlib import Path
import subprocess
import sys

KINDS = ("playbooks", "workflows", "references", "scripts")


def initialize():
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], text=True, capture_output=True)
    if result.returncode:
        raise ValueError("Run init inside the target Git worktree.")
    root = Path(result.stdout.rstrip("\n")) / ".byte-stack"
    dirs = [root, *(root / kind for kind in KINDS)]
    for path in dirs:
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError(f"expected a directory at {path}")
    for path in dirs[1:]:
        placeholder = path / ".gitkeep"
        if placeholder.is_symlink() or (placeholder.exists() and not placeholder.is_file()):
            raise ValueError(f"expected a regular file at {placeholder}")
    created = []
    for path in dirs:
        try:
            path.mkdir()
            created.append(path)
        except FileExistsError:
            if path.is_symlink() or not path.is_dir():
                raise
    for path in dirs[1:]:
        if any(path.iterdir()):
            continue
        placeholder = path / ".gitkeep"
        try:
            with placeholder.open("xb"):
                pass
            created.append(placeholder)
        except FileExistsError:
            if placeholder.is_symlink() or not placeholder.is_file():
                raise
    if created:
        for path in created:
            print(f"Created {path}")
    else:
        print(f"Already initialized: {root}")


if __name__ == "__main__":
    try:
        initialize()
    except (OSError, ValueError) as error:
        sys.exit(str(error))
