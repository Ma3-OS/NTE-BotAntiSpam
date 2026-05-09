import io
import re
import asyncio
import os
import psutil  # 🌟 ใช้สำหรับเช็ค RAM
from PIL import Image
import pytesseract
from rapidfuzz import fuzz
import imagehash

import config
from blacklist import BLACK_LISTED_DOMAINS, BLACK_LISTED_SPAM_PHRASES

pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
spam_hash_cache = set()

def get_ram_usage():
    """ฟังก์ชันช่วยดูการใช้ RAM ปัจจุบัน"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # แปลงเป็น MB

def normalize_text(text):
    text = text.lower()
    return re.sub(r'[^a-z0-9ก-ฮ]', '', text)

def process_image(img):
    width, height = img.size
    box = (0, height // 2, width, height) 
    cropped_img = img.crop(box)
    cropped_img.thumbnail((600, 600))
    return cropped_img

async def analyze_image(image_bytes):
    start_ram = get_ram_usage()
    print(f"📊 [RAM] ก่อนสแกน: {start_ram:.2f} MB")
    
    img = Image.open(io.BytesIO(image_bytes)).convert('L')
    
    img_hash = str(imagehash.average_hash(img))
    if config.IMAGE_CACHE_ENABLED and img_hash in spam_hash_cache:
        print("💾 [Cache] เจอภาพเดิมในหน่วยความจำ! สั่งแบนทันที")
        return True, "เจอสแปมรูปเดิมที่เคยโดนแบน (ระบบจำภาพ)"

    print("🔍 [AI] กำลังเริ่มอ่านข้อความจากรูปภาพ...")
    opt_img = process_image(img)
    raw_text = await asyncio.to_thread(pytesseract.image_to_string, opt_img, lang='eng')
    norm_text = normalize_text(raw_text)
    
    # 🌟 จุดสำคัญ: พ่นข้อความที่ AI เห็นออกมาดู
    print(f"📝 [AI Result] ข้อความที่อ่านได้: '{raw_text.strip()}'")
    print(f"📝 [AI Normalized] ข้อความหลังปรับจูน: '{norm_text}'")
    
    is_spam = False
    reason = ""
    all_blacklists = BLACK_LISTED_DOMAINS + BLACK_LISTED_SPAM_PHRASES
    
    for phrase in all_blacklists:
        if phrase in norm_text:
            is_spam, reason = True, f"เจอคำต้องห้าม: '{phrase}'"
            break
        
        similarity = fuzz.partial_ratio(phrase, norm_text)
        if similarity >= config.FUZZY_THRESHOLD:
            is_spam, reason = True, f"เจอคำคล้าย: '{phrase}' ({similarity}%)"
            break

    if is_spam:
        if config.IMAGE_CACHE_ENABLED:
            spam_hash_cache.add(img_hash)
        print(f"🚨 [Match] ตรวจพบสแปม! สาเหตุ: {reason}")
    else:
        print("✅ [Match] ไม่พบคำที่ตรงกับ Blacklist")

    end_ram = get_ram_usage()
    print(f"📊 [RAM] หลังสแกน: {end_ram:.2f} MB (ใช้เพิ่มไป: {end_ram - start_ram:.2f} MB)")
    
    return is_spam, reason
