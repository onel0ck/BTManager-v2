"""
Interactive menu system using Rich.
"""

import asyncio
from rich.prompt import Prompt, IntPrompt, Confirm, FloatPrompt

from core.substrate_client import SubstrateClient, rao_to_tao, tao_to_rao
from core.wallet_ops import (
    list_wallets, load_wallet, get_coldkey_ss58,
    create_coldkey_with_hotkeys, add_hotkeys_to_wallet, create_hotkey,
)
from core.balance import check_balance, check_all_balances
from core.staking import remove_stake, unstake_all, unstake_subnet
from core.registration import burn_register, get_registration_info, check_registration_status
from core.transfer import transfer_tao, transfer_tao_keep_alive
from core.stats import get_wallet_stats, get_subnet_overview, fetch_tao_price
from ui.display import (
    console, print_header, print_success, print_error, print_warn, print_info,
    display_balance_table, display_wallet_stats, display_multi_wallet_stats,
    display_subnet_overview, display_wallet_list,
)

MENU_OPTIONS = [
    ("1", "Create Wallet (Coldkey/Hotkey)"),
    ("2", "Check Balances"),
    ("3", "Wallet Stats"),
    ("4", "Register (Burn)"),
    ("5", "Transfer TAO"),
    ("6", "Unstake"),
    ("7", "Subnet Info"),
    ("0", "Exit"),
]


def show_main_menu():
    console.print("\n[bold cyan]╔══════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║[/bold cyan]    [bold white]Bittensor Manager v2[/bold white]              [bold cyan]║[/bold cyan]")
    console.print("[bold cyan]╚══════════════════════════════════════╝[/bold cyan]")
    for key, label in MENU_OPTIONS:
        if key == "0":
            console.print(f"  [dim]{key}.[/dim] [dim]{label}[/dim]")
        else:
            console.print(f"  [cyan]{key}.[/cyan] {label}")
    console.print()


# ========================================================================
# Wallet selection helpers
# ========================================================================

def _resolve_wallets(input_str: str, wallets: list[dict]) -> list[dict]:
    input_str = input_str.strip()
    if input_str.lower() == "all":
        return wallets

    parts = [p.strip() for p in input_str.split(",") if p.strip()]
    result = []
    name_map = {w["name"]: w for w in wallets}

    for part in parts:
        if part in name_map:
            result.append(name_map[part])
            continue
        try:
            idx = int(part)
            if 1 <= idx <= len(wallets):
                result.append(wallets[idx - 1])
                continue
        except ValueError:
            pass
        matches = [w for w in wallets if w["name"].startswith(part)]
        if matches:
            result.extend(matches)
        else:
            console.print(f"  [yellow]'{part}' not found, skipping[/yellow]")

    seen = set()
    deduped = []
    for w in result:
        if w["name"] not in seen:
            seen.add(w["name"])
            deduped.append(w)
    return deduped


def select_wallets(base_path: str, prompt: str = "Select wallet(s)", allow_multi: bool = True) -> list[dict]:
    wallets = list_wallets(base_path)
    if not wallets:
        print_warn("No wallets found. Create one first.")
        return []
    display_wallet_list(wallets)
    hint = " (name, #, comma-separated, or 'all')" if allow_multi else " (name or #)"
    user_input = Prompt.ask(f"{prompt}{hint}")
    selected = _resolve_wallets(user_input, wallets)
    if not selected:
        print_error("No wallets selected")
    return selected


def select_single_wallet(base_path: str, prompt: str = "Select wallet") -> dict | None:
    result = select_wallets(base_path, prompt=prompt, allow_multi=False)
    return result[0] if result else None


def select_hotkey(wallet: dict) -> str | None:
    hotkeys = wallet.get("hotkeys", [])
    if not hotkeys:
        print_warn(f"No hotkeys for {wallet['name']}")
        return None
    if len(hotkeys) == 1:
        return hotkeys[0]

    console.print(f"\n  Hotkeys for [cyan]{wallet['name']}[/cyan] ({len(hotkeys)} total):")
    for i, hk in enumerate(hotkeys, 1):
        console.print(f"    {i}. {hk}")

    user_input = Prompt.ask("Select hotkey (name, #, or 'all')")
    if user_input.lower() == "all":
        return "all"
    if user_input in hotkeys:
        return user_input
    try:
        idx = int(user_input)
        if 1 <= idx <= len(hotkeys):
            return hotkeys[idx - 1]
    except ValueError:
        pass
    print_error("Invalid hotkey selection")
    return None


# ========================================================================
# 1. Create Wallet
# ========================================================================

