# BTManager-v2

Terminal manager for a **fleet** of Bittensor wallets. Create coldkeys and hotkeys in bulk, see what every
hotkey actually earns, burn register, move TAO and alpha around, stake and unstake across many wallets at
once, and research subnets before you spend anything.

Talks to the chain directly through `async-substrate-interface`. No `btcli` needed. Your coldkeys stay on
your machine and are only decrypted in memory when a transaction has to be signed.

```
╔══════════════════════════════════════╗
║    Bittensor Manager v2              ║
╚══════════════════════════════════════╝
  1. Create Wallet (Coldkey/Hotkey)
  2. Check Balances
  3. Wallet Stats
  4. Register (Burn)
  5. Transfer TAO
  6. Unstake
  7. Subnet Info
  8. Wallet Groups
  9. Add Stake
  10. Find Address (coldkey/hotkey lookup)
  0. Exit
```

## Quick start

```bash
git clone https://github.com/onel0ck/BTManager-v2.git
cd BTManager-v2
bash setup.sh
source venv/bin/activate
python main.py
```

Needs Python 3.10 or newer. Wallets are read from `~/.bittensor/wallets` by default, so an existing
`btcli` setup works as is.

## The menu at a glance

| # | Mode | What it is for |
|---|------|----------------|
| 1 | Create Wallet | One coldkey with N hotkeys, extra hotkeys for an existing coldkey, or many coldkeys at once |
| 2 | Check Balances | Fast table of free, staked and total TAO per wallet, with USD |
| 3 | Wallet Stats | Full picture: per subnet stake, UID, incentive, daily emission, registrations, where the farm comes from |
| 4 | Register (Burn) | Burn register hotkeys on a subnet, or swap a UID to another hotkey |
| 5 | Transfer TAO | Single and batch transfers, collect TAO from many wallets, collect and distribute alpha |
| 6 | Unstake | Unstake everything, unstake from chosen subnets across many wallets, or an exact amount |
| 7 | Subnet Info | Subnet overview, pruning prediction, validator weights analysis |
| 8 | Wallet Groups | Named wallet groups and per wallet collect addresses |
| 9 | Add Stake | Stake TAO into a subnet with slippage protection and a price preview |
| 10 | Find Address | Paste an SS58 address and learn whether it is yours and what it is called |

Every mode that spends TAO shows a full plan and asks for confirmation first.

## Modes in detail

### 1. Create Wallet

- **New coldkey with hotkeys.** Give a name and how many hotkeys to create, default 20. Hotkeys are
  named `1`, `2`, `3` and so on.
- **Add hotkeys to an existing coldkey.** Continues the numbering from the last hotkey.
- **Batch create.** A base name plus how many coldkeys and how many hotkeys each, for example
  `reg` creates `reg_1 ... reg_50`, each with its own hotkeys.

Coldkeys can be encrypted with a password, the prompt defaults to no. Mnemonics are not printed on
screen; the secret phrase is stored inside the key file under `~/.bittensor/wallets`, so back up that
directory, and keep in mind that an unencrypted coldkey file is enough to spend the funds.

### 2. Check Balances

Table of free, staked and total TAO per wallet plus USD and a grand total. Subnet prices are fetched
once and shared across all wallets. If a stake lookup fails for a wallet, the cell shows `?` instead of
a fake zero, and that wallet is left out of the totals.

### 3. Wallet Stats

Two modes.

**Full wallet stats.** Per wallet, a table of every subnet where the wallet has stake or a registration:
subnet, hotkey name, UID, alpha stake, TAO value, USD, daily emission in TAO and USD, incentive.
Then a grand total with:

- free, staked, total TAO and USD
- daily emission in TAO and USD
- **registrations per subnet with the current burn price**, what re-registering all those hotkeys would
  cost right now, and the total registration value
- **where the emission comes from**, the compact summary at the very bottom

```
  Where the emission comes from (total 18.8202 τ/day)
  By subnet (top 5 of 5)    τ/day   $/day  share  hk    τ/hk
  SN92 REAX               16.4351  $4,743  87.3%  29  0.5667
  SN14 Cacheon             1.6346    $472   8.7%   1  1.6346
  SN78 Umi                 0.7407    $214   3.9%  53  0.0140
  By wallet (top 8 of 55)    τ/day   $/day  share  hk  mostly
  speed_1                  16.4430  $4,745  87.4%  37  SN92 REAX
  main_666                  1.6365    $472   8.7%   3  SN14 Cacheon
  others (47)               0.4447    $128   2.4%
  45 wallet(s) earn nothing right now
  Idle: 283 registered hotkey(s) in 25 subnet(s) produce no emission
```

