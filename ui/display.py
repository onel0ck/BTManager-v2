"""
Display helpers using Rich for formatted output.
"""

from rich.console import Console
from rich.table import Table

console = Console()

BLOCKS_PER_DAY = 7200


def print_header(text: str):
    console.print(f"\n[bold cyan]{'═' * 60}[/bold cyan]")
    console.print(f"[bold white]  {text}[/bold white]")
    console.print(f"[bold cyan]{'═' * 60}[/bold cyan]")


def print_success(text: str):
    console.print(f"  [bold green]✓[/bold green] {text}")


def print_error(text: str):
    console.print(f"  [bold red]✗[/bold red] {text}")


def print_warn(text: str):
    console.print(f"  [bold yellow]⚠[/bold yellow] {text}")


def print_info(text: str):
    console.print(f"  [dim]{text}[/dim]")


def display_balance_table(balances: list[dict], tao_price: float = None):
    """Display balance table with full addresses, staked, and totals."""
    table = Table(title="TAO Balances", show_lines=True)
    table.add_column("Wallet", style="cyan")
    table.add_column("Address", style="dim", no_wrap=True)
    table.add_column("Free (τ)", justify="right", style="green")
    table.add_column("Staked (τ)", justify="right", style="yellow")
    table.add_column("Total (τ)", justify="right", style="bold green")
    if tao_price:
        table.add_column("USD", justify="right", style="yellow")

    total_free = 0.0
    total_staked = 0.0
    for b in balances:
        free = b["free_tao"]
        staked = b.get("staked_tao", 0.0)
        total = free + staked
        total_free += free
        total_staked += staked
        row = [b.get("name", ""), b["address"], f"{free:.6f}", f"{staked:.6f}", f"{total:.6f}"]
        if tao_price:
            row.append(f"${total * tao_price:,.2f}")
        table.add_row(*row)

    grand = total_free + total_staked
    total_row = ["[bold]TOTAL[/bold]", "", f"[bold]{total_free:.6f}[/bold]",
                 f"[bold]{total_staked:.6f}[/bold]", f"[bold]{grand:.6f}[/bold]"]
    if tao_price:
        total_row.append(f"[bold]${grand * tao_price:,.2f}[/bold]")
    table.add_row(*total_row)

    console.print(table)
    if tao_price:
        console.print(f"  TAO price: [yellow]${tao_price:.2f}[/yellow]")


def display_wallet_stats(stats: dict, wallet_name: str = ""):
    """Display comprehensive wallet stats with USD."""
    addr = stats["address"]
    tao_price = stats.get("tao_price_usd")
    name_str = f" ({wallet_name})" if wallet_name else ""

    console.print(f"\n[bold]Wallet:[/bold] [cyan]{addr}[/cyan]{name_str}")
    console.print(f"[bold]Free Balance:[/bold] [green]{stats['free_balance_tao']:.4f}[/green] TAO")
    console.print(f"[bold]Total Staked:[/bold] [yellow]{stats['total_staked_tao']:.4f}[/yellow] TAO (est.)")
    console.print(f"[bold]Total Value:[/bold] [bold green]{stats['total_value_tao']:.4f}[/bold green] TAO")

    if stats.get("total_value_usd") is not None:
        console.print(
            f"[bold]USD Value:[/bold] [bold green]${stats['total_value_usd']:,.2f}[/bold green] "
            f"(TAO = ${tao_price:.2f})"
        )

    # Per-wallet daily emission summary
    em_per_blk = stats.get("total_emission_tao_per_block", 0.0)
    if em_per_blk > 0 and tao_price:
        daily_tao = em_per_blk * BLOCKS_PER_DAY
        daily_usd = daily_tao * tao_price
        console.print(
            f"[bold]Daily Emission:[/bold] [magenta]{daily_tao:.4f} τ/day[/magenta]"
            f" [bold green](${daily_usd:,.2f}/day)[/bold green]"
        )

    if stats["subnets"]:
        table = Table(title="Registered Subnets", show_lines=True)
        table.add_column("SN", style="cyan", justify="right")
        table.add_column("Name", style="white")
        table.add_column("Hotkey", style="dim", no_wrap=True)
        table.add_column("UID", style="white", justify="right")
        table.add_column("α Stake", justify="right", style="yellow")
        table.add_column("τ Value", justify="right", style="green")
        if tao_price:
            table.add_column("USD", justify="right", style="yellow")
        table.add_column("τ/day", justify="right", style="magenta")
        if tao_price:
            table.add_column("$/day", justify="right", style="bold green")
        table.add_column("Inc", justify="right", style="blue")
        table.add_column("Reg", justify="center")

        for s in stats["subnets"]:
            hk = str(s["hotkey"])
            reg = "✓" if s["is_registered"] else "✗"
            uid_str = str(s["uid"]) if s.get("uid") is not None else "-"
            inc = s.get("incentive", 0)
            inc_str = f"{inc/65535*100:.1f}%" if inc else "0"
            em_per_block = s.get("emission", 0)
            daily_tao = em_per_block * BLOCKS_PER_DAY
            row = [
                str(s["netuid"]),
                s["subnet_name"],
                hk,
                uid_str,
                f"{s['alpha_stake']:.4f}",
                f"{s['tao_value']:.4f}",
            ]
            if tao_price:
                row.append(f"${s['tao_value'] * tao_price:,.2f}")
            row.append(f"{daily_tao:.6f}")
            if tao_price:
                row.append(f"${daily_tao * tao_price:,.2f}")
            row.extend([inc_str, reg])
            table.add_row(*row)

        console.print(table)
    else:
        console.print("  [dim]No registrations found[/dim]")