async def handle_create_wallet(config: dict):
    print_header("Create Wallet")
    base_path = config["wallet"]["base_path"]

    console.print("  [cyan]1.[/cyan] Create new coldkey (+ hotkeys)")
    console.print("  [cyan]2.[/cyan] Add hotkeys to existing coldkey")
    choice = Prompt.ask("Select", choices=["1", "2"])

    if choice == "1":
        name = Prompt.ask("Coldkey name")
        wallets = list_wallets(base_path)
        existing_names = {w["name"] for w in wallets}
        if name in existing_names:
            print_error(f"Wallet '{name}' already exists!")
            return

        hotkey_count = IntPrompt.ask("Number of hotkeys", default=20)
        use_pw = Confirm.ask("Encrypt coldkey with password?", default=False)

        console.print(f"  Creating [cyan]{name}[/cyan] with {hotkey_count} hotkeys...")
        try:
            wallet, created = create_coldkey_with_hotkeys(
                name, hotkey_count, use_password=use_pw, base_path=base_path
            )
            print_success(f"Created {name}: {wallet.coldkeypub.ss58_address}")
            print_success(f"Created {created} hotkeys (1-{created})")
        except Exception as e:
            print_error(f"Failed: {e}")
    else:
        w = select_single_wallet(base_path, "Select coldkey to add hotkeys")
        if not w:
            return
        current = len(w["hotkeys"])
        console.print(f"  [cyan]{w['name']}[/cyan] currently has {current} hotkeys")
        count = IntPrompt.ask("How many hotkeys to add")
        console.print(f"  Adding {count} hotkeys to [cyan]{w['name']}[/cyan]...")
        try:
            start, end = add_hotkeys_to_wallet(w["name"], count, base_path=base_path)
            print_success(f"Created hotkeys {start}-{end} for {w['name']}")
        except Exception as e:
            print_error(f"Failed: {e}")


# ========================================================================
# 2. Check Balances
# ========================================================================

async def handle_check_balances(client: SubstrateClient, config: dict):
    print_header("Check Balances")
    base_path = config["wallet"]["base_path"]
    wallets = list_wallets(base_path)
    if not wallets:
        print_warn("No wallets found.")
        return

    addresses = []
    for w in wallets:
        addr = get_coldkey_ss58(w["name"], base_path)
        if addr:
            addresses.append({"name": w["name"], "address": addr})
    if not addresses:
        print_warn("No valid coldkey addresses found.")
        return

    console.print(f"  Checking {len(addresses)} wallets...")
    tao_price = await fetch_tao_price()

    async def get_balance_with_stake(a):
        bal = await check_balance(client, a["address"])
        bal["name"] = a["name"]
        try:
            stats = await get_wallet_stats(client, a["address"], include_usd=False)
            bal["staked_tao"] = stats.get("total_staked_tao", 0.0)
        except Exception:
            bal["staked_tao"] = 0.0
        return bal

    tasks = [get_balance_with_stake(a) for a in addresses]
    balances = await asyncio.gather(*tasks, return_exceptions=True)
    balances = [b for b in balances if not isinstance(b, Exception)]

    display_balance_table(balances, tao_price=tao_price)


# ========================================================================
# 3. Wallet Stats
# ========================================================================

async def handle_wallet_stats(client: SubstrateClient, config: dict):
    print_header("Wallet Stats")
    base_path = config["wallet"]["base_path"]
    selected = select_wallets(base_path, "Select wallet(s) for stats")
    if not selected:
        return

    show_usd = config.get("display", {}).get("show_usd_prices", True)

    # Build global neuron cache once (all subnets, ~10s)
    console.print("  [dim]Loading neuron data from all subnets...[/dim]")
    from core.stats import build_global_neuron_cache
    neuron_cache = await build_global_neuron_cache(client)
    console.print(f"  [dim]Cached {len(neuron_cache)} hotkeys[/dim]")

    all_stats = []
    for w in selected:
        addr = get_coldkey_ss58(w["name"], base_path)
        if not addr:
            print_warn(f"Could not load address for {w['name']}")
            continue
        console.print(f"  Loading stats for [cyan]{w['name']}[/cyan]...")

        # Load hotkey SS58 addresses for registration checks
        hotkey_ss58_list = []
        from bittensor_wallet import Wallet
        for hk_name in (w.get("hotkeys") or []):
            try:
                hw = Wallet(name=w["name"], hotkey=hk_name, path=base_path)
                hotkey_ss58_list.append(hw.hotkey.ss58_address)
            except Exception:
                pass

        stats = await get_wallet_stats(
            client, addr, include_usd=show_usd,
            hotkey_ss58_list=hotkey_ss58_list,
            neuron_cache=neuron_cache,
        )
        all_stats.append((w["name"], stats))

    if all_stats:
        display_multi_wallet_stats(all_stats)


