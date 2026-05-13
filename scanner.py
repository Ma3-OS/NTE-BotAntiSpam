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
import time

import config
from blacklist import BLACK_LISTED_DOMAINS, BLACK_LISTED_SPAM_PHRASES

pytesseract.pytesseract.tesseract_cmd = getattr(config, 'TESSERACT_CMD', 'tesseract')

# 🌟 เปลี่ยนจาก set() เป็น dict เพื่อเก็บเวลาที่จำภาพไว้
spam_hash_cache = {} 

SPAM_REGEX_PATTERNS = [
    r"\+[0-9,]+\s?usdt",           
    r"\$[0-9,]+\s?was success",    
    r"discord\.gift/[a-zA-Z0-9]+", 
    r"withdrawal of \$[0-9,]+"     
]

def get_ram_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024 

def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9ก-ฮ\.\$\+]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def process_image_advanced(image_bytes):
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    height, width = img.shape
    if width < 1000:
        img = cv2.resize(img, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
    blur = cv2.GaussianBlur(img, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 5)
    return thresh

def clean_expired_cache():
    """🌟 ระบบล้างความจำภาพที่หมดอายุ"""
    current_time = time.time()
    expiry_seconds = getattr(config, 'IMAGE_CACHE_EXPIRY_MINUTES', 60) * 60
    expired_keys = [k for k, v in spam_hash_cache.items() if current_time - v > expiry_seconds]
    for k in expired_keys:
        del spam_hash_cache[k]

async def analyze_image(image_bytes):
    start_ram = get_ram_usage()
    clean_expired_cache() # สั่งล้างความจำเก่าทุกครั้งที่สแกนรูปใหม่
    
    pil_img_for_hash = Image.open(io.BytesIO(image_bytes)).convert('L')
    img_hash = str(imagehash.average_hash(pil_img_for_hash))
    
    if getattr(config, 'IMAGE_CACHE_ENABLED', False) and img_hash in spam_hash_cache:
        # อัปเดตเวลาให้ใหม่ล่าสุดถ้ารูปเดิมซ้ำมาอีก
        spam_hash_cache[img_hash] = time.time() 
        return True, "จำภาพนี้ได้ (ระบบ Cache)", img_hash

    # เลือกสมองตาม Config
    if getattr(config, 'STRICT_REGEX_MODE', True):
        processed_img = process_image_advanced(image_bytes)
    else:
        # ถ้าปิดโหมดโปร จะใช้แค่ Threshold ธรรมดา
        nparr = np.frombuffer(image_bytes, np.uint8)
        processed_img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

    raw_text = await asyncio.to_thread(pytesseract.image_to_string, processed_img, lang='eng')
    norm_text = normalize_text(raw_text)
    
    is_spam = False
    reason = ""
    
    for pattern in SPAM_REGEX_PATTERNS:
        if re.search(pattern, raw_text.lower()):
            is_spam, reason = True, f"ตรวจพบแพทเทิร์นสแปม: '{pattern}'"
            break

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
                    is_spam, reason = True, f"เจอคำคล้าย: '{phrase}' ({int(similarity)}%)"
                    break

    if is_spam and getattr(config, 'IMAGE_CACHE_ENABLED', False):
        spam_hash_cache[img_hash] = time.time() # บันทึกเวลาที่เจอ

    end_ram = get_ram_usage()
    return is_spam, reason, img_hash

def analyze_text(text):
    norm_text = text.lower()
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
