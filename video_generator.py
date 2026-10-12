import subprocess
import shutil
import math
import os
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# إعدادات الفيديو
# ==========================================
W, H = 1080, 1920
FPS = 30

OUT = Path("output")
FRAMES = OUT / "frames"
OUT.mkdir(exist_ok=True)

FONT_PATH = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"

font = ImageFont.truetype(FONT_PATH, 39)
title_font = ImageFont.truetype(FONT_BOLD, 49)
small_font = ImageFont.truetype(FONT_BOLD, 25)


# ==========================================
# قراءة القصة
# ==========================================
story_file = OUT / "story.txt"

if not story_file.exists():
    raise FileNotFoundError("ملف output/story.txt مش موجود!")

story = story_file.read_text(encoding="utf-8")

title = "حكاية كرتونية"
lines = []
reading_scenes = False

for raw_line in story.splitlines():
    line = raw_line.strip()

    if not line:
        continue

    if line.startswith("عنوان القصة:"):
        title = line.split(":", 1)[1].strip()
        continue

    if line.startswith("المشهد"):
        reading_scenes = True
        continue

    if line == "النهاية:":
        break

    if reading_scenes:
        lines.append(line)

if not lines:
    raise ValueError("ملقيناش مشاهد صالحة في ملف القصة!")

lines = lines[:5]


# ==========================================
# أدوات الرسم
# ==========================================
def wrap_arabic(draw, text, selected_font, max_width):
    words = text.split()
    result = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=selected_font,
            direction="rtl",
            language="ar",
        )

        width = bbox[2] - bbox[0]

        if width <= max_width or not current:
            current = candidate
        else:
            result.append(current)
            current = word

    if current:
        result.append(current)

    return "\n".join(result)


def lerp_color(a, b, t):
    return tuple(
        int(a[i] * (1 - t) + b[i] * t)
        for i in range(3)
    )


# ==========================================
# خلفيات سينمائية
# ==========================================
backgrounds = [
    ((20, 30, 68), (110, 65, 112)),
    ((18, 70, 105), (45, 125, 150)),
    ((55, 35, 85), (170, 80, 100)),
    ((25, 48, 75), (100, 105, 145)),
    ((45, 35, 70), (190, 105, 90)),
]


def make_background(scene_index):
    top_color, bottom_color = backgrounds[
        scene_index % len(backgrounds)
    ]

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        color = lerp_color(
            top_color,
            bottom_color,
            y / max(1, H - 1),
        )
        draw.line((0, y, W, y), fill=color)

    draw.ellipse(
        (120, 170, 600, 650),
        fill=lerp_color(
            top_color,
            (225, 185, 155),
            0.22,
        ),
    )

    # نجوم صغيرة
    for i in range(28):
        x = (i * 127 + scene_index * 53) % W
        y = (i * 173 + 85) % 700
        radius = 2 + i % 3

        draw.ellipse(
            (
                x - radius,
                y - radius,
                x + radius,
                y + radius,
            ),
            fill=(235, 230, 220),
        )

    # مبانٍ بعيدة
    for i in range(12):
        x = i * 95 - 15
        building_height = 100 + (i * 37 % 150)

        draw.rectangle(
            (
                x,
                790 - building_height,
                x + 75,
                790,
            ),
            fill=(30, 35, 65),
        )

        for wy in range(
            max(0, 700 - building_height),
            770,
            35,
        ):
            for wx in range(x + 12, x + 65, 28):
                draw.rectangle(
                    (wx, wy, wx + 8, wy + 12),
                    fill=(210, 180, 120),
                )

    # أرضية المشهد
    draw.ellipse(
        (-120, 720, W + 120, 1050),
        fill=(27, 32, 60),
    )

    draw.arc(
        (-100, 690, W + 100, 1010),
        start=180,
        end=360,
        fill=(100, 130, 175),
        width=4,
    )

    return img


