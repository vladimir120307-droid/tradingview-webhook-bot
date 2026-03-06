<p align="center">
  <img src="https://img.shields.io/badge/TradingView-Webhook%20Bot-131722?style=for-the-badge&logo=tradingview&logoColor=white" alt="TradingView Webhook Bot"/>
</p>

<h1 align="center">TradingView Webhook Bot</h1>

<p align="center">
  <strong>Automate your TradingView alerts — receive webhook signals and execute trades on Binance, Bybit, OKX</strong>
</p>

<p align="center">
  <a href="https://github.com/vladimir120307-droid/tradingview-webhook-bot/actions"><img src="https://img.shields.io/github/actions/workflow/status/vladimir120307-droid/tradingview-webhook-bot/ci.yml?style=flat-square&label=CI" alt="CI"></a>
  <a href="https://github.com/vladimir120307-droid/tradingview-webhook-bot/releases"><img src="https://img.shields.io/github/v/release/vladimir120307-droid/tradingview-webhook-bot?style=flat-square&color=blue" alt="Release"></a>
  <a href="https://github.com/vladimir120307-droid/tradingview-webhook-bot/blob/main/LICENSE"><img src="https://img.shields.io/github/license/vladimir120307-droid/tradingview-webhook-bot?style=flat-square" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://hub.docker.com"><img src="https://img.shields.io/badge/docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker"></a>
  <a href="https://github.com/vladimir120307-droid/tradingview-webhook-bot/stargazers"><img src="https://img.shields.io/github/stars/vladimir120307-droid/tradingview-webhook-bot?style=flat-square&color=yellow" alt="Stars"></a>
</p>

<p align="center">
  <a href="#features">Features</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#alert-format">Alert Format</a> &bull;
  <a href="#supported-actions">Actions</a> &bull;
  <a href="#risk-management">Risk Management</a> &bull;
  <a href="#multi-account">Multi-Account</a> &bull;
  <a href="#docker-deployment">Docker</a> &bull;
  <a href="#faq">FAQ</a>
</p>

---

## Why This Bot?

You have a profitable strategy on TradingView. You set alerts. But then you sit there, manually opening positions, setting stop-losses, calculating position sizes... and sometimes you miss the signal entirely because you were asleep.

**This bot solves that.** It receives your TradingView webhook alerts and executes trades automatically on your exchange account in milliseconds. No missed signals. No emotional trading. No manual errors.

---

## Features

| Feature | Description |
|---------|-------------|
| **Multi-Exchange** | Binance, Bybit, OKX — spot and futures (USDT-M, COIN-M) |
| **Webhook Server** | FastAPI-based, TradingView IP whitelisting, HMAC signature validation |
| **Smart Parsing** | Supports both JSON and plain-text TradingView alert messages |
| **Order Types** | Market, limit, stop-market, stop-limit, take-profit, trailing stop |
| **Risk Management** | Daily loss limits, max concurrent positions, Kelly criterion sizing |
| **Position Sizing** | Fixed amount, percentage of balance, risk-based (SL distance), Kelly |
| **SL/TP** | Automatic stop-loss and take-profit placement with every trade |
| **Multi-Account** | Route different alerts to different exchange accounts |
| **Notifications** | Telegram and Discord alerts for every trade action |
| **Trade Logging** | SQLite database with full trade history and performance metrics |
| **Docker Ready** | One-command deployment with Docker Compose |
| **Battle-Tested** | Input validation, error handling, automatic reconnection |

---

## Quick Start

### Prerequisites

- Python 3.10+
- TradingView account (Pro, Pro+, or Premium for webhook alerts)
- Exchange API keys (Binance / Bybit / OKX)
- A server with a public IP or domain (VPS, cloud instance, etc.)

### Installation

```bash
# Clone the repository
git clone https://github.com/vladimir120307-droid/tradingview-webhook-bot.git
cd tradingview-webhook-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
nano .env  # Edit with your API keys
```

### Configuration

