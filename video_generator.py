import asyncio
import subprocess
import shutil
import math
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

W, H = 720, 1280
FPS = 12
OUT = Path("output")
FRAMES = OUT / "frames"

OUT.mkdir(exist_ok=True)

FONT_PATH = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"

font = ImageFont.truetype(FONT_PATH, 43)
title_font = ImageFont.truetype(FONT_BOLD, 57)
small_font = ImageFont.truetype(FONT_BOLD, 25)

story_file = OUT / "story.txt"
if not story_file.exists():
    raise FileNotFoundError("ملف القصة مش موجود!")

story = story_file.read_text(encoding="utf-8")

lines = []
for line in story.splitlines():
    line = line.strip()
    if not line:
        continue
    if line.startswith("عنوان القصة:"):
        continue
    if line.startswith("المشهد"):
        continue
    if line in ("النهاية:", "يتبع... لو عايز تعرف باقي الحكاية!"):
        continue
    lines.append(line)

lines = lines[:5]

if not lines:
    raise ValueError("مفيش مشاهد صالحة في القصة!")

# خلفيات مختلفة للمشاهد
backgrounds = [
    ((255, 220, 170), (255, 145, 125)),
    ((150, 210, 255), (105, 130, 220)),
    ((180, 240, 195), (60, 165, 150)),
    ((255, 195, 220), (210, 115, 180)),
    ((210, 190, 255), (115, 100, 205)),
]


def wrap_arabic(draw, text, selected_font, max_width):
    words = text.split()
    result = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textbbox(
            (0, 0), candidate, font=selected_font, direction="rtl"
        )[2]

        if width <= max_width or not current:
            current = candidate
        else:
            result.append(current)
            current = word

    if current:
        result.append(current)

    return "\n".join(result)


def draw_character(draw, kind, cx, cy, bob):
    cy += bob

    if kind == 0:
        # فاكهة كرتونية
        draw.ellipse(
            (cx - 105, cy - 110, cx + 105, cy + 110),
            fill=(245, 75, 75),
            outline=(125, 40, 50),
            width=6,
        )
        draw.ellipse(
            (cx - 25, cy - 145, cx + 8, cy - 95),
            fill=(65, 125, 55),
        )
        draw.ellipse(
            (cx - 48, cy - 30, cx - 20, cy + 2),
            fill="black",
        )
        draw.ellipse(
            (cx + 20, cy - 30, cx + 48, cy + 2),
            fill="black",
        )
        draw.arc(
            (cx - 42, cy - 5, cx + 42, cy + 65),
            start=5,
            end=175,
            fill="black",
            width=7,
        )
        draw.ellipse(
            (cx - 75, cy + 5, cx - 45, cy + 25),
            fill=(255, 155, 155),
        )
        draw.ellipse(
            (cx + 45, cy + 5, cx + 75, cy + 25),
            fill=(255, 155, 155),
        )

    elif kind == 1:
        # إنسان كرتوني
        draw.rounded_rectangle(
            (cx - 90, cy + 45, cx + 90, cy + 235),
            radius=45,
            fill=(70, 115, 230),
            outline=(35, 55, 125),
            width=5,
        )
        draw.ellipse(
            (cx - 90, cy - 100, cx + 90, cy + 100),
            fill=(245, 190, 145),
            outline=(120, 80, 65),
            width=5,
        )
        draw.pieslice(
            (cx - 95, cy - 120, cx + 95, cy + 15),
            start=180,
            end=360,
            fill=(65, 40, 30),
        )
        draw.ellipse((cx - 42, cy - 15, cx - 18, cy + 12), fill="black")
        draw.ellipse((cx + 18, cy - 15, cx + 42, cy + 12), fill="black")
        draw.arc(
            (cx - 35, cy + 5, cx + 35, cy + 55),
            start=5,
            end=175,
            fill=(100, 40, 35),
            width=5,
        )

    else:
        # حيوان كرتوني يشبه القطة
        draw.polygon(
            [(cx - 90, cy - 35), (cx - 75, cy - 130),
             (cx - 15, cy - 65)],
            fill=(245, 170, 95),
            outline=(110, 70, 40),
        )
        draw.polygon(
            [(cx + 90, cy - 35), (cx + 75, cy - 130),
             (cx + 15, cy - 65)],
            fill=(245, 170, 95),
            outline=(110, 70, 40),
        )
        draw.ellipse(
            (cx - 95, cy - 90, cx + 95, cy + 105),
            fill=(250, 195, 125),
            outline=(125, 85, 50),
            width=5,
        )
        draw.ellipse((cx - 45, cy - 15, cx - 20, cy + 12), fill="black")
        draw.ellipse((cx + 20, cy - 15, cx + 45, cy + 12), fill="black")
        draw.polygon(
            [(cx - 12, cy + 20), (cx + 12, cy + 20),
             (cx, cy + 35)],
            fill=(210, 80, 100),
        )
        draw.arc(
            (cx - 35, cy + 25, cx, cy + 60),
            start=0,
            end=120,
            fill="black",
            width=4,
        )
        draw.arc(
            (cx, cy + 25, cx + 35, cy + 60),
            start=60,
            end=180,
            fill="black",
            width=4,
        )
        for offset in (-1, 1):
            draw.line(
                (cx + offset * 35, cy + 30,
                 cx + offset * 100, cy + 15),
                fill=(90, 65, 50),
                width=3,
            )


