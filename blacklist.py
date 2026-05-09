# ไฟล์: blacklist.py
# ==========================================
# รายชื่อโดเมน/ลิงก์อันตราย (ลิงก์ฟิชชิ่ง, ลิงก์หลอกหลวง)
# ==========================================
BLACK_LISTED_DOMAINS = [
    "discord.gift/", 
    "discrod.gift/", 
    "discord-nitro.", 
    "dlscord.com",            
    "steamcommunity-",        
    "discordapp.com/invite/honey-girl",
    "discord.com/billing/promotions", # ลิงก์หลอกให้กรอกบัตรเครดิต
    "free-nitro.com",
    "roblox-robux.com",
    "opensea-airdrop."        # ลิงก์สแกม NFT/คริปโต
]

# ==========================================
# วลี/ประโยคสแปม 
# ==========================================
BLACK_LISTED_SPAM_PHRASES = [
    # 🔞 หมวดหมู่: บอท 18+ / สแกมเว็บแคม
    "honey-girl",
    "omg girl in cam join",
    "shes on cam look",
    "yoo this girl on cam naked",
    "watch me masturbate",
    "my leaked video",
    
    # 🎁 หมวดหมู่: หลอกแจกของ / ฟิชชิ่ง
    "free nitro",
    "steam gift",
    "claim your airdrop",
    "crypto giveaway",
    "@everyone free nitro",
    "get your free robux",
    "csgo skins free",
    
    # 🎰 หมวดหมู่: เว็บพนัน / สล็อต (ภาษาไทย)
    "ปั่นบา",
    "รับปั่นบาคาร่า",
    "เว็บตรง100%",           
    "สล็อตเว็บตรง",
    "แจกเครดิตฟรี",           
    "แตกหนัก แตกจริง",
    "สมัครรับโบนัส",
    "ฝากถอนไม่มีขั้นต่ำ"
]
# แก๊งชื่อโดเมน (แฮกเกอร์มักจะเปลี่ยนบ่อยๆ)
BLACK_LISTED_DOMAINS = [
    "maxbeast",
    "degambat",
    "degamb",
    "velspin",
    "velspincc",
]

# แก๊งคำโฆษณาตายตัว (ถึงเปลี่ยนเว็บ แต่มันก็มักจะใช้คำพวกนี้)
BLACK_LISTED_SPAM_PHRASES = [
    "2500usdt",
    "3200usdt",
    "cryptocurrencycasino",
    "cryptocasino",
    "promocodebeast",
    "withdrawalsuccess",
    "activatecodeforbonus",
    "rewardreceived",
    "successfullyreceived"
]
