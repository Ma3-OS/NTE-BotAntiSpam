import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name="MaO-Bot"):
    # สร้างโฟลเดอร์ logs ถ้ายังไม่มี
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    
    # ถ้ายังไม่มี handler ให้เพิ่มเข้าไป (ป้องกันการแสดงผลซ้ำซ้อน)
    if not logger.handlers:
        # แสดงผลใน Console (หน้าจอ)
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
        
        # เก็บ Log ลงไฟล์ หมุนเวียนไฟล์ละ 5MB สูงสุด 3 ไฟล์
        fh = RotatingFileHandler(os.path.join(log_dir, "bot.log"), maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
    return logger
