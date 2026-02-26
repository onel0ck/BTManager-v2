"""
Burn registration for Bittensor subnets.
Only burn registration — no PoW.
Signed by COLDKEY (not hotkey).
"""

from typing import Optional
from core.substrate_client import SubstrateClient, rao_to_tao
from utils.logger import setup_logger

logger = setup_logger("registration")


async def get_registration_info(
    client: SubstrateClient,
    netuid: int,
) -> dict:
    """
    Get registration-related info for a subnet.
    Returns: {burn_cost_rao, burn_cost_tao, registration_allowed, max_neurons, current_neurons}
    """
    info = {"netuid": netuid}

    # Burn cost via direct storage query
    burn_rao = await client.get_burn_cost(netuid)
    info["burn_cost_rao"] = burn_rao
    info["burn_cost_tao"] = rao_to_tao(burn_rao)

    # Hyperparams for registration status
    params = await client.get_subnet_hyperparams(netuid)
    if params:
        info["registration_allowed"] = params.get("registration_allowed", True)
        info["max_regs_per_block"] = params.get("max_regs_per_block", 0)
    else:
        info["registration_allowed"] = True

    # Neuron count via subnet_info_v2 (more reliable)
    try:
        result = await client.substrate.runtime_call(
            api="SubnetInfoRuntimeApi",
            method="get_subnet_info_v2",
            params=[netuid],
        )
        sinfo = result.value if hasattr(result, "value") else result
        if isinstance(sinfo, dict):
            info["current_neurons"] = sinfo.get("subnetwork_n", 0)
            info["max_neurons"] = sinfo.get("max_allowed_uids", 0)
    except Exception:
        pass

    return info


async def check_registration_status(
    client: SubstrateClient,
    hotkey_ss58: str,
    netuid: int,
) -> Optional[int]:
    """
    Check if a hotkey is registered on a subnet.
    Returns UID if registered, None otherwise.
    """
    try:
        result = await client.substrate.query(
            module="SubtensorModule",
            storage_function="Uids",
            params=[netuid, hotkey_ss58],
        )
        if result is not None:
            val = result.value if hasattr(result, "value") else result
            if val is not None:
                return int(val)
        return None
    except Exception as e:
        logger.error(f"Failed to check registration: {e}")
        return None


async def burn_register(
    client: SubstrateClient,
    wallet,
    hotkey_ss58: str,
    netuid: int,
    check_balance: bool = True,
) -> tuple[bool, Optional[str], Optional[int]]:
    """
    Register a hotkey on a subnet via burn registration.
    
    IMPORTANT: Signed by COLDKEY (wallet.coldkey), not hotkey.
    
    Args:
        client: Connected SubstrateClient
        wallet: Wallet with unlocked coldkey
        hotkey_ss58: Hotkey SS58 address to register
        netuid: Subnet ID to register on
        check_balance: Pre-check if balance sufficient
        
    Returns:
        (success, error_message, uid)
        uid is the assigned UID if registration succeeded
    """
    # Pre-checks
    burn_rao = await client.get_burn_cost(netuid)
    burn_tao = rao_to_tao(burn_rao)
    logger.info(f"Burn cost for SN{netuid}: {burn_tao:.9f} TAO")

    if check_balance:
        balance = await client.get_balance(wallet.coldkeypub.ss58_address)
        if balance < burn_rao:
            return (
                False,
                f"Insufficient balance: {rao_to_tao(balance):.9f} TAO < {burn_tao:.9f} TAO burn cost",
                None,
            )

    # Check if already registered
    existing_uid = await check_registration_status(client, hotkey_ss58, netuid)
    if existing_uid is not None:
        return True, f"Already registered with UID {existing_uid}", existing_uid

    # Submit burned_register extrinsic
    logger.info(f"Submitting burn registration: SN{netuid} hotkey={hotkey_ss58[:12]}...")

    try:
        receipt = await client.compose_and_submit(
            call_module="SubtensorModule",
            call_function="burned_register",
            call_params={
                "netuid": netuid,
                "hotkey": hotkey_ss58,
            },
            keypair=wallet.coldkey,
            wait_for_inclusion=True,
        )

        if await receipt.is_success:
            # Try to get UID from events
            uid = None
            try:
                events = await receipt.triggered_events
                for event in events:
                    ev = event.value if hasattr(event, "value") else event
                    if isinstance(ev, dict):
                        event_id = ev.get("event_id", "")
                        if event_id == "NeuronRegistered":
                            attrs = ev.get("attributes", {})
                            uid = attrs.get("uid") or attrs.get(1)
                    elif hasattr(ev, "event_id") and ev.event_id == "NeuronRegistered":
                        uid = getattr(ev, "uid", None)
            except Exception:
                pass  # Event parsing is best-effort, UID is queried as fallback

            # Fallback: query UID directly
            if uid is None:
                uid = await check_registration_status(client, hotkey_ss58, netuid)

            logger.info(f"Registration successful! UID: {uid}")
            return True, None, uid
        else:
            error = await receipt.error_message
            error_str = str(error) if error else "Unknown error"
            logger.error(f"Registration failed: {error_str}")
            return False, error_str, None

    except Exception as e:
        logger.error(f"Registration exception: {e}")
        return False, str(e), None