# ========================================================================
# 4. Register (Burn)
# ========================================================================

async def handle_register(client: SubstrateClient, config: dict):
    print_header("Burn Registration")
    base_path = config["wallet"]["base_path"]

    w = select_single_wallet(base_path)
    if not w:
        return

    hk_name = select_hotkey(w)
    if not hk_name:
        return

    hotkey_names = w["hotkeys"] if hk_name == "all" else [hk_name]
    netuid = IntPrompt.ask("Subnet ID (netuid)")

    info = await get_registration_info(client, netuid)
    tao_price = await fetch_tao_price()
    burn_tao = info["burn_cost_tao"]
    burn_usd = f" (${burn_tao * tao_price:.4f})" if tao_price else ""
    console.print(f"\n  Burn cost: [yellow]{burn_tao:.9f} TAO{burn_usd}[/yellow]")
    if info.get("current_neurons") is not None:
        console.print(f"  Neurons: {info['current_neurons']} / {info.get('max_neurons', '?')}")

    if len(hotkey_names) > 1:
        if not Confirm.ask(f"Register {len(hotkey_names)} hotkeys on SN{netuid}?"):
            return

    wallet_obj = None
    for hk in hotkey_names:
        wallet = load_wallet(w["name"], hk, base_path)
        hotkey_ss58 = wallet.hotkey.ss58_address
        console.print(f"\n  Hotkey {hk}: [dim]{hotkey_ss58}[/dim]")

        uid = await check_registration_status(client, hotkey_ss58, netuid)
        if uid is not None:
            print_success(f"Already registered on SN{netuid} with UID {uid}")
            continue

        if len(hotkey_names) == 1:
            if not Confirm.ask(f"Register on SN{netuid} for {burn_tao:.9f} TAO?"):
                return

        if wallet_obj is None:
            console.print("  [dim]Unlocking coldkey...[/dim]")
            _ = wallet.coldkey
            wallet_obj = wallet

        console.print("  [dim]Submitting registration...[/dim]")
        success, error, uid = await burn_register(client, wallet, hotkey_ss58, netuid)
        if success:
            print_success(f"Registered on SN{netuid}! UID: {uid}")
        else:
            print_error(f"Registration failed: {error}")


# ========================================================================
# 5. Transfer TAO
# ========================================================================

async def handle_transfer(client: SubstrateClient, config: dict):
    print_header("Transfer TAO")
    base_path = config["wallet"]["base_path"]

    console.print("  [cyan]1.[/cyan] Single transfer")
    console.print("  [cyan]2.[/cyan] Batch transfer (one sender → multiple destinations)")
    console.print("  [cyan]3.[/cyan] Collect (multiple wallets → one destination)")
    mode = Prompt.ask("Select mode", choices=["1", "2", "3"], default="1")

    if mode == "1":
        await _transfer_single(client, base_path)
    elif mode == "2":
        await _transfer_batch(client, base_path)
    else:
        await _transfer_collect(client, base_path)


async def _transfer_single(client, base_path):
    w = select_single_wallet(base_path, "Select source wallet")
    if not w:
        return
    wallet = load_wallet(w["name"], base_path=base_path)
    addr = wallet.coldkeypub.ss58_address
    bal = await check_balance(client, addr)
    console.print(f"  Source: [cyan]{w['name']}[/cyan] ({addr})")
    console.print(f"  Available: [green]{bal['free_tao']:.4f} TAO[/green]")

    dest = Prompt.ask("Destination SS58 address")
    amount = FloatPrompt.ask("Amount (TAO)")
    if amount <= 0 or amount > bal["free_tao"]:
        print_error("Invalid amount")
        return
    if not Confirm.ask(f"Send {amount} TAO to {dest}?"):
        return

    console.print("  [dim]Unlocking coldkey...[/dim]")
    _ = wallet.coldkey
    console.print("  [dim]Submitting transfer...[/dim]")
    success, error = await transfer_tao_keep_alive(client, wallet, dest, amount)
    if success:
        print_success(f"Transferred {amount} TAO")
    else:
        print_error(f"Transfer failed: {error}")


