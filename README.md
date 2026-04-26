# 🚀 ssh-bot-Robexia

A powerful Telegram SSH Bot that lets users connect to their servers directly through Telegram.
Perfect for situations where internet access is limited, but Telegram is still available.

## ✨ Features

* ⚡ Fast SSH connection using IP, username, and password
* 🔍 Automatic detection of default SSH port `22`
* 🛠 Custom port support
* 💻 Live terminal inside Telegram
* 📤 Send commands and receive instant output
* 📁 Save and manage server list (**My Hosts**)
* 🔄 Quick reconnect to saved servers
* ⏸ Temporary exit from terminal using `wait`
* ❌ Fully close terminal using `close`
* 💤 Auto session close after inactivity
* 📂 Can be used as SFTP for file management
* 🎛 Clean and simple control panel

---

## 📦 Requirements

* Ubuntu 22.04
* Python 3
* Stable internet connection
* Telegram Bot Token

---

## ⚙️ Quick Install

Run this command on your server:

```bash
bash <(curl -sSL https://raw.githubusercontent.com/Hajiyor/ssh-bot-Robexia/main/install.sh)
```

The installer will automatically:

* Install all dependencies
* Ask for your bot token
* Ask for admin numeric ID
* Configure the bot
* Start the bot automatically

---

## 📸 How It Works

1. Create your bot using Telegram BotFather
2. Copy your bot token
3. Run the install command
4. Enter token + admin ID
5. Done ✅

---

## 🔐 Security Notes

* Keep your bot token private
* Use strong server passwords
* Limit access only to trusted admins
* Recommended to use firewall rules

---

## 🛠 Commands

| Command  | Description                      |
| -------- | -------------------------------- |
| `wait`   | Temporary leave terminal session |
| `close`  | Fully close terminal             |
| `/start` | Open bot panel                   |

---

## 💖 Support / Donate

If this project helped you, you can support development with a donation.

### 💰 Wallets

* **BTC:** `YOUR_BTC_WALLET`
* **ETH:** `YOUR_ETH_WALLET`
* **USDT (TRC20):** `YOUR_USDT_WALLET`
* **LTC:** `YOUR_LTC_WALLET`

> Replace wallet addresses with your real wallets.

---

## 📢 Official Telegram Channel

For updates, news, and future releases:
