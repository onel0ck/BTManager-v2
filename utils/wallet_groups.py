"""
Wallet groups management.
Groups are saved as JSON in the config directory.
Each group maps a name to a list of coldkey wallet names.
"""

import json
from pathlib import Path
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger("wallet_groups")

GROUPS_FILE = "wallet_groups.json"


def _get_groups_path() -> Path:
    """Get path to groups JSON file (same directory as main script)."""
    return Path(GROUPS_FILE)


def load_groups() -> dict[str, list[str]]:
    """Load all groups from file. Returns {group_name: [wallet_names]}."""
    path = _get_groups_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load groups: {e}")
    return {}


def save_groups(groups: dict[str, list[str]]) -> None:
    """Save all groups to file."""
    path = _get_groups_path()
    try:
        with open(path, "w") as f:
            json.dump(groups, f, indent=2)
    except IOError as e:
        logger.error(f"Failed to save groups: {e}")
        raise


def create_group(name: str, wallet_names: list[str]) -> None:
    """Create or overwrite a wallet group."""
    groups = load_groups()
    groups[name] = wallet_names
    save_groups(groups)
    logger.info(f"Created group '{name}' with {len(wallet_names)} wallets")


def delete_group(name: str) -> bool:
    """Delete a group. Returns True if deleted, False if not found."""
    groups = load_groups()
    if name not in groups:
        return False
    del groups[name]
    save_groups(groups)
    logger.info(f"Deleted group '{name}'")
    return True


def get_group(name: str) -> Optional[list[str]]:
    """Get wallet names for a group. Returns None if not found."""
    groups = load_groups()
    return groups.get(name)


def list_group_names() -> list[str]:
    """Get sorted list of all group names."""
    return sorted(load_groups().keys())