So a run over a hundred wallets does not have to be scrolled back: the bottom says which subnets and
which wallets carry the farm, the average per hotkey, and how many registered hotkeys sit idle.
Row count per table is `display.emission_top_n` in `config.yaml`.

**Check registrations on a subnet.** For one subnet, which of your hotkeys are registered, with UID,
stake, emission and daily reward, which wallets have nothing there, and which deregistered hotkeys still
hold alpha. Ends with a copy friendly `wallet/hotkeys` list.

### 4. Register (Burn)

- **Burn register.** Pick a wallet, pick hotkeys, pick the subnet. The current burn cost is shown with
  its USD value before anything is signed. An optional max burn price submits `register_limit`, so the
  extrinsic fails instead of overpaying if the cost moves. Hotkeys already registered are skipped.
  If registration is closed on that subnet you get a warning and a chance to stop.
  The coldkey password is asked **once** for the whole batch.
- **Swap hotkey.** Moves a UID from one of your hotkeys to another on the same subnet.

### 5. Transfer TAO

- **Single transfer.** One sender, one destination, one amount.
- **Batch transfer.** One sender to many destinations. Either type destination and amount pairs one by
  one, or give a list of wallet names, a group or SS58 addresses and one amount per wallet. More than
  one destination is submitted as a single atomic `utility.batch_all` transaction.
- **Collect TAO.** Many wallets into one destination, leaving a configurable amount for fees, default
  0.01 TAO. Two destination modes:
  - one address for every wallet, or
  - **bound addresses**, where every wallet sends to its own saved address, see Wallet Groups below.
    A wallet with no binding is asked once and remembered. If you use a single destination while some
    selected wallets have a different bound address, you are warned and can send those to their own.
- **Collect Alpha.** Consolidates alpha from many wallets and hotkeys onto one hotkey and coldkey using
  `move_stake` plus `transfer_stake`, per wallet in one batch.
- **Distribute Alpha.** The opposite direction: alpha from one source wallet out to many wallets.

### 6. Unstake

- **Unstake ALL.** Finds every hotkey with stake across the selected wallets and submits `unstake_all`
  per hotkey. Sequential or parallel across coldkeys, your choice.
- **Unstake from subnet(s).** Any number of wallets by any number of subnets. Subnets accept `78,14`,
  a range `1-5`, or `all`. Optionally keep some alpha per wallet on each subnet, `0` means take
  everything. A full exit uses `remove_stake_full_limit`; a partial one splits the amount across the
  hotkeys holding stake there in proportion to what each holds. Before confirming you see a per subnet
  table with alpha and the estimated TAO out, and after the run a per subnet result plus a retry option
  for anything that failed.
- **Unstake exact amount.** One hotkey, one subnet, an exact alpha amount.

### 7. Subnet Info

- **Overview.** Price in TAO and USD, both pool sides, tempo, neuron count, burn cost, whether
  registration is open. Spot price and, when they differ, the chain's EMA price.
- **Pruning prediction.** Who is likely to be deregistered next, with your own UIDs marked and immunity
  taken into account.
- **Validator weights analysis.** Who weights whom, for the current epoch and, through an archive node,
  for previous ones.

### 8. Wallet Groups

- **Groups.** Save a set of coldkeys under a name, then use `group:name` anywhere a wallet selection is
  asked for. Create, view and delete.
- **Collect addresses.** Bind each wallet to its own payout address once, then Collect TAO can send
  every wallet to its own destination. Paste all pairs in one line:

  ```
  wallet:address,wallet:address,...
  ```

  `;`, spaces, `=` and `->` work as separators too, and a path to a text file with pairs is accepted for
  large batches. Addresses are checksum validated before they are saved. The result table says what was
  added, updated or left unchanged, lists any rejected line with the reason, and reminds you which
  wallets of the same name family still have no binding.

### 9. Add Stake

Stake TAO into a subnet. Before signing you see the subnet name and symbol, the pool price, how much
alpha the amount buys and the resulting rate. Slippage protection is on by default: the stake is
submitted as `add_stake_limit` with a limit price derived from the pool spot price, so the chain rejects
the transaction instead of filling it at a worse price. Answer `no` to the slippage prompt for a plain
market order. Afterwards the actual TAO spent and the actual alpha received are read back from the chain.

