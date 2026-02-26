#!/usr/bin/env python3
"""
Bittensor Manager v2
Direct chain interaction via async-substrate-interface.
No btcli dependency.
"""

import asyncio
import sys
from rich.console import Console

from utils.config import load_config
from core.substrate_client import SubstrateClient
from ui.menus import main_menu_loop

console = Console()


async def main():
    config = load_config("config.yaml")

    rpc = config["rpc_endpoint"]
    fallbacks = config.get("fallback_endpoints", [])

    console.print(f"\n[bold cyan]Bittensor Manager v2[/bold cyan]")
    console.print(f"[dim]Connecting to {rpc}...[/dim]")

    client = SubstrateClient(url=rpc, fallbacks=fallbacks)

    try:
        await client.connect()
        block = await client.get_current_block()
        console.print(f"[green]✓ Connected[/green] | Block: [cyan]{block:,}[/cyan]")

        await main_menu_loop(client, config)

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
    except Exception as e:
        console.print(f"\n[bold red]Fatal error:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
