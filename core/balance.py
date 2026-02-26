"""
Balance queries for Bittensor wallets.
"""

import asyncio
from typing import Optional
from core.substrate_client import SubstrateClient, rao_to_tao
from utils.logger import setup_logger

logger = setup_logger("balance")


async def check_balance(client: SubstrateClient, ss58_address: str) -> dict:
    """
    Check balance for a single address.
    Returns: {address, free_rao, free_tao}
    """
    balance_rao = await client.get_balance(ss58_address)
    return {
        "address": ss58_address,
        "free_rao": balance_rao,
        "free_tao": rao_to_tao(balance_rao),
    }


async def check_all_balances(
    client: SubstrateClient,
    addresses: list[str],
) -> list[dict]:
    """
    Check balances for multiple addresses in parallel.
    Returns list of {address, free_rao, free_tao}
    """
    tasks = [check_balance(client, addr) for addr in addresses]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    balances = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Balance check failed: {r}")
        else:
            balances.append(r)

    return balances
