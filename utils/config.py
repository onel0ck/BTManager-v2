import yaml
import os
from pathlib import Path


def load_config(path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Expand ~ in wallet base_path
    if "wallet" in config and "base_path" in config["wallet"]:
        config["wallet"]["base_path"] = os.path.expanduser(config["wallet"]["base_path"])

    return config