def display_multi_wallet_stats(all_stats: list[tuple[str, dict]]):
    """Display combined stats for multiple wallets with grand totals."""
    grand_free = 0.0
    grand_staked = 0.0
    grand_total = 0.0
    grand_emission_per_block = 0.0
    tao_price = None

    for name, stats in all_stats:
        display_wallet_stats(stats, wallet_name=name)
        grand_free += stats["free_balance_tao"]
        grand_staked += stats["total_staked_tao"]
        grand_total += stats["total_value_tao"]
        grand_emission_per_block += stats.get("total_emission_tao_per_block", 0.0)
        if stats.get("tao_price_usd"):
            tao_price = stats["tao_price_usd"]
        console.print()

    if len(all_stats) > 1:
        console.print(f"[bold cyan]{'─' * 50}[/bold cyan]")
        console.print(f"[bold]GRAND TOTAL ({len(all_stats)} wallets):[/bold]")
        console.print(f"  Free: [green]{grand_free:.4f}[/green] TAO")
        console.print(f"  Staked: [yellow]{grand_staked:.4f}[/yellow] TAO (est.)")
        console.print(f"  Total: [bold green]{grand_total:.4f}[/bold green] TAO")
        if tao_price:
            console.print(f"  USD: [bold green]${grand_total * tao_price:,.2f}[/bold green] (TAO = ${tao_price:.2f})")
        if grand_emission_per_block > 0:
            daily_tao = grand_emission_per_block * BLOCKS_PER_DAY
            console.print(f"  Daily Emission: [bold magenta]{daily_tao:.4f} τ/day[/bold magenta]", end="")
            if tao_price:
                daily_usd = daily_tao * tao_price
                console.print(f" [bold green](${daily_usd:,.2f}/day)[/bold green]")
            else:
                console.print()

        # Subnet registration summary
        subnet_reg_count = {}  # {(netuid, name): count}
        for _, stats in all_stats:
            for s in stats.get("subnets", []):
                if s.get("is_registered"):
                    key = (s["netuid"], s["subnet_name"])
                    subnet_reg_count[key] = subnet_reg_count.get(key, 0) + 1
        if subnet_reg_count:
            total_reg = sum(subnet_reg_count.values())
            console.print(f"  [bold]Registrations ({total_reg} total):[/bold]")
            for (netuid, name), count in sorted(subnet_reg_count.items()):
                console.print(f"    SN{netuid} {name}: [cyan]{count}[/cyan] hotkeys")


def display_subnet_overview(info: dict, tao_price: float = None):
    """Display subnet overview."""
    table = Table(show_lines=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Subnet", f"SN{info['netuid']}")
    table.add_row("Name", info.get("name", "?"))
    table.add_row("Symbol", info.get("symbol", "?"))
    table.add_row("Tempo", str(info.get("tempo", "?")))

    mp = info.get("moving_price", 0)
    table.add_row("Price", f"{mp:.6f} TAO/alpha")
    if tao_price and mp:
        table.add_row("Price (USD)", f"${mp * tao_price:.4f} / alpha")

    tao_in = info.get("tao_in", 0)
    table.add_row("Pool (TAO side)", f"{tao_in:,.4f} TAO")
    if tao_price and tao_in:
        table.add_row("Pool (USD)", f"${tao_in * tao_price:,.2f}")
    table.add_row("Pool (Alpha side)", f"{info.get('alpha_out', 0):,.4f}")

    if "burn_cost_tao" in info:
        burn_str = f"{info['burn_cost_tao']:.9f} TAO"
        if tao_price:
            burn_str += f" (${info['burn_cost_tao'] * tao_price:.4f})"
        table.add_row("Burn Cost", burn_str)
    if "neurons" in info:
        table.add_row("Neurons", f"{info['neurons']} / {info.get('max_neurons', '?')}")
    if "registration_allowed" in info:
        reg = "[green]Open[/green]" if info["registration_allowed"] else "[red]Closed[/red]"
        table.add_row("Registration", reg)

    console.print(table)


def display_wallet_list(wallets: list[dict]):
    """Display wallet list for selection."""
    table = Table(title="Available Wallets", show_lines=True)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Name", style="bold white")
    table.add_column("Coldkey", justify="center")
    table.add_column("Hotkeys", justify="right")

    for i, w in enumerate(wallets, 1):
        ck = "✓" if w["coldkey_exists"] else "✗"
        hk_count = str(len(w["hotkeys"])) if w["hotkeys"] else "0"
        table.add_row(str(i), w["name"], ck, hk_count)

    console.print(table)
