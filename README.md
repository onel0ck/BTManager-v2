# BTManager-v2

Terminal-based manager for Bittensor wallets. Create wallets, check balances, register hotkeys, transfer TAO, and manage staking — all from one interactive menu.

## Quick Start

```bash
git clone https://github.com/onel0ck/BTManager-v2.git
cd BTManager-v2
bash setup.sh
source venv/bin/activate
python main.py
```

## Features

**Wallet Management**
- Create coldkey + batch hotkeys (e.g. 20 at once)
- Add more hotkeys to existing wallets
- Optional password encryption

**Balances & Stats**
- Free, Staked, and Total TAO per wallet
- USD values via Binance/CoinGecko pricing
- Per-subnet breakdown with emissions
- Registration summary with current burn cost per subnet and total registration value
- "Where the emission comes from" summary at the bottom: top subnets and top wallets by daily TAO, their share, and how many registered hotkeys are idle

**Registration**
- Burn-based registration to any subnet
- Auto-detects burn cost before confirming
- Batch register across multiple hotkeys

**Transfers**
- Send TAO between wallets
- Collect mode: gather TAO from many wallets into one
- Bound collect addresses: bind each wallet to its own destination once (Wallet Groups → Collect addresses, one line: `wallet:address,wallet:address`), then Collect TAO sends every wallet to its saved address
- Batch mode: send from one wallet to many destinations

**Staking**
- Unstake ALL: auto-finds hotkeys with stake across many wallets, one confirm
- Unstake from subnet(s): any number of wallets x any number of subnets (`78,14`, `1-5`, `all`), optional alpha to keep per wallet per subnet
- Unstake exact amount from one hotkey on one subnet

**Subnet Info**
- Browse all subnets with prices, emission, and registration cost

**Find Address**
- Paste any SS58 address and see whether it is yours, as a coldkey or a hotkey
- For a hotkey it shows the hotkey name and the coldkey it belongs to
- Batch mode: paste many addresses at once, or point it at a text file
- Local only, reads just the public address from the wallet files

## Configuration

Edit `config.yaml`:

```yaml
rpc_endpoint: "wss://entrypoint-finney.opentensor.ai:443"

wallet:
  base_path: "~/.bittensor/wallets"
```

## Wallet Selection

When prompted to select wallets, you can use:
- Wallet name: `wallet_1`
- Number from list: `1`
- Multiple: `1,3,5` or `wallet_1,wallet_2`
- All wallets: `all`

## License

MIT
