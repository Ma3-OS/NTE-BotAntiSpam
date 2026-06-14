# NTE-BotAntiSpam

บอท Discord สำหรับป้องกันการสแปมข้อความและลิงก์อันตราย ออกแบบมาเพื่อดูแลความปลอดภัยให้กับเซิร์ฟเวอร์ของคุณ

## 👑 Developer / Creator
**Ma3-OS**  
*(ผู้คิดค้น ออกแบบ และพัฒนาโค้ดทั้งหมดแต่เพียงผู้เดียว)*

## 🌟 Features
- **Smart Text Scanner**: สแกนข้อความอัจฉริยะ ตัดตัวอักษรล่องหน และป้องกันการหลบเลี่ยงคำสแปม (เช่น การเว้นวรรค `f r e e`)
- **Cross-Channel Rate Limiting**: ตรวจจับการสแปมข้อความรัวๆ ข้ามห้องแชท (เช่น ส่งเกิน 5 ข้อความใน 3 วินาที) และทำการลงโทษอัตโนมัติ
- **Dynamic Blacklist**: จัดการเพิ่ม/ลด คำต้องห้ามหรือลิงก์อันตรายได้ทันทีผ่านคำสั่ง `/addword` และ `/removeword` โดยไม่ต้องรีสตาร์ทบอท (ข้อมูลถูกบันทึกถาวรใน `data/blacklist.json`)
- **Modular Architecture**: โครงสร้างแบบ Cogs แยกส่วนการทำงาน ทำให้บอททำงานได้อย่างเสถียรและดูแลรักษาง่าย
- **Mod Panel UI**: ระบบ UI ปุ่มกดสำหรับให้แอดมินจัดการผู้กระทำผิด (แบน/เตะ/ปลด Timeout) ได้อย่างรวดเร็วจากในแชท

## 📂 Project Structure
```text
NTE-BotAntiSpam/
├── cogs/                   # ระบบหลักแบบ Modular
│   ├── antispam.py         # จัดการเรทลิมิตและการสแกนข้อความ
│   └── admin_tools.py      # คำสั่งสำหรับ Mod/Admin
├── core/                   # ระบบแกนกลางของบอท
│   ├── bot_instance.py     # ตัวจัดการหลักและ Setup
│   └── database.py         # จัดการ Blacklist Data
├── utils/                  # ตัวช่วยประมวลผล
│   ├── scanner.py          # ระบบทำความสะอาดและตรวจสอบข้อความ
│   └── logger.py           # ระบบแสดงผล Log
├── data/                   # ฐานข้อมูล
│   └── blacklist.json      # ไฟล์เก็บข้อมูลคำต้องห้าม
└── main.py                 # ไฟล์สำหรับเริ่มต้นรันโปรแกรม
```

## 🚀 How to Run
1. ติดตั้ง Library ที่จำเป็น: `pip install -r requirements.txt`
2. ใส่ Token ลงในไฟล์ `.env`
3. รันบอท: `python main.py`

---
*Created by **Ma3-OS***