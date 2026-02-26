"""
Wallet stats and subnet overview.
Aggregates balance, stake, emission data with TAO/USD pricing.
"""

import asyncio
from typing import Optional
from core.substrate_client import SubstrateClient, rao_to_tao, decode_price, decode_bytes
from utils.logger import setup_logger

logger = setup_logger("stats")


async def fetch_tao_price() -> Optional[float]:
    """Fetch current TAO/USD price. Binance primary, CoinGecko fallback."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            # Binance (free, no API key)
            try:
                url = "https://api.binance.com/api/v3/ticker/price?symbol=TAOUSDT"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = float(data.get("price", 0))
                        if price > 0:
                            return price
            except Exception as e:
                logger.warning(f"Binance price failed: {e}")

            # CoinGecko fallback
            try:
                url = "https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("bittensor", {}).get("usd")
            except Exception as e:
                logger.warning(f"CoinGecko price failed: {e}")
    except Exception as e:
        logger.warning(f"Failed to fetch TAO price: {e}")
    return None


def decode_ss58(raw) -> str:
    """Decode raw account bytes to SS58 address."""
    if isinstance(raw, str):
        return raw
    # Handle ((byte, byte, ...),) wrapper format from chain
    if isinstance(raw, tuple) and len(raw) == 1 and isinstance(raw[0], tuple):
        raw = raw[0]
    if isinstance(raw, (tuple, list)) and len(raw) == 32:
        try:
            from scalecodec.utils.ss58 import ss58_encode
            return ss58_encode(bytes(raw), 42)
        except ImportError:
            try:
                from substrateinterface.utils.ss58 import ss58_encode
                return ss58_encode(bytes(raw), 42)
            except ImportError:
                return "0x" + bytes(raw).hex()
    return str(raw)


async def get_wallet_stats(
    client: SubstrateClient,
    coldkey_ss58: str,
    include_usd: bool = True,
) -> dict:
    """
    Get comprehensive wallet stats.

    Returns dict with balance, per-subnet stakes, totals in TAO/USD.
    """
    # Parallel queries
    tasks = {
        "balance": client.get_balance(coldkey_ss58),
        "stakes": client.get_stake_info_for_coldkey(coldkey_ss58),
        "dynamic": client.get_all_dynamic_info(),
    }
    if include_usd:
        tasks["price"] = fetch_tao_price()

    results = {}
    for key, task in tasks.items():
        try:
            results[key] = await task
        except Exception as e:
            logger.error(f"Failed to fetch {key}: {e}")
            results[key] = None

    # Build price map: netuid -> moving_price (decoded float)
    price_map = {}
    name_map = {}
    if results.get("dynamic"):
        for info in results["dynamic"]:
            if isinstance(info, dict):
                netuid = info.get("netuid", 0)
                price_map[netuid] = decode_price(info.get("moving_price", 0))
                # Prefer subnet_identity name, fallback to subnet_name
                identity = info.get("subnet_identity")
                if identity and isinstance(identity, dict):
                    name_raw = identity.get("subnet_name", info.get("subnet_name", ()))
                else:
                    name_raw = info.get("subnet_name", ())
                name_map[netuid] = decode_bytes(name_raw) if name_raw else f"SN{netuid}"

    # Process stake entries
    subnets = []
    total_staked_tao = 0.0
    total_emission_tao = 0.0

    stakes = results.get("stakes", []) or []
    for entry in stakes:
        if not isinstance(entry, dict):
            continue

        netuid = entry.get("netuid", 0)
        alpha_stake_rao = entry.get("stake", 0)
        emission = entry.get("emission", 0)
        tao_emission = entry.get("tao_emission", 0)
        is_registered = entry.get("is_registered", False)

        hotkey = decode_ss58(entry.get("hotkey", ""))

        alpha_tao = rao_to_tao(alpha_stake_rao)
        moving_price = price_map.get(netuid, 0.0)

        if netuid == 0:
            # Root subnet: stake IS in TAO
            tao_value = alpha_tao
        elif moving_price > 0:
            # moving_price = TAO per alpha (from I64F64)
            tao_value = alpha_tao * moving_price
        else:
            tao_value = 0.0

        emission_tao = rao_to_tao(tao_emission) if tao_emission else rao_to_tao(emission)

        total_staked_tao += tao_value
        total_emission_tao += emission_tao

        if alpha_stake_rao > 0 or is_registered:
            subnets.append({
                "netuid": netuid,
                "subnet_name": name_map.get(netuid, f"SN{netuid}"),
                "hotkey": hotkey,
                "alpha_stake": alpha_tao,
                "tao_value": tao_value,
                "emission": emission_tao,
                "is_registered": is_registered,
                "moving_price": moving_price,
            })

    subnets.sort(key=lambda x: x["tao_value"], reverse=True)

    free_balance_tao = rao_to_tao(results.get("balance", 0) or 0)
    total_value_tao = free_balance_tao + total_staked_tao

    tao_price = results.get("price")
    total_value_usd = total_value_tao * tao_price if tao_price else None

    return {
        "address": coldkey_ss58,
        "free_balance_tao": free_balance_tao,
        "total_staked_tao": total_staked_tao,
        "total_emission_tao": total_emission_tao,
        "total_value_tao": total_value_tao,
        "total_value_usd": total_value_usd,
        "tao_price_usd": tao_price,
        "subnets": subnets,
    }


async def get_subnet_overview(
    client: SubstrateClient,
    netuid: int,
) -> Optional[dict]:
    """Get overview info for a single subnet."""
    info = await client.get_subnet_dynamic_info(netuid)
    if not info:
        return None

    # Get burn cost via direct query
    burn_rao = await client.get_burn_cost(netuid)

    # Get hyperparams for registration status
    params = await client.get_subnet_hyperparams(netuid)

    # Get neuron count via subnet_info_v2 (has subnetwork_n and max_allowed_uids)
    sinfo = None
    try:
        result = await client.substrate.runtime_call(
            api="SubnetInfoRuntimeApi",
            method="get_subnet_info_v2",
            params=[netuid],
        )
        sinfo = result.value if hasattr(result, "value") else result
    except Exception:
        pass

    # Decode name from subnet_identity or subnet_name
    identity = info.get("subnet_identity")
    if identity and isinstance(identity, dict):
        name = decode_bytes(identity.get("subnet_name", info.get("subnet_name", ())))
    else:
        name = decode_bytes(info.get("subnet_name", ()))

    symbol = decode_bytes(info.get("token_symbol", ()))

    overview = {
        "netuid": netuid,
        "name": name or f"SN{netuid}",
        "symbol": symbol or "?",
        "tempo": info.get("tempo", 0),
        "tao_in": rao_to_tao(info.get("tao_in", 0)),
        "alpha_out": rao_to_tao(info.get("alpha_out", 0)),
        "moving_price": decode_price(info.get("moving_price", 0)),
        "burn_cost_tao": rao_to_tao(burn_rao),
        "burn_cost_rao": burn_rao,
    }

    if params:
        overview["registration_allowed"] = params.get("registration_allowed", True)
        overview["min_burn_tao"] = rao_to_tao(params.get("min_burn", 0))
        overview["max_burn_tao"] = rao_to_tao(params.get("max_burn", 0))

    if sinfo and isinstance(sinfo, dict):
        overview["neurons"] = sinfo.get("subnetwork_n", 0)
        overview["max_neurons"] = sinfo.get("max_allowed_uids", 0)

    return overview
