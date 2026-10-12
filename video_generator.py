import asyncio
import subprocess
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

W, H = 720, 1280
OUT = Path("output")
OUT.mkdir(exist_ok=True)

FONT_PATH = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"

font = ImageFont.truetype(FONT_PATH, 42)
title_font = ImageFont.truetype(FONT_BOLD, 58)

story_file = OUT / "story.txt"
if not story_file.exists():
    raise FileNotFoundError("ملف القصة مش موجود!")

story = story_file.read_text(encoding="utf-8")
lines = [
    line.strip()
    for line in story.splitlines()
    if line.strip() and not line.startswith("عنوان القصة:")
]

if not lines:
    raise ValueError("القصة مفيهاش مشاهد!")

# إنشاء مشاهد كرتونية بسيطة
backgrounds = [
    (255, 225, 170),
    (180, 225, 255),
    (210, 245, 190),
    (255, 200, 220),
    (220, 205, 255),
]

for i, text in enumerate(lines[:5]):
    img = Image.new("RGB", (W, H), backgrounds[i % len(backgrounds)])
    draw = ImageDraw.Draw(img)

    # إطار المشهد
    draw.rounded_rectangle(
        (35, 45, W - 35, H - 45),
        radius=35,
        fill=(255, 250, 235),
        outline=(70, 65, 90),
        width=5,
    )

    # شخصية فاكهة كرتونية بسيطة
    cx, cy = W // 2, 420
    draw.ellipse(
        (cx - 115, cy - 115, cx + 115, cy + 115),
        fill=(255, 100, 80),
        outline=(120, 50, 40),
        width=5,
    )
    draw.ellipse((cx - 48, cy - 25, cx - 22, cy + 5), fill="black")
    draw.ellipse((cx + 22, cy - 25, cx + 48, cy + 5), fill="black")
    draw.arc((cx - 45, cy - 5, cx + 45, cy + 65),
             start=10, end=170, fill="black", width=6)
    draw.ellipse((cx - 22, cy - 135, cx + 15, cy - 100),
                 fill=(60, 140, 65))

    # نص المشهد
    draw.text(
        (W // 2, 690),
        text,
        font=font,
        fill=(35, 35, 50),
        anchor="mm",
        align="center",
        direction="rtl",
        language="ar",
    )

    img.save(OUT / f"scene_{i:02d}.png")

# تعليق صوتي مصري
narration = " ".join(lines[:5])

async def make_voice():
    voice = edge_tts.Communicate(
        narration,
        voice="ar-EG-SalmaNeural",
        rate="+8%",
    )
    await voice.save(str(OUT / "narration.mp3"))

asyncio.run(make_voice())

# تجهيز الفيديو باستخدام FFmpeg
with open(OUT / "scenes.txt", "w", encoding="utf-8") as f:
    for i in range(min(5, len(lines))):
        f.write(f"file 'scene_{i:02d}.png'\n")
        f.write("duration 5\n")
    f.write(f"file 'scene_{min(4, len(lines)-1):02d}.png'\n")

subprocess.run([
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0",
    "-i", str(OUT / "scenes.txt"),
    "-i", str(OUT / "narration.mp3"),
    "-vf", "fps=30,format=yuv420p",
    "-c:v", "libx264",
    "-c:a", "aac",
    "-shortest",
    "-movflags", "+faststart",
    str(OUT / "short.mp4"),
], check=True)

print("Video created:", OUT / "short.mp4")
