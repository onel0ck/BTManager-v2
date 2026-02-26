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

**Registration**
- Burn-based registration to any subnet
- Auto-detects burn cost before confirming
- Batch register across multiple hotkeys

**Transfers**
- Send TAO between wallets
- Collect mode: gather TAO from many wallets into one
- Batch mode: send from one wallet to many destinations

**Staking**
- Unstake ALL: auto-finds hotkeys with stake, one confirm
- Unstake from specific subnet
- Unstake custom amounts

**Subnet Info**
- Browse all subnets with prices, emission, and registration cost

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
