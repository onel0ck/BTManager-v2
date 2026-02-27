"""
Substrate client wrapper for direct RPC communication with Bittensor chain.
No btcli dependency — uses async-substrate-interface directly.
"""

import asyncio
from typing import Optional, Any
from async_substrate_interface import AsyncSubstrateInterface
from async_substrate_interface.substrate_addons import RetryAsyncSubstrate
from utils.logger import setup_logger

logger = setup_logger("substrate_client")

# Constants
RAO_PER_TAO = 1_000_000_000  # 1 TAO = 1e9 RAO
SS58_FORMAT = 42  # Bittensor SS58 format
I64F64_DIVISOR = 2**32  # I64F64 fixed-point: bits / 2^32 = real value


def rao_to_tao(rao: int) -> float:
    """Convert RAO to TAO."""
    return rao / RAO_PER_TAO


def tao_to_rao(tao: float) -> int:
    """Convert TAO to RAO."""
    return int(tao * RAO_PER_TAO)


def decode_price(price_raw) -> float:
    """
    Decode I64F64 fixed-point price from chain.
    Chain returns {'bits': int} where real_value = bits / 2^32.
    """
    if isinstance(price_raw, dict):
        bits = price_raw.get("bits", 0)
    elif isinstance(price_raw, (int, float)):
        bits = price_raw
    else:
        return 0.0
    return bits / I64F64_DIVISOR


def decode_bytes(data) -> str:
    """
    Decode byte tuple/list from chain into string.
    Chain returns tuples like (65, 112, 101, 120) for 'Apex'.
    """
    if isinstance(data, (tuple, list)):
        return bytes(data).decode("utf-8", errors="replace")
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    if isinstance(data, str):
        return data
    return str(data)


