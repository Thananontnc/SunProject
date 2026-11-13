# Train the fire model on your PC (RTX 4060) / เทรนโมเดลบน PC ที่บ้าน

Expected time: about **1.5–3 hours** for 50 epochs on an RTX 4060. This is an estimate.
เวลาโดยประมาณ: **1.5–3 ชั่วโมง** สำหรับ 50 epochs บน RTX 4060

## 1. Install Python / ติดตั้ง Python
- Install **Python 3.12** from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"** during setup.
- ติดตั้ง **Python 3.12** แล้วติ๊ก **"Add python.exe to PATH"** ตอนติดตั้ง
- Update the NVIDIA driver (GeForce Experience or nvidia.com). / อัปเดตไดรเวอร์การ์ดจอ NVIDIA

## 2. Set up / ตั้งค่า (Command Prompt / PowerShell)
Copy this `training` folder to the PC, then:
คัดลอกโฟลเดอร์ `training` ไปไว้ที่ PC แล้วรันคำสั่ง:
```bat
cd path\to\training
python -m venv venv
venv\Scripts\activate
```
Install PyTorch **with CUDA**. Get the exact command from https://pytorch.org/get-started/locally/ (choose Stable, Windows, Pip, Python, the newest CUDA). It looks like:
ติดตั้ง PyTorch **แบบ CUDA** โดยเอาคำสั่งจากเว็บ pytorch.org (เลือก Stable / Windows / Pip / Python / CUDA เวอร์ชันล่าสุด) หน้าตาประมาณนี้:
```bat
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
```
Then:
```bat
pip install ultralytics kagglehub
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```
It must print `True NVIDIA GeForce RTX 4060`. If it prints `False`, reinstall PyTorch using the CUDA command above.
ต้องขึ้น `True NVIDIA GeForce RTX 4060` ถ้าขึ้น `False` ให้ติดตั้ง PyTorch ใหม่ด้วยคำสั่ง CUDA ด้านบน

## 3. Train / เทรน
```bat
python train_fire.py
```
- The first run downloads the D-Fire dataset (a few GB). / ครั้งแรกจะดาวน์โหลด dataset D-Fire (หลาย GB)
- PC shut down or crashed? Continue with: `python train_fire.py --resume` / ถ้าคอมดับหรือค้าง เทรนต่อด้วยคำสั่งนี้
- Out of GPU memory? Use: `python train_fire.py --batch 16` / ถ้า GPU memory ไม่พอ ใช้คำสั่งนี้
- Windows error about workers or a "spawn" error? Add `--workers 0`. / ถ้าเจอ error เรื่อง workers หรือ "spawn" ให้เพิ่ม `--workers 0`
- Add your own Pi camera photos (Roboflow YOLO export, unzipped): `python train_fire.py --extra D:\my_fire_photos`
  เพิ่มภาพจากกล้อง Pi ของเราเอง (ไฟล์ export จาก Roboflow แบบ YOLO ที่แตกไฟล์แล้ว)

## 4. Result / ผลลัพธ์
- The accuracy is printed at the end. Fire **mAP50 > 0.6 = usable, > 0.75 = good**.
  ค่าความแม่นยำจะแสดงตอนจบ ถ้า fire **mAP50 > 0.6 = ใช้ได้, > 0.75 = ดี**
- `training\fire_ncnn_model.zip` → copy to the Pi and unzip into `server/models/`. Restart the server.
  คัดลอกไฟล์นี้ไปที่ Pi แล้วแตกไฟล์ไว้ใน `server/models/` จากนั้นรีสตาร์ท server
- Charts: `training\runs\fire\results.png`. / กราฟผลการเทรน

## Auto train (one command) / เทรนอัตโนมัติคำสั่งเดียว
```bat
git pull
python auto_train.py
```
About 3–5 hours on an RTX 4060. It downloads D-Fire, then generates two extra sets:
- **small flames** (lighter or candle size, labelled as fire)
- **printed/cartoon flames** on shirts, posters and screens (empty labels, so they are NOT fire)

Then it trains for 100 epochs and prints how often printed fire gives a false alarm and how many small flames it finds. Finally it exports `fire_ncnn_model.zip` at 416 px.
On the Pi: unzip it into `server/models/`, add `YOLO_IMGSZ=416` to `server/fire-monitor.env`, then run `sudo systemctl restart fire-monitor`.

- Check that it runs first (about 10 min): `python auto_train.py --quick`
- PC turned off? Continue with `python auto_train.py --resume`
- Optional, better: put your own Pi camera photos in `training/my_photos/not_fire/` (fire shirt etc., no labelling needed) and/or a Roboflow export of real flames in `training/my_photos/fire/`. They are added automatically.
