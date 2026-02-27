"""
Wallet stats and subnet overview.
Aggregates balance, stake, emission data with TAO/USD pricing.
Uses global neuron cache for fast registration lookups.
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


async def build_global_neuron_cache(client: SubstrateClient) -> dict:
    """
    Fetch neurons_lite from ALL subnets and build hotkey -> registrations map.
    Returns: {hotkey_ss58: [{netuid, uid, emission, incentive, ...}, ...]}
    Note: emission values are in alpha RAO per TEMPO (not per block).
    """
    netuids = await client.get_all_subnet_netuids()
    if not netuids:
        return {}

    async def fetch_neurons(netuid):
        try:
            result = await client.substrate.runtime_call(
                api="NeuronInfoRuntimeApi",
                method="get_neurons_lite",
                params=[netuid],
            )
            data = result.value if hasattr(result, "value") else result
            return netuid, data if isinstance(data, list) else []
        except Exception:
            return netuid, []

    BATCH = 25
    all_neurons = {}
    for i in range(0, len(netuids), BATCH):
        batch = netuids[i:i+BATCH]
        results = await asyncio.gather(*[fetch_neurons(n) for n in batch])
        for netuid, neurons in results:
            all_neurons[netuid] = neurons

    hotkey_map = {}
    for netuid, neurons in all_neurons.items():
        for n in neurons:
            if not isinstance(n, dict):
                continue
            hk = decode_ss58(n.get("hotkey", ""))
            if hk not in hotkey_map:
                hotkey_map[hk] = []
            hotkey_map[hk].append({
                "netuid": netuid,
                "uid": n.get("uid", 0),
                "emission": n.get("emission", 0),
                "incentive": n.get("incentive", 0),
                "trust": n.get("trust", 0),
                "dividends": n.get("dividends", 0),
                "active": n.get("active", False),
                "rank": n.get("rank", 0),
                "validator_trust": n.get("validator_trust", 0),
            })

    return hotkey_map


async def get_wallet_stats(
    client: SubstrateClient,
    coldkey_ss58: str,
    include_usd: bool = True,
    hotkey_ss58_list: list = None,
    neuron_cache: dict = None,
) -> dict:
    """
    Get comprehensive wallet stats.

    Args:
        neuron_cache: pre-built {hotkey -> [{netuid, uid, emission, ...}]} from build_global_neuron_cache()
                      emission values are alpha RAO per tempo.
    """
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

    price_map = {}
    name_map = {}
    tempo_map = {}
    if results.get("dynamic"):
        for info in results["dynamic"]:
            if isinstance(info, dict):
                netuid = info.get("netuid", 0)
                price_map[netuid] = decode_price(info.get("moving_price", 0))
                tempo_map[netuid] = info.get("tempo", 360)
                identity = info.get("subnet_identity")
                if identity and isinstance(identity, dict):
                    name_raw = identity.get("subnet_name", info.get("subnet_name", ()))
                else:
                    name_raw = info.get("subnet_name", ())
                name_map[netuid] = decode_bytes(name_raw) if name_raw else f"SN{netuid}"

    subnets = []
    total_staked_tao = 0.0
    total_emission_tao_per_block = 0.0
    seen_pairs = set()

    stakes = results.get("stakes", []) or []
    for entry in stakes:
        if not isinstance(entry, dict):
            continue

        netuid = entry.get("netuid", 0)
        hotkey = decode_ss58(entry.get("hotkey", ""))
        alpha_stake_rao = entry.get("stake", 0)
        alpha_tao = rao_to_tao(alpha_stake_rao)
        moving_price = price_map.get(netuid, 0.0)
        tempo = tempo_map.get(netuid, 360)

        if netuid == 0:
            tao_value = alpha_tao
        elif moving_price > 0:
            tao_value = alpha_tao * moving_price
        else:
            tao_value = 0.0

        total_staked_tao += tao_value

        # Lookup neuron data from cache for emission/uid
        neuron_data = None
        if neuron_cache:
            for nd in neuron_cache.get(hotkey, []):
                if nd["netuid"] == netuid:
                    neuron_data = nd
                    break

        if neuron_data:
            # emission is alpha RAO per tempo -> convert to TAO per block
            emission_alpha_per_tempo = rao_to_tao(neuron_data["emission"])
            emission_tao_per_tempo = emission_alpha_per_tempo * moving_price if moving_price > 0 else 0.0
            emission_tao_per_block = emission_tao_per_tempo / tempo if tempo > 0 else 0.0
            uid = neuron_data["uid"]
            incentive = neuron_data["incentive"]
            is_registered = True
        else:
            emission_tao_per_block = 0.0
            uid = None
            incentive = 0
            is_registered = entry.get("is_registered", False)

        total_emission_tao_per_block += emission_tao_per_block
        seen_pairs.add((hotkey, netuid))

        if alpha_stake_rao > 0 or is_registered:
            subnets.append({
                "netuid": netuid,
                "subnet_name": name_map.get(netuid, f"SN{netuid}"),
                "hotkey": hotkey,
                "uid": uid,
                "alpha_stake": alpha_tao,
                "tao_value": tao_value,
                "emission": emission_tao_per_block,
                "incentive": incentive,
                "is_registered": is_registered,
                "moving_price": moving_price,
            })

    # Add registered hotkeys with 0 stake (from neuron cache)
    if neuron_cache and hotkey_ss58_list:
        for hk in hotkey_ss58_list:
            for nd in neuron_cache.get(hk, []):
                netuid = nd["netuid"]
                if (hk, netuid) in seen_pairs:
                    continue
                seen_pairs.add((hk, netuid))
                mp = price_map.get(netuid, 0.0)
                tempo = tempo_map.get(netuid, 360)
                emission_alpha_per_tempo = rao_to_tao(nd["emission"])
                emission_tao_per_tempo = emission_alpha_per_tempo * mp if mp > 0 else 0.0
                emission_tao_per_block = emission_tao_per_tempo / tempo if tempo > 0 else 0.0
                total_emission_tao_per_block += emission_tao_per_block
                subnets.append({
                    "netuid": netuid,
                    "subnet_name": name_map.get(netuid, f"SN{netuid}"),
                    "hotkey": hk,
                    "uid": nd["uid"],
                    "alpha_stake": 0.0,
                    "tao_value": 0.0,
                    "emission": emission_tao_per_block,
                    "incentive": nd["incentive"],
                    "is_registered": True,
                    "moving_price": mp,
                })

    subnets.sort(key=lambda x: x["netuid"])

    free_balance_tao = rao_to_tao(results.get("balance", 0) or 0)
    total_value_tao = free_balance_tao + total_staked_tao

    tao_price = results.get("price")
    total_value_usd = total_value_tao * tao_price if tao_price else None

    return {
        "address": coldkey_ss58,
        "free_balance_tao": free_balance_tao,
        "total_staked_tao": total_staked_tao,
        "total_emission_tao_per_block": total_emission_tao_per_block,
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

    burn_rao = await client.get_burn_cost(netuid)
    params = await client.get_subnet_hyperparams(netuid)

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
