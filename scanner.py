import io
import re
import asyncio
import os
import psutil
import pytesseract
from rapidfuzz import fuzz
import imagehash
from PIL import Image
import cv2
import numpy as np

import config
from blacklist import BLACK_LISTED_DOMAINS, BLACK_LISTED_SPAM_PHRASES

pytesseract.pytesseract.tesseract_cmd = getattr(config, 'TESSERACT_CMD', 'tesseract')
spam_hash_cache = set()

# ==========================================
# 🌟 [ฟีเจอร์ใหม่] สมองอัจฉริยะ (Regex Patterns)
# เอาไว้ดักทางพวกที่ชอบเปลี่ยนตัวเลข หรือเปลี่ยนชื่อเว็บนิดๆ หน่อยๆ
# ==========================================
SPAM_REGEX_PATTERNS = [
    r"\+[0-9,]+\s?usdt",           # ดัก: +2500 usdt, +3000USDT, +1,000 usdt
    r"\$[0-9,]+\s?was success",    # ดัก: $2500 was successfully
    r"discord\.gift/[a-zA-Z0-9]+", # ดักลิงก์ดิสคอร์ดสแปมแบบเป๊ะๆ
    r"withdrawal of \$[0-9,]+"     # ดัก: Withdrawal of $3200
]

def get_ram_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024 

def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9ก-ฮ\.\$\+]', ' ', text) # อนุญาตให้มีจุด($)และบวก(+) ผ่านได้
    return re.sub(r'\s+', ' ', text).strip()

def process_image_advanced(image_bytes):
    """
    🌟 [อัปเกรด] ใช้ OpenCV จัดการภาพถ่ายจากหน้าจอคอม (ฆ่าเส้น Moire Effect)
    """
    # 1. แปลงไฟล์ไบต์เป็นอาเรย์ของ OpenCV (ความไวแสง)
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    
    # 2. ขยายภาพแบบคุณภาพสูง (Cubic Interpolation)
    height, width = img.shape
    if width < 1000:
        img = cv2.resize(img, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        
    # 3. ลบ Noise และเส้นหน้าจอคอมออกด้วย Gaussian Blur
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    
    # 4. แปลงภาพให้เป็นขาว-ดำสนิท (Adaptive Thresholding) 
    # ตัวหนังสือจะดำปี๋ พื้นหลังจะขาวจั๊วะ AI ชอบมาก!
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 15, 5
    )
    
    return thresh

async def analyze_image(image_bytes):
    start_ram = get_ram_usage()
    
    # เพื่อให้ยังใช้ ImageHash ได้ เราแปลง bytes เป็น PIL แค่ชั่วคราว
    pil_img_for_hash = Image.open(io.BytesIO(image_bytes)).convert('L')
    img_hash = str(imagehash.average_hash(pil_img_for_hash))
    
    if getattr(config, 'IMAGE_CACHE_ENABLED', False) and img_hash in spam_hash_cache:
        return True, "จำภาพนี้ได้ (ระบบ Cache)", img_hash

    # ส่งเข้าโรงชำแหละ OpenCV
    processed_cv_img = process_image_advanced(image_bytes)
    
    # Tesseract รองรับภาพจาก OpenCV (Numpy Array) โดยตรง!
    raw_text = await asyncio.to_thread(pytesseract.image_to_string, processed_cv_img, lang='eng')
    norm_text = normalize_text(raw_text)
    
    print(f"📝 [AI OpenCV] ข้อความที่ดึงได้: '{norm_text}'")
    
    is_spam = False
    reason = ""
    
    # ==========================================
    # 🛡️ ด่านที่ 1: ตรวจด้วย Regex อัจฉริยะ (แม่นยำสุด)
    # ==========================================
    for pattern in SPAM_REGEX_PATTERNS:
        if re.search(pattern, raw_text.lower()):
            is_spam = True
            reason = f"ตรวจพบแพทเทิร์นสแปม: '{pattern}'"
            break

    # ==========================================
    # 🛡️ ด่านที่ 2: ตรวจด้วย Blacklist ปกติและคำคล้าย (Fuzzy)
    # ==========================================
    if not is_spam:
        all_blacklists = BLACK_LISTED_DOMAINS + BLACK_LISTED_SPAM_PHRASES
        for phrase in all_blacklists:
            norm_phrase = normalize_text(phrase)
            
            if norm_phrase in norm_text:
                is_spam, reason = True, f"เจอคำตรงตัว: '{phrase}'"
                break
                
            if len(norm_phrase) > 5:
                similarity = fuzz.partial_ratio(norm_phrase, norm_text)
                if similarity >= getattr(config, 'FUZZY_THRESHOLD', 85):
                    is_spam, reason = True, f"เจอคำคล้าย: '{phrase}' ({similarity}%)"
                    break

    if is_spam and getattr(config, 'IMAGE_CACHE_ENABLED', False):
        spam_hash_cache.add(img_hash)

    end_ram = get_ram_usage()
    print(f"📊 [RAM OpenCV] หลังสแกนใช้ไป: {end_ram - start_ram:.2f} MB")
    
    return is_spam, reason, img_hash

def analyze_text(text):
    norm_text = text.lower()
    
    # เพิ่มการตรวจ Regex ในข้อความแชทด้วย
    for pattern in SPAM_REGEX_PATTERNS:
        if re.search(pattern, norm_text):
            return True, f"จับแพทเทิร์นสแปมได้: '{pattern}'"
            
    for domain in BLACK_LISTED_DOMAINS:
        if domain in norm_text:
            return True, f"เจอลิงก์อันตราย: '{domain}'"
    for phrase in BLACK_LISTED_SPAM_PHRASES:
        if phrase in norm_text:
            return True, f"เจอประโยคสแปม: '{phrase}'"
    return False, ""