async def _transfer_batch(client, base_path):
    w = select_single_wallet(base_path, "Select source wallet")
    if not w:
        return
    wallet = load_wallet(w["name"], base_path=base_path)
    addr = wallet.coldkeypub.ss58_address
    bal = await check_balance(client, addr)
    console.print(f"  Source: [cyan]{w['name']}[/cyan] ({addr})")
    console.print(f"  Available: [green]{bal['free_tao']:.4f} TAO[/green]")

    transfers = []
    console.print("  Enter destinations (empty line to finish):")
    while True:
        dest = Prompt.ask("  Dest SS58 (or empty to stop)", default="")
        if not dest:
            break
        amount = FloatPrompt.ask("  Amount TAO")
        if amount > 0:
            transfers.append((dest, amount))
    if not transfers:
        print_warn("No transfers entered")
        return

    total = sum(a for _, a in transfers)
    console.print(f"\n  Total: [yellow]{total:.4f} TAO[/yellow] to {len(transfers)} addresses")
    if total > bal["free_tao"]:
        print_error("Insufficient balance")
        return
    if not Confirm.ask("Proceed with batch transfer?"):
        return

    console.print("  [dim]Unlocking coldkey...[/dim]")
    _ = wallet.coldkey
    for dest, amount in transfers:
        console.print(f"  Sending {amount} TAO → {dest[:20]}...")
        success, error = await transfer_tao_keep_alive(client, wallet, dest, amount)
        if success:
            print_success(f"Sent {amount} TAO")
        else:
            print_error(f"Failed: {error}")


async def _transfer_collect(client, base_path):
    dest = Prompt.ask("Destination SS58 address")
    leave_behind = FloatPrompt.ask("TAO to leave in each wallet (for fees)", default=0.01)

    selected = select_wallets(base_path, "Select source wallet(s)")
    if not selected:
        return

    send_list = []
    for w in selected:
        addr = get_coldkey_ss58(w["name"], base_path)
        if not addr:
            continue
        bal = await check_balance(client, addr)
        available = bal["free_tao"] - leave_behind
        if available > 0.0001:
            send_list.append((w, addr, available))
            console.print(f"  {w['name']:>12}: {bal['free_tao']:.4f} TAO → send {available:.4f}")

    if not send_list:
        print_warn("No wallets with sufficient balance")
        return

    total = sum(a for _, _, a in send_list)
    console.print(f"\n  Total to collect: [yellow]{total:.4f} TAO[/yellow] from {len(send_list)} wallets")
    console.print(f"  Destination: {dest}")
    if not Confirm.ask("Proceed with collect?"):
        return

    for w, addr, amount in send_list:
        console.print(f"  Collecting from {w['name']}...")
        wallet = load_wallet(w["name"], base_path=base_path)
        _ = wallet.coldkey
        success, error = await transfer_tao_keep_alive(client, wallet, dest, amount)
        if success:
            print_success(f"Collected {amount:.4f} TAO from {w['name']}")
        else:
            print_error(f"Failed {w['name']}: {error}")


# ========================================================================
# 6. Unstake
# ========================================================================