# ==========================================
# الشخصيات الكرتونية
# ==========================================
def draw_character(
    draw,
    cx,
    cy,
    scale,
    shirt_color,
    hair_color,
    mood,
    movement,
):
    cx = int(cx)
    cy = int(cy + movement)

    outline = (35, 28, 45)

    arm_shift = int(
        12 * math.sin(movement / 4)
    )

    # الرجلان
    draw.line(
        (
            int(cx - 30 * scale),
            int(cy + 195 * scale),
            int(cx - 42 * scale),
            int(cy + 245 * scale),
        ),
        fill=outline,
        width=max(4, int(15 * scale)),
    )

    draw.line(
        (
            int(cx + 30 * scale),
            int(cy + 195 * scale),
            int(cx + 42 * scale),
            int(cy + 245 * scale),
        ),
        fill=outline,
        width=max(4, int(15 * scale)),
    )

    # الجسم
    draw.rounded_rectangle(
        (
            int(cx - 70 * scale),
            int(cy + 45 * scale),
            int(cx + 70 * scale),
            int(cy + 205 * scale),
        ),
        radius=int(28 * scale),
        fill=shirt_color,
        outline=outline,
        width=max(3, int(5 * scale)),
    )

    # الذراعان
    draw.line(
        (
            int(cx - 65 * scale),
            int(cy + 75 * scale),
            int(cx - 95 * scale),
            int(cy + (130 + arm_shift) * scale),
        ),
        fill=outline,
        width=max(5, int(18 * scale)),
    )

    draw.line(
        (
            int(cx + 65 * scale),
            int(cy + 75 * scale),
            int(cx + 95 * scale),
            int(cy + (130 - arm_shift) * scale),
        ),
        fill=outline,
        width=max(5, int(18 * scale)),
    )

    # الرقبة
    draw.rectangle(
        (
            int(cx - 18 * scale),
            int(cy + 20 * scale),
            int(cx + 18 * scale),
            int(cy + 65 * scale),
        ),
        fill=(225, 165, 125),
    )

    # الرأس
    radius = int(70 * scale)

    draw.ellipse(
        (
            cx - radius,
            cy - radius,
            cx + radius,
            cy + radius,
        ),
        fill=(245, 190, 150),
        outline=outline,
        width=max(3, int(5 * scale)),
    )

    # الشعر
    draw.pieslice(
        (
            cx - radius - 3,
            cy - radius - 10,
            cx + radius + 3,
            int(cy + 35 * scale),
        ),
        start=180,
        end=360,
        fill=hair_color,
    )

    eye_y = int(cy - 8 * scale)
    eye_offset = int(25 * scale)
    eye_radius = max(3, int(7 * scale))

    eyes = (
        cx - eye_offset,
        cx + eye_offset,
    )

    # تعبيرات الوجه
    if mood == "surprised":
        for ex in eyes:
            draw.ellipse(
                (
                    ex - eye_radius - 3,
                    eye_y - eye_radius - 4,
                    ex + eye_radius + 3,
                    eye_y + eye_radius + 4,
                ),
                fill=(255, 255, 255),
                outline=outline,
                width=2,
            )

            draw.ellipse(
                (
                    ex - 3,
                    eye_y - 3,
                    ex + 3,
                    eye_y + 3,
                ),
                fill=outline,
            )

        draw.ellipse(
            (
                int(cx - 9 * scale),
                int(cy + 22 * scale),
                int(cx + 9 * scale),
                int(cy + 43 * scale),
            ),
            fill=(95, 35, 40),
        )

    else:
        for ex in eyes:
            draw.ellipse(
                (
                    ex - eye_radius,
                    eye_y - eye_radius,
                    ex + eye_radius,
                    eye_y + eye_radius,
                ),
                fill=outline,
            )

        if mood == "worried":
            draw.line(
                (
                    int(cx - 42 * scale),
                    int(cy - 30 * scale),
                    int(cx - 15 * scale),
                    int(cy - 35 * scale),
                ),
                fill=outline,
                width=max(2, int(4 * scale)),
            )

            draw.line(
                (
                    int(cx + 15 * scale),
                    int(cy - 35 * scale),
                    int(cx + 42 * scale),
                    int(cy - 30 * scale),
                ),
                fill=outline,
                width=max(2, int(4 * scale)),
            )

            draw.arc(
                (
                    int(cx - 23 * scale),
                    int(cy + 30 * scale),
                    int(cx + 23 * scale),
                    int(cy + 55 * scale),
                ),
                start=200,
                end=340,
                fill=outline,
                width=max(2, int(4 * scale)),
            )

        elif mood == "sad":
            draw.arc(
                (
                    int(cx - 25 * scale),
                    int(cy + 30 * scale),
                    int(cx + 25 * scale),
                    int(cy + 65 * scale),
                ),
                start=200,
                end=340,
                fill=outline,
                width=max(2, int(4 * scale)),
            )

        else:
            draw.arc(
                (
                    int(cx - 28 * scale),
                    int(cy + 5 * scale),
                    int(cx + 28 * scale),
                    int(cy + 50 * scale),
                ),
                start=5,
                end=175,
                fill=outline,
                width=max(2, int(5 * scale)),
            )

    # الخدود
    cheek_y = int(cy + 12 * scale)

    for side in (-1, 1):
        cheek_x = int(cx + side * 42 * scale)

        draw.ellipse(
            (
                int(cheek_x - 8 * scale),
                int(cheek_y - 5 * scale),
                int(cheek_x + 8 * scale),
                int(cheek_y + 5 * scale),
            ),
            fill=(240, 125, 135),
        )