### 10. Find Address

Paste a coldkey or hotkey SS58 address and get an answer about your own wallets:

```
  5CCyj8wKuRXPCJ9FgmJpV27jBWkNZpfbRMwC13BnRS6yz68i
  ✓ hotkey 3 of coldkey speed_1
      coldkey address: 5EcfbEyR24f65ineb6rAwED8mijTvUnEZeegKA4U4wE9UDtj
```

Paste a whole batch separated by commas, spaces or newlines, or give a path to a text file, and you get a
table with the type of each key, the coldkey name, the hotkey name, and a copyable list of the addresses
that are not yours. A wallet name works as input too. Everything is local: only the public address field
is read from the wallet files, and no network call is made.

## Input formats

**Wallet selection**, wherever wallets are asked for:

| Input | Meaning |
|-------|---------|
| `wallet_1` | by name |
| `3` | by number from the printed list |
| `1,3,5` or `w1,w2` | several |
| `all` | every wallet |
| `group:sn-11` | a saved group |

Modes that act on exactly one wallet say so and warn if your input matched several.

**Hotkey selection:** a name, a comma separated list, or `all`.

**Subnets** in unstake: `78`, `78,14`, a range `1-5`, or `all`.

**Addresses and bindings:** commas, semicolons, spaces or newlines, or a path to a text file.

## Files it creates

| File | What it holds |
|------|---------------|
| `wallet_groups.json` | your named wallet groups |
| `collect_addresses.json` | wallet to payout address bindings |
| `logs/btmanager.log` | log of operations and RPC errors |

Both JSON files live next to `main.py` and are git ignored, so they never end up in a commit. They are
plain user data, worth copying when you move the tool to another machine. Wallet keys themselves are
never written by this tool outside `~/.bittensor/wallets`.

## Configuration

`config.yaml`:

```yaml
# Chain endpoints: the first is primary, the rest are tried if it fails
rpc_endpoint: "wss://entrypoint-finney.opentensor.ai:443"
fallback_endpoints:
  - "wss://lite.finney.opentensor.ai:443"

wallet:
  base_path: "~/.bittensor/wallets"   # where coldkeys and hotkeys live

display:
  show_usd_prices: true   # fetch TAO/USD and show USD columns
  emission_top_n: 8       # rows per table in the emission summary
```

## How the numbers are computed

- **Alpha value in TAO** uses the pool spot price, `tao_in / alpha_in`, the price an unstake actually
  executes against. The chain also exposes `moving_price`, a slow EMA; on young or fast moving subnets it
  can lag the pool by an order of magnitude, so it is never used for valuation. Subnet Info shows both
  when they differ.
- **Daily emission** takes the neuron emission value, which is alpha per tempo, converts it to TAO at the
  spot price and scales it to 7200 blocks per day.
- **USD** comes from Binance with CoinGecko as fallback. With `show_usd_prices: false` nothing is fetched
  and no USD columns appear.
- **Root (SN0)** alpha counts as TAO one to one.

## Notes on safety

- Coldkeys are decrypted in memory only to sign, and the password is asked once per batch where possible.
- Nothing is submitted before a printed plan and an explicit confirmation.
- Add Stake defaults to a price limit, Register accepts a max burn price, Unstake accepts an amount to
  keep. Use them when the chain is busy.
- Multi destination transfers and alpha consolidation are atomic batches: either everything in that
  wallet's batch lands, or nothing does.
- Mass operations run one transaction at a time per coldkey and in parallel across coldkeys, so nonces
  never collide.

## Troubleshooting

- **Connection fails at startup.** Add or reorder `fallback_endpoints` in `config.yaml`.
- **`Could not load address for X`.** A directory inside the wallets path that is not a wallet, or a
  coldkey without `coldkeypub.txt`. Harmless, that entry is skipped.
- **Stake shows `?` in Check Balances.** The stake lookup for that wallet failed, the reason is printed
  above the table and in the log. Re-run or check the endpoint.
- **Weights history is empty.** Historical epochs need the archive node, reachable at
  `wss://archive.chain.opentensor.ai:443`.
- **More detail on any failure.** `logs/btmanager.log` keeps the extrinsic errors verbatim.

## License

MIT
