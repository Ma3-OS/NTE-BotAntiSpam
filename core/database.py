import json
import os

# Default static lists
BLACK_LISTED_DOMAINS = [
    "discord.gift/",
    "xoeawin.com",
    "discrod.gift/", 
    "discord-nitro.", 
    "dlscord.com",            
    "steamcommunity-",        
    "discordapp.com/invite/honey-girl",
    "discord.com/billing/promotions",
    "free-nitro.com",
    "roblox-robux.com",
    "opensea-airdrop.",
    "maxbeast",
    "degambat",
    "degamb",
    "velspin",
    "velspincc"
]

BLACK_LISTED_SPAM_PHRASES = [
    "honey-girl",
    "omg girl in cam join",
    "shes on cam look",
    "yoo this girl on cam naked",
    "watch me masturbate",
    "my leaked video",
    "musbeastnet",
    "XORA5600",
    "free nitro",
    "steam gift",
    "claim your airdrop",
    "crypto giveaway",
    "@everyone free nitro",
    "get your free robux",
    "csgo skins free",
    "2500usdt",
    "3200usdt",
    "cryptocurrencycasino",
    "cryptocasino",
    "promocodebeast",
]

# Navigate up one directory since we are in core/
DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "blacklist.json")

def load_blacklist():
    global BLACK_LISTED_DOMAINS, BLACK_LISTED_SPAM_PHRASES
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                BLACK_LISTED_DOMAINS = data.get("domains", BLACK_LISTED_DOMAINS)
                BLACK_LISTED_SPAM_PHRASES = data.get("phrases", BLACK_LISTED_SPAM_PHRASES)
        except Exception as e:
            print(f"Error loading blacklist from JSON: {e}")

def save_blacklist():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "domains": BLACK_LISTED_DOMAINS,
            "phrases": BLACK_LISTED_SPAM_PHRASES
        }, f, indent=4, ensure_ascii=False)

# Load on module import
load_blacklist()