# ==========================================
# توليد الصوت باستخدام Gemini
# ==========================================
def make_voice(text):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY مش موجود في GitHub Secrets."
        )

    client = genai.Client(api_key=api_key)

    style = (
        "Speak in natural Egyptian Arabic (Masri), using everyday "
        "Egyptian expressions and pronunciation, not Modern Standard "
        "Arabic. Use a warm, lively female cartoon-storyteller voice. "
        "Speak clearly at a natural pace. Read only the exact story text; "
        "do not add an introduction, explanation, or extra words."
    )

    response = client.models.generate_content(
        model="gemini-3.8-flash-tts",
        contents=[
            {
                "role": "user",
                "parts": [
                    {
                        "text": text,
                        "speech_metadata": {"style": style},
                    }
                ],
            }
        ],
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    voice="Kore"
                )
            ),
        ),
    )

    audio_data = None

    for candidate in response.candidates or []:
        if not candidate.content:
            continue

        for part in candidate.content.parts or []:
            if part.inline_data and part.inline_data.data:
                audio_data = part.inline_data.data
                break

        if audio_data:
            break

    if not audio_data:
        raise RuntimeError(
            "Gemini ملقاش صوت في الاستجابة."
        )

    audio_path = OUT / "narration.wav"
    audio_path.write_bytes(audio_data)

    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )

    if probe.returncode != 0:
        raise RuntimeError(
            "ملف الصوت غير صالح: " + probe.stderr[-1000:]
        )

    return float(probe.stdout.strip())


# ==========================================
# الصوت وتوزيع مدة المشاهد
# ==========================================
narration = " ".join(lines)
audio_duration = make_voice(narration)

# إجمالي الفريمات يطابق مدة الصوت تقريبًا
target_frames = max(
    len(lines),
    round(audio_duration * FPS),
)

weights = [
    max(1, len(line.split()))
    for line in lines
]

total_words = sum(weights)

# توزيع الفريمات حسب طول كل مشهد
scene_frames = []
previous_boundary = 0
cumulative_words = 0

for index, weight in enumerate(weights):
    cumulative_words += weight

    if index == len(weights) - 1:
        boundary = target_frames
    else:
        boundary = round(
            target_frames * cumulative_words / total_words
        )

    scene_frames.append(
        max(1, boundary - previous_boundary)
    )

    previous_boundary = boundary

# تصحيح التقريب للحفاظ على إجمالي عدد الفريمات
scene_frames[-1] += target_frames - sum(scene_frames)


