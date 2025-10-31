import json
import os
import tempfile

HISTORY_KEYS = (
    "history",
    "slots_history",
    "blackjack_history",
    "dice_history",
    "wheel_history",
    "coinflip_history",
    "rps_history",
    "number_history",
    "transactions",
)

USER_DATA_FILE = os.path.join(os.path.dirname(__file__), "users.json")
_users_cache = None

def load_users() -> dict:
    """Load user data once and reuse cached version."""
    global _users_cache
    if _users_cache is None:
        if not os.path.exists(USER_DATA_FILE):
            _users_cache = {}
        else:
            try:
                with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                    _users_cache = json.load(f)
            except Exception:
                _users_cache = {}
        # Trim any existing histories to avoid loading large files
        if cleanup_users(_users_cache, limit=100):
            _atomic_write_json(USER_DATA_FILE, _users_cache)
    return _users_cache


def _atomic_write_json(path: str, data: dict) -> None:
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp_path, path)
    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass


def save_users(users: dict) -> None:
    """Persist user data after trimming heavy history lists."""
    cleanup_users(users, limit=100)
    _atomic_write_json(USER_DATA_FILE, users)
    global _users_cache
    _users_cache = users


def trim_history(user: dict, key: str, limit: int = 100) -> bool:
    """Keep only last ``limit`` entries for history lists to prevent bloat."""
    history = user.get(key)
    if history and len(history) > limit:
        del history[limit:]
        return True
    return False


def cleanup_users(users: dict, limit: int = 100) -> bool:
    """Trim stored histories for all users to keep the JSON compact."""
    changed = False
    for data in users.values():
        for key in HISTORY_KEYS:
            if trim_history(data, key, limit):
                changed = True
    return changed
