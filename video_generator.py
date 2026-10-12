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

W, H = 720, 1280
FPS = 15

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
    top, bottom = backgrounds[
        scene_index % len(backgrounds)
    ]

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # تدرج رأسي ناعم
    for y in range(H):
        color = lerp_color(top, bottom, y / H)
        draw.line((0, y, W, y), fill=color)

    # إضاءة سينمائية خلف الشخصيات
    draw.ellipse(
        (120, 170, 600, 650),
        fill=lerp_color(top, (225, 185, 155), 0.22),
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

    # مبانٍ بعيدة لإضافة العمق
    for i in range(9):
        x = i * 95 - 15
        height = 100 + (i * 37 % 100)

        draw.rectangle(
            (
                x,
                760 - height,
                x + 75,
                790,
            ),
            fill=(30, 35, 65),
        )

        # نوافذ
        for wy in range(700 - height, 770, 35):
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

    # خط أرضي مضيء
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

    # تحريك الذراعين بصورة بسيطة
    arm_shift = int(12 * math.sin(movement / 4))

    # الرجلان
    draw.line(
        (
            cx - 30 * scale,
            cy + 195 * scale,
            cx - 42 * scale,
            cy + 245 * scale,
        ),
        fill=outline,
        width=max(4, int(15 * scale)),
    )

    draw.line(
        (
            cx + 30 * scale,
            cy + 195 * scale,
            cx + 42 * scale,
            cy + 245 * scale,
        ),
        fill=outline,
        width=max(4, int(15 * scale)),
    )

    # الجسم
    draw.rounded_rectangle(
        (
            cx - 70 * scale,
            cy + 45 * scale,
            cx + 70 * scale,
            cy + 205 * scale,
        ),
        radius=int(28 * scale),
        fill=shirt_color,
        outline=outline,
        width=max(3, int(5 * scale)),
    )

    # الذراعان
    draw.line(
        (
            cx - 65 * scale,
            cy + 75 * scale,
            cx - 95 * scale,
            cy + (130 + arm_shift) * scale,
        ),
        fill=outline,
        width=max(5, int(18 * scale)),
    )

    draw.line(
        (
            cx + 65 * scale,
            cy + 75 * scale,
            cx + 95 * scale,
            cy + (130 - arm_shift) * scale,
        ),
        fill=outline,
        width=max(5, int(18 * scale)),
    )

    # الرقبة
    draw.rectangle(
        (
            cx - 18 * scale,
            cy + 20 * scale,
            cx + 18 * scale,
            cy + 65 * scale,
        ),
        fill=(225, 165, 125),
    )

    # الرأس
    radius = 70 * scale

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
            cy + 35 * scale,
        ),
        start=180,
        end=360,
        fill=hair_color,
    )

    eye_y = cy - 8 * scale
    eye_offset = 25 * scale
    eye_radius = max(3, int(7 * scale))

    # تعبيرات الوجه
    if mood == "surprised":
        for ex in (
            cx - eye_offset,
            cx + eye_offset,
        ):
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
                cx - 9 * scale,
                cy + 22 * scale,
                cx + 9 * scale,
                cy + 43 * scale,
            ),
            fill=(95, 35, 40),
        )

    elif mood == "worried":
        for ex in (
            cx - eye_offset,
            cx + eye_offset,
        ):
            draw.ellipse(
                (
                    ex - eye_radius,
                    eye_y - eye_radius,
                    ex + eye_radius,
                    eye_y + eye_radius,
                ),
                fill=outline,
            )

        draw.line(
            (
                cx - 42 * scale,
                cy - 30 * scale,
                cx - 15 * scale,
                cy - 35 * scale,
            ),
            fill=outline,
            width=max(2, int(4 * scale)),
        )

        draw.line(
            (
                cx + 15 * scale,
                cy - 35 * scale,
                cx + 42 * scale,
                cy - 30 * scale,
            ),
            fill=outline,
            width=max(2, int(4 * scale)),
        )

        draw.arc(
            (
                cx - 23 * scale,
                cy + 30 * scale,
                cx + 23 * scale,
                cy + 55 * scale,
            ),
            start=200,
            end=340,
            fill=outline,
            width=max(2, int(4 * scale)),
        )

    elif mood == "sad":
        for ex in (
            cx - eye_offset,
            cx + eye_offset,
        ):
            draw.ellipse(
                (
                    ex - eye_radius,
                    eye_y - eye_radius,
                    ex + eye_radius,
                    eye_y + eye_radius,
                ),
                fill=outline,
            )

        draw.arc(
            (
                cx - 25 * scale,
                cy + 30 * scale,
                cx + 25 * scale,
                cy + 65 * scale,
            ),
            start=200,
            end=340,
            fill=outline,
            width=max(2, int(4 * scale)),
        )

    else:
        for ex in (
            cx - eye_offset,
            cx + eye_offset,
        ):
            draw.ellipse(
                (
                    ex - eye_radius,
                    eye_y - eye_radius,
                    ex + eye_radius,
                    eye_y + eye_radius,
                ),
                fill=outline,
            )

        draw.arc(
            (
                cx - 28 * scale,
                cy + 5 * scale,
                cx + 28 * scale,
                cy + 50 * scale,
            ),
            start=5,
            end=175,
            fill=outline,
            width=max(2, int(5 * scale)),
        )

    # الخدود
    cheek_y = cy + 12 * scale

    for side in (-1, 1):
        cheek_x = cx + side * 42 * scale

        draw.ellipse(
            (
                cheek_x - 8 * scale,
                cheek_y - 5 * scale,
                cheek_x + 8 * scale,
                cheek_y + 5 * scale,
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
# تجهيز الصوت وتوقيت المشاهد
# ==========================================

narration = " ".join(lines)

audio_duration = make_voice(narration)

weights = [
    max(1, len(line.split()))
    for line in lines
]

total_words = sum(weights)

# توزيع وقت الفيديو حسب طول كل مشهد
target_frames = max(
    len(lines) * FPS * 2,
    round(audio_duration * FPS),
)

scene_frames = [
    max(
        FPS * 2,
        round(target_frames * weight / total_words),
    )
    for weight in weights
]

# ضبط المجموع على مدة الفيديو المستهدفة
difference = target_frames - sum(scene_frames)

scene_frames[-1] += difference

if scene_frames[-1] < FPS:
    scene_frames[-1] = FPS


# ==========================================
# إنشاء الإطارات
# ==========================================

if FRAMES.exists():
    shutil.rmtree(FRAMES)

FRAMES.mkdir(parents=True)

# تعبيرات الوجه حسب تطور القصة
moods = [
    "happy",
    "worried",
    "surprised",
    "worried",
    "happy",
]

# ألوان ثابتة للشخصيتين
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
        (245, 140, 475, 190),
        radius=22,
        fill=(235, 175, 75),
    )

    draw.text(
        (W // 2, 165),
        f"المشهد {scene_index + 1}",
        font=small_font,
        fill=(40, 30, 45),
        anchor="mm",
        direction="rtl",
        language="ar",
    )

    # لوحة الترجمة
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

    mood = moods[
        min(scene_index, len(moods) - 1)
    ]

    count = scene_frames[scene_index]

    for local_frame in range(count):

        progress = local_frame / max(1, count - 1)

        # حركة رأسية ناعمة
        bob = 8 * math.sin(progress * math.pi * 4)

        # حركة بسيطة بين الشخصيتين
        sway = 10 * math.sin(progress * math.pi * 2)

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

        # الشخصية الثانية تظهر في جميع المشاهد
        # مع الحفاظ على شكلها وألوانها
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
        zoom = 1.0 + 0.025 * progress

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
            quality=92,
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
        "-crf", "20",
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
