"""
Per-wallet collect addresses.
Binds a coldkey wallet name to the SS58 address its TAO should be collected to.
Saved as JSON next to wallet_groups.json: {wallet_name: ss58_address}.
"""

import json
import re
from pathlib import Path
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger("collect_addresses")

COLLECT_FILE = "collect_addresses.json"


def _get_path() -> Path:
    return Path(COLLECT_FILE)


def is_valid_ss58(address: str) -> bool:
    """Validate SS58 address (format + checksum)."""
    try:
        from bittensor_wallet.utils import is_valid_ss58_address
        return bool(is_valid_ss58_address(address))
    except ImportError:
        return bool(re.fullmatch(r"5[1-9A-HJ-NP-Za-km-z]{47}", address or ""))


def load_collect_addresses() -> dict[str, str]:
    """Load all bindings. Returns {wallet_name: ss58_address}."""
    path = _get_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load collect addresses: {e}")
    return {}


def save_collect_addresses(mapping: dict[str, str]) -> None:
    """Save all bindings atomically."""
    path = _get_path()
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(dict(sorted(mapping.items())), f, indent=2)
        tmp.replace(path)
    except IOError as e:
        logger.error(f"Failed to save collect addresses: {e}")
        raise


def get_collect_address(wallet_name: str) -> Optional[str]:
    return load_collect_addresses().get(wallet_name)


def set_collect_address(wallet_name: str, address: str) -> None:
    """Bind wallet to address. Raises ValueError on invalid SS58."""
    address = address.strip()
    if not is_valid_ss58(address):
        raise ValueError(f"Invalid SS58 address: {address}")
    mapping = load_collect_addresses()
    mapping[wallet_name] = address
    save_collect_addresses(mapping)
    logger.info(f"Bound {wallet_name} -> {address}")


def delete_collect_address(wallet_name: str) -> bool:
    mapping = load_collect_addresses()
    if wallet_name not in mapping:
        return False
    del mapping[wallet_name]
    save_collect_addresses(mapping)
    logger.info(f"Unbound {wallet_name}")
    return True


def parse_bindings(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Parse many 'wallet:address' pairs from one string (or a whole file).

    Pairs may be separated by ',', ';', spaces or newlines. Inside a pair the
    separator may be ':', '=', '->' or just a space:
        78-clean_1:5Do...,78-clean_2:5FZ...
        78-clean_1 = 5Do...; 78-clean_2 5FZ...
    Returns (pairs, leftovers) — leftovers are tokens that did not form a pair.
    """
    pairs: list[tuple[str, str]] = []
    leftovers: list[str] = []
    pending = None
    for tok in re.split(r"[,;\s]+", text.strip()):
        if not tok:
            continue
        parts = re.split(r"->|[:=]", tok, maxsplit=1)
        if len(parts) == 2:
            a, b = parts[0].strip(), parts[1].strip()
            if a and b:
                if pending:
                    leftovers.append(pending)
                    pending = None
                pairs.append((a, b))
            elif a:  # "wallet:" followed by the address as the next token
                if pending:
                    leftovers.append(pending)
                pending = a
            elif b and pending:  # ":address" after a bare wallet name
                pairs.append((pending, b))
                pending = None
            elif b:
                leftovers.append(b)
            continue
        if pending:
            pairs.append((pending, tok))
            pending = None
        else:
            pending = tok
    if pending:
        leftovers.append(pending)
    return pairs, leftovers
