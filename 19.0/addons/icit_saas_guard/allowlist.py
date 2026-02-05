import json
import logging
import os
import threading

import odoo.tools.config

_logger = logging.getLogger(__name__)

_lock = threading.Lock()

VALID_MODES = ("allowlist", "denylist", "disabled")


def _get_allowlist_path():
    """Return the path to the allowlists JSON file."""
    data_dir = odoo.tools.config["data_dir"]
    return os.path.join(data_dir, "saas_guard", "allowlists.json")


def _default_config():
    """Return a default empty config."""
    return {
        "version": 1,
        "defaults": {"mode": "disabled"},
        "databases": {},
    }


def load_allowlist():
    """Read and return the full allowlist config. Thread-safe."""
    with _lock:
        path = _get_allowlist_path()
        if not os.path.isfile(path):
            return _default_config()
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return config
        except (json.JSONDecodeError, OSError) as e:
            _logger.warning("Failed to read allowlist at %s: %s", path, e)
            return _default_config()


def save_allowlist(config):
    """Atomically write the allowlist config. Thread-safe."""
    with _lock:
        path = _get_allowlist_path()
        dir_path = os.path.dirname(path)
        os.makedirs(dir_path, exist_ok=True)
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except OSError as e:
            _logger.error("Failed to save allowlist to %s: %s", path, e)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise


def get_db_allowlist(dbname):
    """Return the allowlist config for a specific database."""
    config = load_allowlist()
    db_config = config.get("databases", {}).get(dbname)
    if not db_config:
        defaults = config.get("defaults", {})
        return {"mode": defaults.get("mode", "disabled")}
    return db_config


def set_db_allowlist(dbname, db_config):
    """Update the allowlist config for a specific database."""
    mode = db_config.get("mode", "disabled")
    if mode not in VALID_MODES:
        raise ValueError("Invalid allowlist mode: %s" % mode)
    config = load_allowlist()
    if "databases" not in config:
        config["databases"] = {}
    config["databases"][dbname] = db_config
    save_allowlist(config)


def is_module_allowed(dbname, module_name):
    """Check if a module is allowed for a database. Returns True if allowed."""
    db_config = get_db_allowlist(dbname)
    mode = db_config.get("mode", "disabled")
    if mode == "disabled":
        return True
    if mode == "allowlist":
        allowed = db_config.get("allowed_modules", [])
        return module_name in allowed
    if mode == "denylist":
        denied = db_config.get("denied_modules", [])
        return module_name not in denied
    return True
