"""
Staking and unstaking operations for Bittensor.

Key concepts:
  - add_stake: takes TAO amount (in RAO), converts TAO->alpha on subnet
  - remove_stake: takes ALPHA amount (in RAO), converts alpha->TAO
  - unstake_all: removes all stake from all subnets for a hotkey
  - remove_stake_full_limit: unstake all alpha from one subnet with optional price limit
"""

from typing import Optional
from core.substrate_client import SubstrateClient, tao_to_rao, rao_to_tao
from utils.logger import setup_logger

logger = setup_logger("staking")


async def add_stake(
    client: SubstrateClient,
    wallet,
    hotkey_ss58: str,
    netuid: int,
    tao_amount: float,
    limit_price: Optional[float] = None,
    allow_partial: bool = True,
) -> tuple[bool, Optional[str]]:
    """
    Stake TAO to a hotkey on a specific subnet.
    
    Args:
        client: Connected SubstrateClient
        wallet: Wallet with unlocked coldkey (wallet.coldkey for signing)
        hotkey_ss58: Hotkey SS58 address to stake to
        netuid: Subnet ID
        tao_amount: Amount of TAO to stake
        limit_price: Min acceptable alpha/TAO price (slippage protection)
        allow_partial: Allow partial fill if limit price hit
        
    Returns:
        (success, error_message)
    """
    amount_rao = tao_to_rao(tao_amount)

    if limit_price is not None:
        # Use add_stake_limit for slippage protection
        # limit_price is in units of alpha_per_tao * 1e9
        limit_price_rao = tao_to_rao(limit_price)
        logger.info(
            f"add_stake_limit: hotkey={hotkey_ss58[:12]}... netuid={netuid} "
            f"amount={tao_amount} TAO limit_price={limit_price}"
        )
        return await client.compose_and_submit_checked(
            call_module="SubtensorModule",
            call_function="add_stake_limit",
            call_params={
                "hotkey": hotkey_ss58,
                "netuid": netuid,
                "amount_staked": amount_rao,
                "limit_price": limit_price_rao,
                "allow_partial": allow_partial,
            },
            keypair=wallet.coldkey,
        )
    else:
        logger.info(
            f"add_stake: hotkey={hotkey_ss58[:12]}... netuid={netuid} "
            f"amount={tao_amount} TAO"
        )
        return await client.compose_and_submit_checked(
            call_module="SubtensorModule",
            call_function="add_stake",
            call_params={
                "hotkey": hotkey_ss58,
                "netuid": netuid,
                "amount_staked": amount_rao,
            },
            keypair=wallet.coldkey,
        )


async def remove_stake(
    client: SubstrateClient,
    wallet,
    hotkey_ss58: str,
    netuid: int,
    alpha_amount: float,
    limit_price: Optional[float] = None,
    allow_partial: bool = True,
) -> tuple[bool, Optional[str]]:
    """
    Unstake alpha from a hotkey on a specific subnet.
    
    NOTE: amount is in ALPHA (not TAO). The chain converts alpha->TAO.
    
    Args:
        client: Connected SubstrateClient
        wallet: Wallet with unlocked coldkey
        hotkey_ss58: Hotkey SS58 address
        netuid: Subnet ID
        alpha_amount: Amount of ALPHA to unstake (in token units, not RAO)
        limit_price: Max acceptable price (price protection)
        allow_partial: Allow partial fill
        
    Returns:
        (success, error_message)
    """
    amount_rao = tao_to_rao(alpha_amount)  # alpha also uses 1e9 decimals

    if limit_price is not None:
        limit_price_rao = tao_to_rao(limit_price)
        logger.info(
            f"remove_stake_limit: hotkey={hotkey_ss58[:12]}... netuid={netuid} "
            f"amount={alpha_amount} alpha limit_price={limit_price}"
        )
        return await client.compose_and_submit_checked(
            call_module="SubtensorModule",
            call_function="remove_stake_limit",
            call_params={
                "hotkey": hotkey_ss58,
                "netuid": netuid,
                "amount_unstaked": amount_rao,
                "limit_price": limit_price_rao,
                "allow_partial": allow_partial,
            },
            keypair=wallet.coldkey,
        )
    else:
        logger.info(
            f"remove_stake: hotkey={hotkey_ss58[:12]}... netuid={netuid} "
            f"amount={alpha_amount} alpha"
        )
        return await client.compose_and_submit_checked(
            call_module="SubtensorModule",
            call_function="remove_stake",
            call_params={
                "hotkey": hotkey_ss58,
                "netuid": netuid,
                "amount_unstaked": amount_rao,
            },
            keypair=wallet.coldkey,
        )


async def unstake_all(
    client: SubstrateClient,
    wallet,
    hotkey_ss58: str,
) -> tuple[bool, Optional[str]]:
    """
    Unstake ALL alpha from ALL subnets for a specific hotkey.
    
    This requires hotkey parameter - one tx per hotkey.
    To unstake everything for a coldkey, call this for each hotkey.
    
    Returns:
        (success, error_message)
    """
    logger.info(f"unstake_all: hotkey={hotkey_ss58[:12]}...")
    return await client.compose_and_submit_checked(
        call_module="SubtensorModule",
        call_function="unstake_all",
        call_params={
            "hotkey": hotkey_ss58,
        },
        keypair=wallet.coldkey,
    )


async def unstake_subnet(
    client: SubstrateClient,
    wallet,
    hotkey_ss58: str,
    netuid: int,
    limit_price: Optional[float] = None,
) -> tuple[bool, Optional[str]]:
    """
    Unstake ALL alpha from a specific subnet.
    Uses remove_stake_full_limit (call_index 103).
    
    Args:
        client: Connected SubstrateClient
        wallet: Wallet with unlocked coldkey
        hotkey_ss58: Hotkey SS58 address
        netuid: Subnet ID
        limit_price: Optional min TAO/alpha price protection
        
    Returns:
        (success, error_message)
    """
    params = {
        "hotkey": hotkey_ss58,
        "netuid": netuid,
    }
    if limit_price is not None:
        params["limit_price"] = tao_to_rao(limit_price)
    else:
        params["limit_price"] = 0  # 0 = no limit

    logger.info(
        f"remove_stake_full_limit: hotkey={hotkey_ss58[:12]}... netuid={netuid}"
    )
    return await client.compose_and_submit_checked(
        call_module="SubtensorModule",
        call_function="remove_stake_full_limit",
        call_params=params,
        keypair=wallet.coldkey,
    )
