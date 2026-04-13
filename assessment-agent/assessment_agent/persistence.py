"""Thread-safe JSON file persistence for prototype data stores."""
import json
import os
from filelock import FileLock


def append_json(filepath: str, entry: dict) -> None:
    """Append an entry to a JSON array file with file locking."""
    lock = FileLock(filepath + ".lock", timeout=10)
    with lock:
        data = []
        if os.path.exists(filepath):
            with open(filepath) as f:
                data = json.load(f)
        data.append(entry)
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)


def read_json(filepath: str) -> list[dict]:
    """Read a JSON array file, returning empty list if missing."""
    if not os.path.exists(filepath):
        return []
    with open(filepath) as f:
        return json.load(f)


def update_json(filepath: str, match_key: str, match_value: str, updates: dict) -> bool:
    """Update the first matching entry in a JSON array file. Returns True if found."""
    lock = FileLock(filepath + ".lock", timeout=10)
    with lock:
        if not os.path.exists(filepath):
            return False
        with open(filepath) as f:
            data = json.load(f)
        found = False
        for item in data:
            if item.get(match_key) == match_value:
                item.update(updates)
                found = True
                break
        if found:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
        return found
