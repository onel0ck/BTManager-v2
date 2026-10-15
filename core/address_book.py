"""
Local address book: map SS58 addresses back to wallet names.

Reads the public address out of the wallet files on disk
(coldkeypub.txt and each hotkey file) without unlocking anything.
Only the ss58Address field is ever read; secret fields are ignored.
"""

import json
import re
from pathlib import Path
from typing import Optional

from core.wallet_ops import get_wallets_path, get_coldkey_ss58
from utils.logger import setup_logger

logger = setup_logger("address_book")


def _read_ss58(path: Path) -> Optional[str]:
    """Read the ss58Address field out of a wallet key file."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            addr = data.get("ss58Address")
            if isinstance(addr, str) and addr:
                return addr
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        pass
    return None


def build_address_index(base_path: str = "~/.bittensor/wallets") -> dict:
    """
    Build an index of every local key.

    Returns:
        {
          "coldkeys": {ss58: [wallet_name, ...]},
          "hotkeys":  {ss58: [(wallet_name, hotkey_name), ...]},
          "wallets":  {wallet_name: {"coldkey": ss58|None, "hotkeys": {hk_name: ss58}}},
          "unreadable": [path_as_str, ...],
        }
    Lists are used because the same key can be reused in several wallets.
    """
    wallets_dir = get_wallets_path(base_path)
    index = {"coldkeys": {}, "hotkeys": {}, "wallets": {}, "unreadable": []}
    if not wallets_dir.exists():
        return index

    for entry in sorted(wallets_dir.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        wallet_entry = {"coldkey": None, "hotkeys": {}}

        ck_pub = entry / "coldkeypub.txt"
        ck_ss58 = _read_ss58(ck_pub) if ck_pub.exists() else None
        if ck_ss58 is None:
            # No readable coldkeypub.txt: fall back to the wallet library
            try:
                ck_ss58 = get_coldkey_ss58(name, base_path)
            except Exception:
                ck_ss58 = None
            if ck_ss58 is None and (ck_pub.exists() or (entry / "coldkey").exists()):
                index["unreadable"].append(str(ck_pub))
        if ck_ss58:
            wallet_entry["coldkey"] = ck_ss58
            index["coldkeys"].setdefault(ck_ss58, []).append(name)

        hotkeys_dir = entry / "hotkeys"
        if hotkeys_dir.exists():
            for hk in sorted(hotkeys_dir.iterdir()):
                if not hk.is_file() or hk.name.endswith("pub.txt"):
                    continue
                hk_ss58 = _read_ss58(hk)
                if not hk_ss58:
                    index["unreadable"].append(str(hk))
                    continue
                wallet_entry["hotkeys"][hk.name] = hk_ss58
                index["hotkeys"].setdefault(hk_ss58, []).append((name, hk.name))

        index["wallets"][name] = wallet_entry

    return index


def parse_address_input(text: str) -> list[str]:
    """Split pasted input into tokens: commas, semicolons, spaces and newlines."""
    return [t for t in re.split(r"[,;\s]+", (text or "").strip()) if t]


def looks_like_ss58(token: str) -> bool:
    """Cheap shape check (no checksum) so typos can still be looked up."""
    return bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{47,48}", token or ""))


def lookup(token: str, index: dict) -> dict:
    """
    Resolve one token against the index.

    Returns {"query", "kind", "matches", "valid"} where kind is one of
    "coldkey", "hotkey", "both", "wallet_name", "unknown", "not_an_address".
    matches:
      coldkey      -> [{"wallet"}]
      hotkey       -> [{"wallet", "hotkey"}]
      wallet_name  -> [{"wallet", "coldkey", "hotkey_count"}]
    """
    token = (token or "").strip()
    out = {"query": token, "kind": "unknown", "matches": [], "valid": looks_like_ss58(token)}

    ck_hits = index["coldkeys"].get(token, [])
    hk_hits = index["hotkeys"].get(token, [])

    if ck_hits and hk_hits:
        out["kind"] = "both"
        out["matches"] = (
            [{"wallet": w, "hotkey": None} for w in ck_hits]
            + [{"wallet": w, "hotkey": h} for w, h in hk_hits]
        )
        return out
    if ck_hits:
        out["kind"] = "coldkey"
        out["matches"] = [{"wallet": w, "hotkey": None} for w in ck_hits]
        return out
    if hk_hits:
        out["kind"] = "hotkey"
        out["matches"] = [{"wallet": w, "hotkey": h} for w, h in hk_hits]
        return out

    # Not an address we hold: maybe the user pasted a wallet name
    wallet = index["wallets"].get(token)
    if wallet is not None:
        out["kind"] = "wallet_name"
        out["matches"] = [{
            "wallet": token,
            "coldkey": wallet["coldkey"],
            "hotkey_count": len(wallet["hotkeys"]),
        }]
        return out

    out["kind"] = "unknown" if out["valid"] else "not_an_address"
    return out


def coldkey_of_hotkey(hotkey_ss58: str, index: dict) -> list[str]:
    """Coldkey SS58 address(es) owning a local hotkey."""
    owners = []
    for wallet_name, _hk in index["hotkeys"].get(hotkey_ss58, []):
        ck = index["wallets"].get(wallet_name, {}).get("coldkey")
        if ck and ck not in owners:
            owners.append(ck)
    return owners
