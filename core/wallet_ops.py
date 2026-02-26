"""
Wallet operations using bittensor_wallet directly.
Handles coldkey/hotkey creation, listing, and loading.
"""

import os
from pathlib import Path
from typing import Optional
from bittensor_wallet import Wallet
from utils.logger import setup_logger

logger = setup_logger("wallet_ops")


def get_wallets_path(base_path: str = "~/.bittensor/wallets") -> Path:
    """Get expanded wallets directory path."""
    return Path(os.path.expanduser(base_path))


def list_wallets(base_path: str = "~/.bittensor/wallets") -> list[dict]:
    """
    List all wallets with their coldkeys and hotkeys.
    Returns list of dicts: {name, coldkey_exists, hotkeys: [str]}
    """
    wallets_dir = get_wallets_path(base_path)
    if not wallets_dir.exists():
        return []

    wallets = []
    for entry in sorted(wallets_dir.iterdir()):
        if not entry.is_dir():
            continue
        wallet_info = {
            "name": entry.name,
            "coldkey_exists": (entry / "coldkey").exists() or (entry / "coldkeypub.txt").exists(),
            "hotkeys": [],
        }
        hotkeys_dir = entry / "hotkeys"
        if hotkeys_dir.exists():
            wallet_info["hotkeys"] = sorted([
                hk.name for hk in hotkeys_dir.iterdir()
                if hk.is_file() and not hk.name.endswith("pub.txt")
            ])
        wallets.append(wallet_info)

    return wallets


def load_wallet(
    coldkey_name: str,
    hotkey_name: str = "default",
    base_path: str = "~/.bittensor/wallets",
) -> Wallet:
    """
    Load an existing wallet.
    Returns Wallet object with coldkey and hotkey accessible.
    """
    wallet = Wallet(name=coldkey_name, hotkey=hotkey_name, path=base_path)
    return wallet


def get_coldkey_ss58(
    coldkey_name: str,
    base_path: str = "~/.bittensor/wallets",
) -> Optional[str]:
    """Get SS58 address for a coldkey without unlocking it."""
    wallet = Wallet(name=coldkey_name, path=base_path)
    try:
        return wallet.coldkeypub.ss58_address
    except Exception:
        return None


def create_coldkey(
    name: str,
    n_words: int = 12,
    use_password: bool = True,
    overwrite: bool = False,
    base_path: str = "~/.bittensor/wallets",
) -> Wallet:
    """Create a new coldkey wallet."""
    wallet = Wallet(name=name, path=base_path)
    wallet.create_new_coldkey(
        n_words=n_words,
        use_password=use_password,
        overwrite=overwrite,
    )
    logger.info(f"Created coldkey: {name} -> {wallet.coldkeypub.ss58_address}")
    return wallet


def create_coldkey_with_hotkeys(
    name: str,
    hotkey_count: int,
    use_password: bool = False,
    base_path: str = "~/.bittensor/wallets",
) -> tuple[Wallet, int]:
    """
    Create coldkey + N hotkeys (named 1,2,...N).
    Checks for duplicate coldkey name first.
    
    Returns: (wallet, num_hotkeys_created)
    """
    wallets_dir = get_wallets_path(base_path)
    if (wallets_dir / name).exists():
        raise ValueError(f"Wallet '{name}' already exists")

    wallet = Wallet(name=name, path=base_path)
    wallet.create_new_coldkey(
        use_password=use_password,
        overwrite=False,
        suppress=True,
    )
    logger.info(f"Created coldkey: {name} -> {wallet.coldkeypub.ss58_address}")

    for i in range(1, hotkey_count + 1):
        hw = Wallet(name=name, hotkey=str(i), path=base_path)
        hw.create_new_hotkey(use_password=False, overwrite=False, suppress=True)

    logger.info(f"Created {hotkey_count} hotkeys for {name}")
    return wallet, hotkey_count


def add_hotkeys_to_wallet(
    coldkey_name: str,
    count: int,
    base_path: str = "~/.bittensor/wallets",
) -> tuple[int, int]:
    """
    Add N more hotkeys to existing wallet.
    Detects existing numbered hotkeys and continues from max+1.
    
    Returns: (start_num, end_num) of newly created hotkeys
    """
    wallets_dir = get_wallets_path(base_path)
    hotkeys_dir = wallets_dir / coldkey_name / "hotkeys"

    # Find existing numbered hotkeys
    existing_nums = set()
    if hotkeys_dir.exists():
        for f in hotkeys_dir.iterdir():
            if f.is_file() and not f.name.endswith("pub.txt"):
                try:
                    existing_nums.add(int(f.name))
                except ValueError:
                    pass  # non-numeric hotkey name, skip

    start = max(existing_nums) + 1 if existing_nums else 1

    for i in range(start, start + count):
        hw = Wallet(name=coldkey_name, hotkey=str(i), path=base_path)
        hw.create_new_hotkey(use_password=False, overwrite=False, suppress=True)

    end = start + count - 1
    logger.info(f"Added hotkeys {start}-{end} to {coldkey_name}")
    return start, end


def create_hotkey(
    coldkey_name: str,
    hotkey_name: str = "default",
    n_words: int = 12,
    use_password: bool = False,
    overwrite: bool = False,
    base_path: str = "~/.bittensor/wallets",
) -> Wallet:
    """
    Create a new hotkey under an existing coldkey.
    
    Args:
        coldkey_name: Parent coldkey wallet name
        hotkey_name: Hotkey name
        n_words: Mnemonic word count
        use_password: Whether to encrypt hotkey
        overwrite: Whether to overwrite existing
        base_path: Wallets directory
        
    Returns:
        Wallet object
    """
    wallet = Wallet(name=coldkey_name, hotkey=hotkey_name, path=base_path)
    wallet.create_new_hotkey(
        n_words=n_words,
        use_password=use_password,
        overwrite=overwrite,
    )
    logger.info(f"Created hotkey: {coldkey_name}/{hotkey_name} -> {wallet.hotkey.ss58_address}")
    return wallet