# ==========================================
# إنشاء الإطارات
# ==========================================
if FRAMES.exists():
    shutil.rmtree(FRAMES)

FRAMES.mkdir(parents=True)

moods = [
    "happy",
    "worried",
    "surprised",
    "worried",
    "happy",
]

main_shirt = (235, 90, 90)
main_hair = (65, 40, 32)

second_shirt = (70, 145, 235)
second_hair = (45, 35, 30)

frame_number = 0

for scene_index, text in enumerate(lines):
    base = make_background(scene_index)
    draw = ImageDraw.Draw(base)

    # عنوان القصة
    draw.rounded_rectangle(
        (28, 35, W - 28, 115),
        radius=25,
        fill=(22, 25, 50),
        outline=(225, 205, 170),
        width=3,
    )

    draw.text(
        (W // 2, 75),
        title,
        font=title_font,
        fill=(255, 245, 220),
        anchor="mm",
        direction="rtl",
        language="ar",
    )

    # رقم المشهد
    draw.rounded_rectangle(
        (345, 140, 735, 200),
        radius=22,
        fill=(235, 175, 75),
    )

    draw.text(
        (W // 2, 170),
        f"المشهد {scene_index + 1}",
        font=small_font,
        fill=(40, 30, 45),
        anchor="mm",
        direction="rtl",
        language="ar",
    )

    # لوحة النص
    draw.rounded_rectangle(
        (28, 900, W - 28, 1170),
        radius=30,
        fill=(255, 250, 238),
        outline=(225, 205, 170),
        width=4,
    )

    wrapped = wrap_arabic(
        draw,
        text,
        font,
        W - 105,
    )

    draw.multiline_text(
        (W // 2, 1035),
        wrapped,
        font=font,
        fill=(35, 35, 55),
        anchor="mm",
        align="center",
        spacing=12,
        direction="rtl",
        language="ar",
    )

    mood = moods[min(scene_index, len(moods) - 1)]
    count = scene_frames[scene_index]

    for local_frame in range(count):
        # الحركة تعتمد على الوقت الفعلي، لا على طول المشهد
        elapsed = frame_number / FPS

        bob = 14 * math.sin(
            elapsed * 2 * math.pi * 1.5
        )

        sway = 18 * math.sin(
            elapsed * 2 * math.pi * 0.8
        )

        progress = local_frame / max(1, count - 1)

        frame = base.copy()
        frame_draw = ImageDraw.Draw(frame)

        # الشخصية الأولى
        draw_character(
            frame_draw,
            cx=235 + sway,
            cy=490,
            scale=0.88,
            shirt_color=main_shirt,
            hair_color=main_hair,
            mood=mood,
            movement=bob,
        )

        # الشخصية الثانية
        second_mood = (
            "surprised"
            if mood == "surprised"
            else "happy"
        )

        draw_character(
            frame_draw,
            cx=490 - sway,
            cy=525,
            scale=0.70,
            shirt_color=second_shirt,
            hair_color=second_hair,
            mood=second_mood,
            movement=-bob,
        )

        # تقريب كاميرا تدريجي
        zoom = 1.0 + 0.04 * progress

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

        frame.save(
            FRAMES / f"{frame_number:05d}.jpg",
            quality=94,
        )

        frame_number += 1


# ==========================================
# تجميع الفيديو والصوت
# ==========================================
subprocess.run(
    [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(FRAMES / "%05d.jpg"),
        "-i", str(OUT / "narration.wav"),

        "-map", "0:v:0",
        "-map", "1:a:0",

        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),

        "-c:a", "aac",
        "-b:a", "192k",

        "-af", "aresample=async=1:first_pts=0",

        "-shortest",
        "-movflags", "+faststart",

        str(OUT / "short.mp4"),
    ],
    check=True,
)

print("Video created:", OUT / "short.mp4")
print(
    f"FPS: {FPS} | Frames: {frame_number} | "
    f"Audio duration: {audio_duration:.2f}s"
            )
