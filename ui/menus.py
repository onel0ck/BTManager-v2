
"""
Interactive menu system using Rich.
"""

import asyncio
from rich.prompt import Prompt, IntPrompt, Confirm, FloatPrompt

from core.substrate_client import SubstrateClient, rao_to_tao, tao_to_rao
from core.wallet_ops import (
    list_wallets, load_wallet, get_coldkey_ss58,
    create_coldkey_with_hotkeys, add_hotkeys_to_wallet, create_hotkey,
    batch_create_wallets,
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
from utils.wallet_groups import load_groups, create_group, delete_group, get_group, list_group_names

MENU_OPTIONS = [
    ("1", "Create Wallet (Coldkey/Hotkey)"),
    ("2", "Check Balances"),
    ("3", "Wallet Stats"),
    ("4", "Register (Burn)"),
    ("5", "Transfer TAO"),
    ("6", "Unstake"),
    ("7", "Subnet Info"),
    ("8", "Wallet Groups"),
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

    # Check for group: prefix (e.g. "group:sn-11")
    if input_str.lower().startswith("group:"):
        group_name = input_str[6:].strip()
        group_wallets = get_group(group_name)
        if group_wallets is None:
            console.print(f"  [red]Group '{group_name}' not found[/red]")
            return []
        # Convert group wallet names to wallet dicts
        name_map = {w["name"]: w for w in wallets}
        result = []
        for wn in group_wallets:
            if wn in name_map:
                result.append(name_map[wn])
            else:
                console.print(f"  [yellow]'{wn}' from group not found, skipping[/yellow]")
        return result

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

    # Show available groups if any
    group_names = list_group_names()
    if group_names and allow_multi:
        groups_str = ", ".join(group_names)
        console.print(f"  [dim]Groups: {groups_str}[/dim]")

    hint = " (name, #, comma-separated, 'all', or 'group:name')" if allow_multi else " (name or #)"
    user_input = Prompt.ask(f"{prompt}{hint}")
    selected = _resolve_wallets(user_input, wallets)
    if not selected:
        print_error("No wallets selected")
    return selected


def select_single_wallet(base_path: str, prompt: str = "Select wallet") -> dict | None:
    result = select_wallets(base_path, prompt=prompt, allow_multi=False)
    return result[0] if result else None


def select_hotkey(wallet: dict) -> list[str] | None:
    hotkeys = wallet.get("hotkeys", [])
    if not hotkeys:
        print_warn(f"No hotkeys for {wallet['name']}")
        return None
    if len(hotkeys) == 1:
        return hotkeys

    console.print(f"\n  Hotkeys for [cyan]{wallet['name']}[/cyan] ({len(hotkeys)} total):")
    for hk in hotkeys:
        console.print(f"    {hk}")

    user_input = Prompt.ask("Select hotkey (name, comma-separated, or 'all')")
    if user_input.lower() == "all":
        return hotkeys

    parts = [p.strip() for p in user_input.split(",") if p.strip()]
    result = []
    for part in parts:
        if part in hotkeys:
            result.append(part)
        else:
            print_error(f"Hotkey '{part}' not found")
            return None
    return result if result else None


# ========================================================================
# 1. Create Wallet
# ========================================================================

async def handle_create_wallet(config: dict):
    print_header("Create Wallet")
    base_path = config["wallet"]["base_path"]

    console.print("  [cyan]1.[/cyan] Create new coldkey (+ hotkeys)")
    console.print("  [cyan]2.[/cyan] Add hotkeys to existing coldkey")
    console.print("  [cyan]3.[/cyan] Batch create multiple wallets")
    choice = Prompt.ask("Select", choices=["1", "2", "3"])

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
    elif choice == "2":
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
    else:
        # Batch create multiple wallets
        base_name = Prompt.ask("Base name (e.g. wallet_reg)")
        coldkey_count = IntPrompt.ask("Number of coldkeys to create")
        hotkey_count = IntPrompt.ask("Number of hotkeys per coldkey", default=5)
        use_pw = Confirm.ask("Encrypt coldkeys with password?", default=False)

        console.print(
            f"\n  Will create [cyan]{coldkey_count}[/cyan] wallets: "
            f"[cyan]{base_name}_1[/cyan] ... [cyan]{base_name}_{coldkey_count}[/cyan]"
        )
        console.print(f"  Each with [cyan]{hotkey_count}[/cyan] hotkeys (1-{hotkey_count})")
        total = coldkey_count * hotkey_count
        console.print(f"  Total: [yellow]{coldkey_count} coldkeys + {total} hotkeys[/yellow]")

        if not Confirm.ask("Proceed?"):
            return

        def on_progress(name, msg):
            console.print(f"  [dim]{name}:[/dim] {msg}")

        try:
            results = batch_create_wallets(
                base_name=base_name,
                coldkey_count=coldkey_count,
                hotkey_count=hotkey_count,
                use_password=use_pw,
                base_path=base_path,
                on_progress=on_progress,
            )
            console.print()
            print_success(f"Created {len(results)} wallets:")
            for name, ss58, hk_count in results:
                console.print(f"    [cyan]{name}[/cyan]: {ss58} ({hk_count} hotkeys)")
        except Exception as e:
            print_error(f"Batch creation failed: {e}")


# ========================================================================
# 2. Check Balances
# ========================================================================

async def handle_check_balances(client: SubstrateClient, config: dict):
    print_header("Check Balances")
    base_path = config["wallet"]["base_path"]

    selected = select_wallets(base_path, "Select wallet(s) for balance check")
    if not selected:
        return

    addresses = []
    for w in selected:
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
        hotkey_name_map = {}  # ss58 -> hotkey name
        from bittensor_wallet import Wallet
        for hk_name in (w.get("hotkeys") or []):
            try:
                hw = Wallet(name=w["name"], hotkey=hk_name, path=base_path)
                hk_ss58 = hw.hotkey.ss58_address
                hotkey_ss58_list.append(hk_ss58)
                hotkey_name_map[hk_ss58] = hk_name
            except Exception:
                pass

        stats = await get_wallet_stats(
            client, addr, include_usd=show_usd,
            hotkey_ss58_list=hotkey_ss58_list,
            neuron_cache=neuron_cache,
            hotkey_name_map=hotkey_name_map,
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

    hk_names = select_hotkey(w)
    if not hk_names:
        return

    hotkey_names = hk_names
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

    console.print("\n  [cyan]1.[/cyan] Enter destinations one by one (SS58 + amount each)")
    console.print("  [cyan]2.[/cyan] Send same amount to multiple wallets (names or SS58, comma-separated)")
    mode = Prompt.ask("Select", choices=["1", "2"], default="2")

    transfers = []  # list of (dest_ss58, amount, label)

    if mode == "1":
        console.print("  Enter destinations (empty line to finish):")
        while True:
            dest = Prompt.ask("  Dest SS58 (or empty to stop)", default="")
            if not dest:
                break
            amount = FloatPrompt.ask("  Amount TAO")
            if amount > 0:
                transfers.append((dest, amount, dest[:16] + "..."))
    else:
        console.print("  Enter destination wallet names or SS58 addresses (comma-separated):")
        console.print("  [dim]You can also use 'group:name' or wallet names like reg_1,reg_2[/dim]")
        dest_input = Prompt.ask("  Destinations")
        amount = FloatPrompt.ask("  Amount TAO per wallet")
        if amount <= 0:
            print_error("Amount must be > 0")
            return

        # Resolve destinations: could be wallet names, group, or SS58 addresses
        all_wallets = list_wallets(base_path)

        # Check if it's a group reference
        if dest_input.strip().lower().startswith("group:"):
            group_name = dest_input.strip()[6:].strip()
            group_wallet_names = get_group(group_name)
            if group_wallet_names is None:
                print_error(f"Group '{group_name}' not found")
                return
            parts = group_wallet_names
        else:
            parts = [p.strip() for p in dest_input.split(",") if p.strip()]

        name_map = {ww["name"]: ww for ww in all_wallets}

        for part in parts:
            # Check if it's a wallet name
            if part in name_map:
                dest_addr = get_coldkey_ss58(part, base_path)
                if dest_addr:
                    transfers.append((dest_addr, amount, part))
                else:
                    print_warn(f"Could not resolve address for {part}, skipping")
            elif part.startswith("5") and len(part) >= 46:
                # Looks like SS58 address
                transfers.append((part, amount, part[:16] + "..."))
            else:
                print_warn(f"'{part}' not found, skipping")

    if not transfers:
        print_warn("No transfers entered")
        return

    total = sum(a for _, a, _ in transfers)
    console.print(f"\n  Sending to {len(transfers)} destinations:")
    for dest_ss58, amt, label in transfers:
        console.print(f"    {label:>16}: {amt:.4f} TAO")
    console.print(f"  [yellow]Total: {total:.4f} TAO[/yellow]")

    if total > bal["free_tao"]:
        print_error(f"Insufficient balance ({bal['free_tao']:.4f} TAO available)")
        return
    if not Confirm.ask("Proceed with batch transfer?"):
        return

    console.print("  [dim]Unlocking coldkey...[/dim]")
    _ = wallet.coldkey

    if mode == "2" and len(transfers) > 1:
        # Use utility.batch_all — single tx, single block
        from core.substrate_client import tao_to_rao
        calls = []
        for dest_ss58, amt, label in transfers:
            calls.append({
                "call_module": "Balances",
                "call_function": "transfer_keep_alive",
                "call_params": {
                    "dest": dest_ss58,
                    "value": tao_to_rao(amt),
                },
            })
        console.print(f"  [dim]Submitting batch ({len(calls)} transfers in 1 tx)...[/dim]")
        success, error = await client.submit_batch(calls, keypair=wallet.coldkey)
        if success:
            print_success(f"Batch sent: {len(transfers)} transfers, {total:.4f} TAO total")
        else:
            print_error(f"Batch failed: {error}")
            if Confirm.ask("Retry transfers one by one?"):
                for dest_ss58, amt, label in transfers:
                    console.print(f"  Sending {amt} TAO → {label}...")
                    success, error = await transfer_tao_keep_alive(client, wallet, dest_ss58, amt)
                    if success:
                        print_success(f"Sent {amt} TAO → {label}")
                    else:
                        print_error(f"Failed {label}: {error}")
    else:
        # Sequential mode
        ok_count = 0
        fail_count = 0
        for dest_ss58, amt, label in transfers:
            console.print(f"  Sending {amt} TAO → {label}...")
            success, error = await transfer_tao_keep_alive(client, wallet, dest_ss58, amt)
            if success:
                print_success(f"Sent {amt} TAO → {label}")
                ok_count += 1
            else:
                print_error(f"Failed {label}: {error}")
                fail_count += 1
        console.print(f"\n  Done: [green]{ok_count} ok[/green], [red]{fail_count} failed[/red]")


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

    # Unlock all coldkeys first
    console.print("  [dim]Unlocking all coldkeys...[/dim]")
    wallet_plans = []
    for w, addr, amount in send_list:
        wallet = load_wallet(w["name"], base_path=base_path)
        _ = wallet.coldkey  # unlock
        wallet_plans.append((w["name"], wallet, amount))

    # Send all transfers in parallel (different coldkeys = no nonce conflict)
    console.print(f"  [dim]Sending {len(wallet_plans)} transfers in parallel...[/dim]")

    async def collect_one(name, wallet, amount):
        try:
            success, error = await transfer_tao_keep_alive(client, wallet, dest, amount)
            return (name, amount, success, error)
        except Exception as e:
            return (name, amount, False, str(e))

    tasks = [collect_one(name, w, amt) for name, w, amt in wallet_plans]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Display results
    ok_count = 0
    fail_count = 0
    collected_total = 0.0
    failed_list = []
    for r in results:
        if isinstance(r, Exception):
            print_error(f"Task failed: {r}")
            fail_count += 1
            continue
        name, amount, success, error = r
        if success:
            print_success(f"Collected {amount:.4f} TAO from {name}")
            ok_count += 1
            collected_total += amount
        else:
            print_error(f"Failed {name}: {error}")
            fail_count += 1
            failed_list.append((name, amount, error))

    console.print(
        f"\n  Done: [green]{ok_count} ok[/green] ({collected_total:.4f} TAO), "
        f"[red]{fail_count} failed[/red]"
    )

    # Retry failed ones sequentially if any
    if failed_list and Confirm.ask(f"Retry {len(failed_list)} failed transfers?"):
        for name, amount, _ in failed_list:
            console.print(f"  Retrying {name}...")
            wallet = load_wallet(name, base_path=base_path)
            _ = wallet.coldkey
            success, error = await transfer_tao_keep_alive(client, wallet, dest, amount)
            if success:
                print_success(f"Collected {amount:.4f} TAO from {name}")
            else:
                print_error(f"Failed again {name}: {error}")


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
        total_wallets = len(unstake_plan)
        console.print(f"\n  Total: [yellow]{total_hotkeys} hotkeys[/yellow] across [yellow]{total_wallets} wallets[/yellow]")

        # Mode selection
        if total_wallets > 1:
            console.print("\n  [cyan]A.[/cyan] Sequential (one tx at a time, safe)")
            console.print("  [cyan]B.[/cyan] Parallel coldkeys (different wallets in same block, faster)")
            mode = Prompt.ask("Mode", choices=["A", "B", "a", "b"], default="B").upper()
        else:
            mode = "A"

        if not Confirm.ask("Unstake all?"):
            return

        if mode == "A":
            # Sequential: one by one
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
        else:
            # Parallel: different coldkeys run concurrently
            # Hotkeys within same coldkey stay sequential (same nonce source)
            console.print("\n  [dim]Unlocking all coldkeys...[/dim]")
            wallet_plans = []
            for w, addr, staked_hotkeys in unstake_plan:
                wallet = load_wallet(w["name"], base_path=base_path)
                _ = wallet.coldkey  # unlock
                wallet_plans.append((w["name"], wallet, list(staked_hotkeys)))

            console.print(f"  [dim]Starting parallel unstake ({total_wallets} wallets)...[/dim]")

            async def unstake_wallet(name, wallet, hotkeys):
                results = []
                for hk_ss58 in hotkeys:
                    try:
                        success, error = await unstake_all(client, wallet, hk_ss58)
                        results.append((name, hk_ss58, success, error))
                    except Exception as e:
                        results.append((name, hk_ss58, False, str(e)))
                return results

            tasks = [unstake_wallet(name, w, hks) for name, w, hks in wallet_plans]
            all_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Display results
            ok_count = 0
            fail_count = 0
            for result in all_results:
                if isinstance(result, Exception):
                    print_error(f"Wallet task failed: {result}")
                    fail_count += 1
                    continue
                for name, hk_ss58, success, error in result:
                    if success:
                        print_success(f"{name}: unstaked {hk_ss58[:16]}...")
                        ok_count += 1
                    else:
                        print_error(f"{name}: {hk_ss58[:16]} - {error}")
                        fail_count += 1

            console.print(f"\n  Done: [green]{ok_count} ok[/green], [red]{fail_count} failed[/red]")

    elif choice == "2":
        w = select_single_wallet(base_path)
        if not w:
            return
        hk_names = select_hotkey(w)
        if not hk_names:
            return
        netuid = IntPrompt.ask("Subnet ID (netuid)")
        hotkey_names = hk_names

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
        hk_names = select_hotkey(w)
        if not hk_names or len(hk_names) > 1:
            print_error("Select exactly one hotkey for partial unstake")
            return
        hk_name = hk_names[0]
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
# 8. Wallet Groups
# ========================================================================

async def handle_wallet_groups(config: dict):
    print_header("Wallet Groups")
    base_path = config["wallet"]["base_path"]

    console.print("  [cyan]1.[/cyan] Create / update group")
    console.print("  [cyan]2.[/cyan] View groups")
    console.print("  [cyan]3.[/cyan] Delete group")
    choice = Prompt.ask("Select", choices=["1", "2", "3"])

    if choice == "1":
        group_name = Prompt.ask("Group name (e.g. sn-11)")

        # Show existing wallets for reference
        wallets = list_wallets(base_path)
        if wallets:
            display_wallet_list(wallets)

        console.print(
            "  Enter coldkey names (comma-separated, or 'all', or select by #):"
        )
        user_input = Prompt.ask("Wallets")

        if user_input.strip().lower() == "all":
            wallet_names = [w["name"] for w in wallets]
        else:
            # Resolve input like _resolve_wallets but just get names
            resolved = _resolve_wallets(user_input, wallets)
            wallet_names = [w["name"] for w in resolved]

        if not wallet_names:
            print_error("No wallets specified")
            return

        existing = get_group(group_name)
        if existing:
            console.print(f"  [yellow]Group '{group_name}' exists ({len(existing)} wallets), will overwrite[/yellow]")
            if not Confirm.ask("Overwrite?"):
                return

        create_group(group_name, wallet_names)
        print_success(f"Group '{group_name}' saved with {len(wallet_names)} wallets:")
        for wn in wallet_names:
            console.print(f"    [cyan]{wn}[/cyan]")

    elif choice == "2":
        groups = load_groups()
        if not groups:
            print_info("No groups created yet")
            return

        for gname, gwallets in sorted(groups.items()):
            console.print(f"\n  [bold cyan]{gname}[/bold cyan] ({len(gwallets)} wallets):")
            for wn in gwallets:
                console.print(f"    {wn}")
        console.print(f"\n  [dim]Use 'group:<name>' when selecting wallets in any mode[/dim]")

    else:
        groups = load_groups()
        if not groups:
            print_info("No groups to delete")
            return

        console.print("  Existing groups:")
        for gname in sorted(groups.keys()):
            console.print(f"    [cyan]{gname}[/cyan] ({len(groups[gname])} wallets)")

        name = Prompt.ask("Group to delete")
        if delete_group(name):
            print_success(f"Deleted group '{name}'")
        else:
            print_error(f"Group '{name}' not found")


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
    "8": handle_wallet_groups,
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
                if choice in ("1", "8"):
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
