"""
TAO transfer operations.
"""

from typing import Optional
from core.substrate_client import SubstrateClient, tao_to_rao, rao_to_tao
from utils.logger import setup_logger

logger = setup_logger("transfer")


async def transfer_tao(
    client: SubstrateClient,
    wallet,
    dest_ss58: str,
    tao_amount: float,
) -> tuple[bool, Optional[str]]:
    """
    Transfer TAO from wallet's coldkey to destination address.
    Uses Balances.transfer_allow_death (keeps it simple, no keep-alive check).
    
    Args:
        client: Connected SubstrateClient
        wallet: Wallet with unlocked coldkey
        dest_ss58: Destination SS58 address
        tao_amount: Amount of TAO to transfer
        
    Returns:
        (success, error_message)
    """
    amount_rao = tao_to_rao(tao_amount)
    
    logger.info(
        f"transfer: {tao_amount} TAO -> {dest_ss58[:12]}..."
    )

    return await client.compose_and_submit_checked(
        call_module="Balances",
        call_function="transfer_allow_death",
        call_params={
            "dest": dest_ss58,
            "value": amount_rao,
        },
        keypair=wallet.coldkey,
    )


async def transfer_tao_keep_alive(
    client: SubstrateClient,
    wallet,
    dest_ss58: str,
    tao_amount: float,
) -> tuple[bool, Optional[str]]:
    """
    Transfer TAO with keep-alive check (won't kill sender account).
    Uses Balances.transfer_keep_alive.
    """
    amount_rao = tao_to_rao(tao_amount)

    logger.info(
        f"transfer_keep_alive: {tao_amount} TAO -> {dest_ss58[:12]}..."
    )

    return await client.compose_and_submit_checked(
        call_module="Balances",
        call_function="transfer_keep_alive",
        call_params={
            "dest": dest_ss58,
            "value": amount_rao,
        },
        keypair=wallet.coldkey,
    )