1. **Edit `.env`** with your exchange API keys and Telegram bot token
2. **Edit `config/settings.yaml`** to configure risk management, position sizing, and general settings
3. **Edit `config/exchanges.yaml`** to set up your exchange accounts

### Run

```bash
# Start the webhook server
python -m src.server

# The server starts on http://0.0.0.0:8000 by default
# Your webhook URL: http://YOUR_SERVER_IP:8000/webhook
```

### Set Up TradingView Alert

1. Open your chart on TradingView
2. Create an alert on your indicator/strategy
3. In the "Notifications" tab, check "Webhook URL"
4. Enter your webhook URL: `http://YOUR_SERVER_IP:8000/webhook`
5. In the "Message" field, paste your alert JSON (see [Alert Format](#alert-format))
6. Save the alert

---

## Alert Format

### JSON Format (Recommended)

```json
{
  "secret": "your_webhook_secret",
  "exchange": "binance",
  "symbol": "BTCUSDT",
  "action": "open_long",
  "order_type": "market",
  "size_type": "percent",
  "size_value": 25,
  "leverage": 10,
  "stop_loss": 42000,
  "take_profit": 48000,
  "account": "main"
}
```

### Plain Text Format

The bot also parses plain-text messages from TradingView:

```
BINANCE:BTCUSDT OPEN_LONG MARKET 25% LEV:10 SL:42000 TP:48000
```

### Alert Fields Reference

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `secret` | Yes* | string | HMAC secret for webhook validation |
| `exchange` | Yes | string | `binance`, `bybit`, `okx` |
| `symbol` | Yes | string | Trading pair, e.g., `BTCUSDT` |
| `action` | Yes | string | See [Supported Actions](#supported-actions) |
| `order_type` | No | string | `market` (default), `limit`, `stop` |
| `price` | No | float | Required for limit orders |
| `size_type` | No | string | `fixed`, `percent`, `risk`, `kelly` |
| `size_value` | No | float | Amount, percentage, or risk factor |
| `leverage` | No | int | Futures leverage (1-125) |
| `stop_loss` | No | float | Stop-loss price |
| `take_profit` | No | float | Take-profit price |
| `trailing_stop` | No | float | Trailing stop callback rate (%) |
| `account` | No | string | Account label for multi-account |
| `comment` | No | string | Trade comment for logging |

*Required if `webhook_secret` is set in your config.

---

## Supported Actions

| Action | Description |
|--------|-------------|
| `open_long` | Open a long position (buy) |
| `open_short` | Open a short position (sell/short) |
| `close_long` | Close an existing long position |
| `close_short` | Close an existing short position |
| `close_all` | Close all positions on the symbol |
| `cancel_orders` | Cancel all open orders on the symbol |
| `set_sl` | Modify stop-loss on existing position |
| `set_tp` | Modify take-profit on existing position |
| `reverse` | Close current position and open opposite |
| `scale_in` | Add to an existing position |
| `scale_out` | Partially close a position (use `size_value` as %) |

### Strategy Integration Example

If you use a Pine Script strategy with `strategy.entry()` and `strategy.close()`, configure your alerts like this:

**Entry Long:**
```json
{"secret":"abc123","exchange":"binance","symbol":"BTCUSDT","action":"open_long","size_type":"risk","size_value":1.5,"leverage":5,"stop_loss":{{strategy.order.comment}}}
```

**Exit Long:**
```json
{"secret":"abc123","exchange":"binance","symbol":"BTCUSDT","action":"close_long"}
```

You can use TradingView placeholders like `{{ticker}}`, `{{close}}`, `{{strategy.order.comment}}` inside the alert message.

---

## Risk Management

The bot includes a comprehensive risk management system that protects your capital.

### Daily Loss Limit

```yaml
# config/settings.yaml
risk:
  daily_loss_limit_percent: 3.0  # Stop trading after 3% daily loss
  daily_loss_reset_hour: 0       # Reset at midnight UTC
```

When the daily loss limit is hit, the bot will:
- Reject all new `open_*` signals
- Still allow `close_*` signals to exit positions
- Send a Telegram/Discord notification
- Resume trading after the reset hour

### Maximum Concurrent Positions

```yaml
risk:
  max_positions: 5         # Max open positions across all symbols
  max_positions_per_symbol: 1  # Max positions per symbol
```

### Position Sizing Methods

#### Fixed Amount
```json
{"size_type": "fixed", "size_value": 1000}
```
Opens a position worth $1,000 USDT.

#### Percentage of Balance
```json
{"size_type": "percent", "size_value": 25}
```
Uses 25% of your available balance.

#### Risk-Based (Recommended)
```json
{"size_type": "risk", "size_value": 1.5, "stop_loss": 42000}
```
Risks 1.5% of your balance. Position size is calculated based on the distance to your stop-loss.

**Formula:** `position_size = (balance * risk_percent) / (entry_price - stop_loss)`

#### Kelly Criterion
```json
{"size_type": "kelly", "size_value": 0.5}
```
Uses Kelly criterion based on your historical win rate and reward/risk ratio. The `size_value` is the Kelly fraction (0.5 = half-Kelly, recommended for safety).

---

## Multi-Account

Route different TradingView alerts to different exchange accounts. Useful for managing multiple strategies or client accounts.

### Setup

```yaml
# config/exchanges.yaml
accounts:
  main:
    exchange: binance
    api_key: ${BINANCE_API_KEY}
    api_secret: ${BINANCE_API_SECRET}
    testnet: false

  scalping:
    exchange: bybit
    api_key: ${BYBIT_SCALP_API_KEY}
    api_secret: ${BYBIT_SCALP_API_SECRET}
    testnet: false

  swing:
    exchange: okx
    api_key: ${OKX_SWING_API_KEY}
    api_secret: ${OKX_SWING_API_SECRET}
    passphrase: ${OKX_SWING_PASSPHRASE}
    testnet: false
```

### Usage

Include the `account` field in your alert:

```json
{"exchange":"bybit","account":"scalping","symbol":"ETHUSDT","action":"open_long",...}
```

If no `account` is specified, the bot uses the first account configured for that exchange.

---

## Telegram Notifications

Get real-time notifications for every trade action.

### Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather)
2. Get your chat ID via [@userinfobot](https://t.me/userinfobot)
3. Add credentials to `.env`:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789
```

4. Run the setup script to verify:

```bash
python scripts/setup_telegram.py
```

### Notification Examples

```
TRADE OPENED
Exchange: Binance
Symbol: BTCUSDT
Side: LONG
Size: 0.5 BTC ($22,500)
Entry: $45,000.00
Stop Loss: $43,500.00
Take Profit: $48,000.00
Leverage: 10x
Risk: 1.5% ($337.50)
```

---

## Discord Notifications

### Setup

1. Create a webhook in your Discord server (Server Settings > Integrations > Webhooks)
2. Add the webhook URL to `.env`:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## Docker Deployment

### Quick Deploy

```bash
# Clone and configure
git clone https://github.com/vladimir120307-droid/tradingview-webhook-bot.git
cd tradingview-webhook-bot
cp .env.example .env
nano .env  # Add your API keys

# Build and run
docker-compose up -d

# View logs
docker-compose logs -f
```

### Docker Compose

The included `docker-compose.yml` provides:
- Automatic container restart on failure
- Volume mounts for config, database, and logs
- Health check endpoint at `/health`
- Environment variable injection from `.env`

### Reverse Proxy (Nginx)

For production, put the bot behind Nginx with SSL:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location /webhook {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Trade Logging

All trades are logged to a SQLite database (`data/trades.db`) with the following information:

- Timestamp, exchange, symbol, side, action
- Entry price, quantity, notional value
- Stop-loss, take-profit levels
- P&L (realized), fees
- Alert source, account label, comments

### Viewing Trade History

```python
# Quick query example
import sqlite3
conn = sqlite3.connect("data/trades.db")
cursor = conn.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT 20")
for row in cursor:
    print(row)
```

---

## Security

### TradingView IP Whitelist

The bot only accepts webhooks from TradingView's official IP addresses. This is enabled by default and updated automatically.

```yaml
# config/settings.yaml
webhook:
  ip_whitelist_enabled: true
```

### HMAC Signature Validation

Add a `secret` field to your TradingView alert. The bot validates it against your configured `WEBHOOK_SECRET`:

```env
WEBHOOK_SECRET=your_strong_random_secret_here
```

### API Key Security

- Store API keys in `.env` (never commit to git)
- Use IP-restricted API keys on your exchange
- Enable only the permissions you need (trade, no withdrawal)
- Use testnet keys for development

---

## Configuration Reference

### settings.yaml

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  workers: 1

webhook:
  ip_whitelist_enabled: true
  require_secret: true

risk:
  daily_loss_limit_percent: 3.0
  max_positions: 5
  max_positions_per_symbol: 1
  default_size_type: "percent"
  default_size_value: 10
  default_leverage: 1
  max_leverage: 50

notifications:
  telegram_enabled: true
  discord_enabled: false
  notify_on_open: true
  notify_on_close: true
  notify_on_error: true

logging:
  level: "INFO"
  file: "logs/bot.log"
  max_size_mb: 50
  backup_count: 5
```

---

## Testing

### Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_parser.py -v
```

### Test Webhook Locally

```bash
# Start the server
python -m src.server

# In another terminal, send a test webhook
python scripts/test_webhook.py
```

The test script sends a sample webhook to your local server and displays the response.

---

## Troubleshooting

### Common Issues

**"Webhook rejected: IP not whitelisted"**
- Your server is receiving requests from a non-TradingView IP
- If using a reverse proxy, make sure to forward `X-Real-IP` headers
- Set `ip_whitelist_enabled: false` for testing (not recommended in production)

**"Invalid secret"**
- Ensure the `secret` in your TradingView alert matches `WEBHOOK_SECRET` in `.env`
- Check for trailing spaces or newlines

**"Insufficient balance"**
- Check your available balance on the exchange
- Reduce `size_value` or adjust `size_type`

**"Max positions reached"**
- You've hit `max_positions` limit in `settings.yaml`
- Close existing positions or increase the limit

**Orders not executing on Binance**
- Ensure futures are enabled on your Binance account
- Check that API key has trading permissions
- Verify the symbol exists (e.g., `BTCUSDT` not `BTC/USDT`)

---

## Roadmap

- [ ] Web dashboard for monitoring trades and P&L
- [ ] More exchanges (Kraken, Gate.io, MEXC)
- [ ] DCA (Dollar Cost Averaging) mode
- [ ] Grid trading support
- [ ] Copy trading between accounts
- [ ] Webhook relay for multiple bots
- [ ] Backtesting integration

---

## FAQ

**Q: Do I need TradingView Premium?**
A: You need at least TradingView Pro for webhook alerts. The free plan does not support webhooks.

**Q: Is this bot free?**
A: Yes, completely free and open source under the MIT license.

**Q: Can I run multiple strategies?**
A: Yes. Use the `account` field to route different alerts to different accounts, or run multiple bot instances.

**Q: Does this work with spot trading?**
A: Yes. The bot supports both spot and futures trading on all exchanges.

**Q: How fast is the execution?**
A: Typically under 100ms from webhook receipt to order placement, depending on exchange API latency.

**Q: Is my API key safe?**
A: API keys are stored locally in your `.env` file and never transmitted anywhere except to the exchange API. Always use IP-restricted keys without withdrawal permissions.

---

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Disclaimer

This software is for educational and informational purposes only. Use it at your own risk. The authors are not responsible for any financial losses incurred through the use of this bot. Always test with small amounts or on testnet before using real funds. Trading cryptocurrency involves significant risk of loss.

---

<p align="center">
  Built with precision by <a href="https://github.com/vladimir120307-droid">Cyber_Lord</a>
</p>

<p align="center">
  If this bot saves you time and makes you money, consider giving it a star on GitHub.
</p>
