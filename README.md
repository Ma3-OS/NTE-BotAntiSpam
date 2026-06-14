# NTE-BotAntiSpam

<p align="center">
  A high-performance Discord Anti-Spam bot designed to protect communities from malicious links, raids, and spam messages. 
</p>

## 📌 Overview
NTE-BotAntiSpam is a robust and modular Discord bot built with `discord.py`. It provides automated moderation (Auto-Mod) features to actively scan chat messages, detect obfuscated spam patterns, enforce cross-channel rate limits, and issue intelligent warnings with visual evidence.

**Lead Developer & Architect:** Ma3-OS

## ✨ Key Features
- **Smart Text Normalization:** Advanced text pre-processing that strips invisible zero-width characters and normalizes spaced-out bypass attempts (e.g., `f r e e n i t r o`) before scanning.
- **Cross-Channel Anti-Raid System:** An in-memory sliding window rate limiter that detects and stops spammers broadcasting across multiple channels simultaneously (e.g., 5 messages in 3 seconds).
- **Dynamic Blacklist Engine:** Instantly add or remove restricted domains and spam phrases via `/addword` and `/removeword` slash commands without restarting the bot. Data is persistently saved in JSON format.
- **Rich Evidence Logging:** Automatically downloads the offender's attachments and reconstructs the deleted spam message into a clean, red-alert Embed sent to both the user's DM and the Admin Log channel.
- **Interactive Mod Panel:** Provides interactive UI buttons directly inside the Log channel, enabling moderators to quickly Ban, Kick, or un-Timeout the offender with a single click.
- **Optimized for Production:** Modular architecture using Discord Cogs, robust error handling, automated file rotation logging (`logs/bot.log`), and a lightweight `python:3.11-slim` Docker image for minimal resource consumption.

## 📂 Architecture & Project Structure
```text
NTE-BotAntiSpam/
├── cogs/                   # Pluggable modular features
│   ├── antispam.py         # Core Auto-Mod, Rate Limiting, and Punishment logic
│   └── admin_tools.py      # Slash Commands & Database management commands
├── core/                   # Core application layer
│   ├── bot_instance.py     # Main Discord Bot subclass and initialization
│   └── database.py         # Persistent Blacklist (JSON) read/write operations
├── utils/                  # Helper utilities
│   ├── scanner.py          # Fuzzy matching and Regex validation engine
│   └── logger.py           # Rotating File Handler and Console Logging setup
├── data/                   # Persistent data storage
│   └── blacklist.json      # Dynamic blocklist for domains and phrases
├── logs/                   # Generated automatically
│   └── bot.log             # Rotating log files
├── Dockerfile              # Containerization configuration
├── requirements.txt        # Production dependencies
└── main.py                 # Application Entry Point
```

## 🚀 Getting Started

### Prerequisites
- Python 3.11 or higher
- Discord Bot Token with `Message Content` and `Server Members` Intents enabled.

### Installation (Local)
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure the environment by creating a `.env` file:
   ```env
   DISCORD_TOKEN=your_bot_token_here
   OWNER_ID=your_discord_id
   LOG_CHANNEL_ID=your_log_channel_id
   ```
3. Run the application:
   ```bash
   python main.py
   ```

### Installation (Docker)
1. Build the Docker image:
   ```bash
   docker build -t nte-botantispam .
   ```
2. Run the container:
   ```bash
   docker run -d --env-file .env --name antispam-bot nte-botantispam
   ```

## 🛠️ Management Commands
- `/addword <word> <category>`: Add a phrase or domain to the blacklist.
- `/removeword <word> <category>`: Remove a phrase or domain.
- `!sync`: Manually sync Slash Commands across the server (Owner/Admin only).

---
*Developed and Maintained by **Ma3-OS***