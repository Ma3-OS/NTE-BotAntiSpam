# ใช้ Python 3.10 เวอร์ชันที่ขนาดเล็กและเสถียร
FROM python:3.10-slim

# ติดตั้งเฉพาะ Tesseract OCR และแพ็กเกจภาษา (ไทย + อังกฤษ)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-tha \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ตั้งค่าโฟลเดอร์ทำงานในเซิร์ฟเวอร์
WORKDIR /app

# คัดลอกไฟล์ทั้งหมดจากเครื่องเรา (หรือ GitHub) ลงไปในเซิร์ฟเวอร์
COPY . .

# ติดตั้ง Library ต่างๆ ที่ระบุไว้ใน requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# คำสั่งสำหรับเริ่มทำงานบอท
CMD ["python", "-u", "bot.py"]