async def handle_unstake(client: SubstrateClient, config: dict):
    print_header("Unstake")
    base_path = config["wallet"]["base_path"]

    console.print("  [cyan]1.[/cyan] Unstake ALL (find staked hotkeys, unstake each)")
    console.print("  [cyan]2.[/cyan] Unstake from specific subnet (full)")
    console.print("  [cyan]3.[/cyan] Unstake specific amount from subnet")
    choice = Prompt.ask("Select", choices=["1", "2", "3"])

    if choice == "1":
        selected = select_wallets(base_path, "Select wallet(s) to unstake ALL")
        if not selected:
            return

        # First pass: find all staked hotkeys across all selected wallets
        unstake_plan = []  # list of (wallet_dict, addr, staked_hotkeys_set)
        for w in selected:
            addr = get_coldkey_ss58(w["name"], base_path)
            if not addr:
                print_warn(f"Could not load address for {w['name']}")
                continue

            console.print(f"  [dim]Checking {w['name']}...[/dim]")
            try:
                stake_entries = await client.get_stake_info_for_coldkey(addr)
            except Exception as e:
                print_error(f"Failed to query stakes for {w['name']}: {e}")
                continue

            if not stake_entries:
                continue

            from core.stats import decode_ss58
            staked_hotkeys = set()
            for entry in stake_entries:
                if isinstance(entry, dict):
                    stake = entry.get("stake", 0)
                    if stake and stake > 0:
                        hk = decode_ss58(entry.get("hotkey", ""))
                        if hk:
                            staked_hotkeys.add(hk)

            if staked_hotkeys:
                unstake_plan.append((w, addr, staked_hotkeys))
                console.print(f"  {w['name']}: {len(staked_hotkeys)} hotkey(s) with stake")

        if not unstake_plan:
            print_info("No staked hotkeys found across selected wallets")
            return

        total_hotkeys = sum(len(hks) for _, _, hks in unstake_plan)
        console.print(f"\n  Total: [yellow]{total_hotkeys} hotkeys[/yellow] across [yellow]{len(unstake_plan)} wallets[/yellow]")
        if not Confirm.ask("Unstake all?"):
            return

        # Execute
        for w, addr, staked_hotkeys in unstake_plan:
            console.print(f"\n  [cyan]{w['name']}[/cyan] ({len(staked_hotkeys)} hotkeys)")
            wallet = load_wallet(w["name"], base_path=base_path)
            console.print("  [dim]Unlocking coldkey...[/dim]")
            _ = wallet.coldkey

            for hk_ss58 in staked_hotkeys:
                console.print(f"  Unstaking {hk_ss58[:16]}...")
                try:
                    success, error = await unstake_all(client, wallet, hk_ss58)
                    if success:
                        print_success(f"Unstaked {hk_ss58[:16]}...")
                    else:
                        print_error(f"{hk_ss58[:16]}: {error}")
                except Exception as e:
                    print_error(f"{hk_ss58[:16]}: {e}")

    elif choice == "2":
        w = select_single_wallet(base_path)
        if not w:
            return
        hk_name = select_hotkey(w)
        if not hk_name:
            return
        netuid = IntPrompt.ask("Subnet ID (netuid)")
        hotkey_names = w["hotkeys"] if hk_name == "all" else [hk_name]

        wallet_obj = None
        for hk in hotkey_names:
            wallet = load_wallet(w["name"], hk, base_path)
            hotkey_ss58 = wallet.hotkey.ss58_address
            if wallet_obj is None:
                console.print("  [dim]Unlocking coldkey...[/dim]")
                _ = wallet.coldkey
                wallet_obj = wallet
            console.print(f"  Unstaking {hk} from SN{netuid}...")
            success, error = await unstake_subnet(client, wallet, hotkey_ss58, netuid)
            if success:
                print_success(f"Unstaked {hk} from SN{netuid}")
            else:
                if error and "NotEnoughStake" in str(error):
                    print_info(f"{hk}: no stake")
                else:
                    print_error(f"{hk}: {error}")

    else:
        w = select_single_wallet(base_path)
        if not w:
            return
        hk_name = select_hotkey(w)
        if not hk_name or hk_name == "all":
            print_error("Select a specific hotkey for partial unstake")
            return
        wallet = load_wallet(w["name"], hk_name, base_path)
        hotkey_ss58 = wallet.hotkey.ss58_address
        netuid = IntPrompt.ask("Subnet ID (netuid)")
        amount = FloatPrompt.ask("Amount of ALPHA to unstake")
        if amount <= 0:
            print_error("Amount must be > 0")
            return
        if not Confirm.ask(f"Unstake {amount} alpha from SN{netuid}?"):
            return
        console.print("  [dim]Unlocking coldkey...[/dim]")
        _ = wallet.coldkey
        success, error = await remove_stake(client, wallet, hotkey_ss58, netuid, amount)
        if success:
            print_success(f"Unstaked {amount} alpha from SN{netuid}")
        else:
            print_error(f"Unstake failed: {error}")


# ========================================================================
# 7. Subnet Info
# ========================================================================

async def handle_subnet_info(client: SubstrateClient, config: dict):
    print_header("Subnet Info")
    netuid = IntPrompt.ask("Subnet ID (netuid)")
    console.print(f"  Loading SN{netuid} info...")
    info, tao_price = await asyncio.gather(
        get_subnet_overview(client, netuid),
        fetch_tao_price()
    )
    if info:
        display_subnet_overview(info, tao_price=tao_price)
    else:
        print_error(f"Could not load info for SN{netuid}")


# ========================================================================
# Main loop
# ========================================================================

HANDLERS = {
    "1": handle_create_wallet,
    "2": handle_check_balances,
    "3": handle_wallet_stats,
    "4": handle_register,
    "5": handle_transfer,
    "6": handle_unstake,
    "7": handle_subnet_info,
}


async def main_menu_loop(client: SubstrateClient, config: dict):
    while True:
        show_main_menu()
        choice = Prompt.ask("Select option", default="0")
        if choice == "0":
            console.print("\n  [dim]Goodbye![/dim]\n")
            break
        handler = HANDLERS.get(choice)
        if handler:
            try:
                if choice == "1":
                    await handler(config)
                else:
                    await handler(client, config)
            except KeyboardInterrupt:
                console.print("\n  [dim]Cancelled[/dim]")
            except Exception as e:
                print_error(f"Error: {e}")
                import traceback
                traceback.print_exc()
        else:
            print_warn("Invalid option")