async def make_voice(text):
    voice = edge_tts.Communicate(
        text,
        voice="ar-EG-SalmaNeural",
        rate="+5%",
    )
    await voice.save(str(OUT / "narration.mp3"))


narration = " ".join(lines)
asyncio.run(make_voice(narration))

# معرفة مدة التعليق الصوتي
probe = subprocess.run(
    [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(OUT / "narration.mp3"),
    ],
    capture_output=True,
    text=True,
    check=True,
)

audio_duration = float(probe.stdout.strip())
scene_duration = max(3.5, audio_duration / len(lines))
frames_per_scene = math.ceil(scene_duration * FPS)

if FRAMES.exists():
    shutil.rmtree(FRAMES)

FRAMES.mkdir(parents=True)

frame_number = 0

for scene_index, text in enumerate(lines):
    top_color, bottom_color = backgrounds[
        scene_index % len(backgrounds)
    ]

    # خلفية متدرجة
    base = Image.new("RGB", (W, H))
    pixels = base.load()

    for y in range(H):
        t = y / H
        color = tuple(
            int(top_color[c] * (1 - t) + bottom_color[c] * t)
            for c in range(3)
        )
        for x in range(W):
            pixels[x, y] = color

    draw = ImageDraw.Draw(base)

    # دوائر زخرفية
    draw.ellipse((35, 160, 115, 240), fill=(255, 255, 255))
    draw.ellipse((585, 230, 655, 300), fill=(255, 255, 255))
    draw.ellipse((65, 570, 125, 630), fill=(255, 255, 255))
    draw.ellipse((585, 610, 645, 670), fill=(255, 255, 255))

    # لوحة النص
    draw.rounded_rectangle(
        (35, 820, W - 35, 1120),
        radius=35,
        fill=(255, 250, 240),
        outline=(55, 45, 80),
        width=4,
    )

    wrapped = wrap_arabic(draw, text, font, W - 110)

    draw.multiline_text(
        (W // 2, 970),
        wrapped,
        font=font,
        fill=(35, 35, 55),
        anchor="mm",
        align="center",
        spacing=16,
        direction="rtl",
        language="ar",
    )

    draw.text(
        (W // 2, 120),
        "حكايات كرتونية",
        font=small_font,
        fill=(255, 255, 255),
        anchor="mm",
    )

    # نوع الشخصية يتغير بين الفاكهة والإنسان والحيوان
    kind = scene_index % 3

    for local_frame in range(frames_per_scene):
        progress = local_frame / max(1, frames_per_scene - 1)

        # حركة صعود وهبوط خفيفة
        bob = int(10 * math.sin(progress * math.pi * 4))

        frame = base.copy()
        frame_draw = ImageDraw.Draw(frame)

        draw_character(
            frame_draw,
            kind,
            W // 2,
            420,
            bob,
        )

        # حركة كاميرا تقريب تدريجي
        zoom = 1.0 + 0.055 * progress
        new_w = int(W * zoom)
        new_h = int(H * zoom)

        frame = frame.resize(
            (new_w, new_h),
            Image.Resampling.LANCZOS,
        )

        left = (new_w - W) // 2
        top = (new_h - H) // 2

        frame = frame.crop(
            (left, top, left + W, top + H)
        )

        frame.save(FRAMES / f"{frame_number:05d}.jpg", quality=90)
        frame_number += 1

# تجميع الإطارات في فيديو
subprocess.run(
    [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(FRAMES / "%05d.jpg"),
        "-i", str(OUT / "narration.mp3"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-af", "apad",
        "-t", str(frame_number / FPS),
        "-movflags", "+faststart",
        str(OUT / "short.mp4"),
    ],
    check=True,
)

print("Video created:", OUT / "short.mp4")