class SubstrateClient:
    """
    Async wrapper around AsyncSubstrateInterface for Bittensor chain operations.
    
    Usage:
        client = SubstrateClient()
        await client.connect("wss://entrypoint-finney.opentensor.ai:443")
        balance = await client.get_balance("5GrwvaEF...")
        await client.close()
    
    Or as async context manager:
        async with SubstrateClient("wss://...") as client:
            balance = await client.get_balance("5GrwvaEF...")
    """

    def __init__(self, url: str = None, fallbacks: list[str] = None):
        self.url = url
        self.fallbacks = fallbacks or []
        self.substrate: Optional[AsyncSubstrateInterface] = None
        self._connected = False

    async def connect(self, url: str = None, fallbacks: list[str] = None) -> None:
        """Connect to the chain."""
        url = url or self.url
        fallbacks = fallbacks or self.fallbacks

        if not url:
            raise ValueError("No RPC URL provided")

        logger.info(f"Connecting to {url}")

        if fallbacks:
            self.substrate = RetryAsyncSubstrate(
                url=url,
                fallback_chains=fallbacks,
                retry_forever=False,
                ss58_format=SS58_FORMAT,
                max_retries=5,
                retry_timeout=30.0,
            )
        else:
            self.substrate = AsyncSubstrateInterface(
                url=url,
                ss58_format=SS58_FORMAT,
            )

        await self.substrate.initialize()
        self._connected = True

        chain = self.substrate._chain
        logger.info(f"Connected to chain: {chain}")

    async def close(self) -> None:
        """Close connection."""
        if self.substrate:
            await self.substrate.close()
            self._connected = False
            logger.info("Connection closed")

    async def __aenter__(self):
        if not self._connected and self.url:
            await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _ensure_connected(self):
        if not self._connected or not self.substrate:
            raise ConnectionError("Not connected. Call connect() first.")

    # ========================================================================
    # Balance queries
    # ========================================================================

    async def get_balance(self, ss58_address: str) -> int:
        """Get free balance in RAO for an address."""
        self._ensure_connected()
        result = await self.substrate.query(
            module="System",
            storage_function="Account",
            params=[ss58_address],
        )
        if result is None:
            return 0
        # result is dict-like: {"nonce": ..., "data": {"free": ..., "reserved": ..., ...}}
        data = result.value if hasattr(result, "value") else result
        if isinstance(data, dict):
            return data.get("data", {}).get("free", 0)
        return 0

    async def get_balance_tao(self, ss58_address: str) -> float:
        """Get free balance in TAO."""
        return rao_to_tao(await self.get_balance(ss58_address))

    async def get_existential_deposit(self) -> int:
        """Get existential deposit (minimum balance) in RAO."""
        self._ensure_connected()
        result = await self.substrate.get_constant("Balances", "ExistentialDeposit")
        if result:
            return result.value if hasattr(result, "value") else int(result)
        return 500  # fallback default

    # ========================================================================
    # Stake info queries
    # ========================================================================

    async def get_stake_info_for_coldkey(self, coldkey_ss58: str) -> list:
        """
        Get all stake info for a coldkey across all subnets.
        Returns list of StakeInfo dicts with: hotkey, coldkey, netuid, stake, 
        emission, tao_emission, is_registered, etc.
        """
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="StakeInfoRuntimeApi",
                method="get_stake_info_for_coldkey",
                params=[coldkey_ss58],
            )
            data = result.value if hasattr(result, "value") else result
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to get stake info for {coldkey_ss58}: {e}")
            return []

    async def get_stake_for_hotkey_coldkey_netuid(
        self, hotkey_ss58: str, coldkey_ss58: str, netuid: int
    ) -> int:
        """Get alpha stake amount for specific hotkey/coldkey/netuid combo. Returns RAO."""
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="StakeInfoRuntimeApi",
                method="get_stake_info_for_hotkey_coldkey_netuid",
                params=[hotkey_ss58, coldkey_ss58, netuid],
            )
            data = result.value if hasattr(result, "value") else result
            if data and isinstance(data, dict):
                return data.get("stake", 0)
            return 0
        except Exception as e:
            logger.error(f"Failed to get stake: {e}")
            return 0

    # ========================================================================
    # Subnet info queries
    # ========================================================================

    async def get_all_subnet_netuids(self) -> list[int]:
        """Get list of all active subnet netuids."""
        self._ensure_connected()
        try:
            result = await self.substrate.query_map(
                module="SubtensorModule",
                storage_function="NetworksAdded",
            )
            netuids = []
            async for netuid, added in result:
                val = added.value if hasattr(added, "value") else added
                if val:
                    uid = netuid.value if hasattr(netuid, "value") else netuid
                    netuids.append(int(uid))
            return sorted(netuids)
        except Exception as e:
            logger.error(f"Failed to get subnet netuids: {e}")
            return []

    async def get_subnet_dynamic_info(self, netuid: int) -> Optional[dict]:
        """
        Get dynamic info for a subnet: prices, emissions, volume.
        Key fields: alpha_in, alpha_out, tao_in, moving_price, subnet_volume,
                    token_symbol, subnet_name, tempo
        """
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="SubnetInfoRuntimeApi",
                method="get_dynamic_info",
                params=[netuid],
            )
            data = result.value if hasattr(result, "value") else result
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error(f"Failed to get dynamic info for subnet {netuid}: {e}")
            return None

    async def get_all_dynamic_info(self) -> list:
        """Get dynamic info for all subnets."""
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="SubnetInfoRuntimeApi",
                method="get_all_dynamic_info",
                params=[],
            )
            data = result.value if hasattr(result, "value") else result
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to get all dynamic info: {e}")
            return []

    async def get_subnet_hyperparams(self, netuid: int) -> Optional[dict]:
        """Get subnet hyperparameters including burn cost, registration status, etc."""
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="SubnetInfoRuntimeApi",
                method="get_subnet_hyperparams",
                params=[netuid],
            )
            data = result.value if hasattr(result, "value") else result
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error(f"Failed to get hyperparams for subnet {netuid}: {e}")
            return None

    async def get_burn_cost(self, netuid: int) -> int:
        """Get current burn registration cost in RAO for a subnet via direct storage query."""
        self._ensure_connected()
        try:
            result = await self.substrate.query(
                module="SubtensorModule",
                storage_function="Burn",
                params=[netuid],
            )
            if result is not None:
                val = result.value if hasattr(result, "value") else result
                return int(val) if val else 0
            return 0
        except Exception as e:
            logger.warning(f"Direct Burn query failed for SN{netuid}, trying subnet_info_v2: {e}")
            # Fallback: get_subnet_info_v2 also has burn field
            try:
                result = await self.substrate.runtime_call(
                    api="SubnetInfoRuntimeApi",
                    method="get_subnet_info_v2",
                    params=[netuid],
                )
                data = result.value if hasattr(result, "value") else result
                if isinstance(data, dict):
                    return int(data.get("burn", 0))
            except Exception:
                pass
            return 0

    # ========================================================================
    # Metagraph queries
    # ========================================================================

    async def get_metagraph(self, netuid: int) -> Optional[dict]:
        """Get full metagraph for a subnet."""
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="SubnetInfoRuntimeApi",
                method="get_metagraph",
                params=[netuid],
            )
            data = result.value if hasattr(result, "value") else result
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error(f"Failed to get metagraph for subnet {netuid}: {e}")
            return None

    async def get_selective_metagraph(self, netuid: int, field_indices: list[int]) -> Optional[dict]:
        """
        Get selective metagraph fields. More efficient than full metagraph.
        
        Common field indices:
            52=hotkeys, 53=coldkeys, 55=axons, 56=active, 57=validator_permit,
            60=emission, 61=dividends, 62=incentives, 63=consensus, 64=trust,
            65=rank, 67=alpha_stake, 68=tao_stake, 69=total_stake,
            32=burn, 30=num_uids, 31=max_uids
        """
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="SubnetInfoRuntimeApi",
                method="get_selective_metagraph",
                params=[netuid, field_indices],
            )
            data = result.value if hasattr(result, "value") else result
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error(f"Failed to get selective metagraph for subnet {netuid}: {e}")
            return None

    # ========================================================================
    # Neuron info queries
    # ========================================================================

    async def get_neurons_lite(self, netuid: int) -> list:
        """Get lite neuron info for all neurons on a subnet."""
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="NeuronInfoRuntimeApi",
                method="get_neurons_lite",
                params=[netuid],
            )
            data = result.value if hasattr(result, "value") else result
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to get neurons for subnet {netuid}: {e}")
            return []

    async def get_uid_for_hotkey_on_subnet(self, netuid: int, hotkey_ss58: str):
        """Check if hotkey is registered on subnet via Uids storage. Returns uid or None."""
        self._ensure_connected()
        try:
            result = await self.substrate.query(
                module="SubtensorModule",
                storage_function="Uids",
                params=[netuid, hotkey_ss58],
            )
            val = result.value if hasattr(result, "value") else result
            if val is not None:
                return int(val)
            return None
        except Exception:
            return None

    async def get_registered_subnets_for_hotkeys(
        self, hotkey_ss58_list: list[str], netuids: list[int]
    ) -> dict:
        """
        For each hotkey, find which subnets it's registered on.
        Returns: {hotkey_ss58: [(netuid, uid), ...]}
        """
        self._ensure_connected()
        result_map = {hk: [] for hk in hotkey_ss58_list}

        tasks = []
        task_keys = []
        for hk in hotkey_ss58_list:
            for netuid in netuids:
                tasks.append(self.get_uid_for_hotkey_on_subnet(netuid, hk))
                task_keys.append((hk, netuid))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for (hk, netuid), res in zip(task_keys, results):
            if isinstance(res, Exception) or res is None:
                continue
            result_map[hk].append((netuid, res))

        return result_map

    async def get_neuron_info_for_uid(self, netuid: int, uid: int):
        """Get neuron lite info for a specific uid on a subnet."""
        self._ensure_connected()
        try:
            result = await self.substrate.runtime_call(
                api="NeuronInfoRuntimeApi",
                method="get_neuron_lite",
                params=[netuid, uid],
            )
            data = result.value if hasattr(result, "value") else result
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    # ========================================================================
    # Block info
    # ========================================================================

    async def get_current_block(self) -> int:
        """Get current block number."""
        self._ensure_connected()
        head = await self.substrate.get_chain_head()
        return await self.substrate.get_block_number(head)

    # ========================================================================
    # Extrinsic submission
    # ========================================================================

    async def compose_and_submit(
        self,
        call_module: str,
        call_function: str,
        call_params: dict,
        keypair,
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = False,
        era: Optional[dict] = None,
        nonce: Optional[int] = None,
    ):
        """
        Compose, sign, and submit an extrinsic.
        
        Args:
            call_module: e.g. "SubtensorModule"
            call_function: e.g. "add_stake"
            call_params: dict of parameters
            keypair: signing keypair (wallet.coldkey or wallet.hotkey)
            wait_for_inclusion: wait for block inclusion
            wait_for_finalization: wait for finalization
            era: mortality period, e.g. {"period": 64}
            nonce: explicit nonce, auto-fetched if None
            
        Returns:
            AsyncExtrinsicReceipt
        """
        self._ensure_connected()

        call = await self.substrate.compose_call(
            call_module=call_module,
            call_function=call_function,
            call_params=call_params,
        )

        extrinsic = await self.substrate.create_signed_extrinsic(
            call=call,
            keypair=keypair,
            era=era,
            nonce=nonce,
        )

        receipt = await self.substrate.submit_extrinsic(
            extrinsic,
            wait_for_inclusion=wait_for_inclusion,
            wait_for_finalization=wait_for_finalization,
        )

        return receipt

    async def compose_and_submit_checked(
        self,
        call_module: str,
        call_function: str,
        call_params: dict,
        keypair,
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """
        Submit extrinsic and return (success, error_message).
        Convenience wrapper that handles receipt checking.
        """
        try:
            receipt = await self.compose_and_submit(
                call_module=call_module,
                call_function=call_function,
                call_params=call_params,
                keypair=keypair,
                wait_for_inclusion=wait_for_inclusion,
                wait_for_finalization=wait_for_finalization,
            )

            if await receipt.is_success:
                return True, None
            else:
                error = await receipt.error_message
                error_str = str(error) if error else "Unknown error"
                return False, error_str

        except Exception as e:
            return False, str(e)
