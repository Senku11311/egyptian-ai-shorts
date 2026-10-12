import subprocess
import shutil
import math
import os
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# =========================================================
# إعدادات الفيديو
# =========================================================
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


# =========================================================
# قراءة القصة
# =========================================================
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
        title = line.split(":", 1)[1].strip() or title
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


# =========================================================
# أدوات مساعدة
# =========================================================
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

        if bbox[2] - bbox[0] <= max_width or not current:
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


def make_gradient(top, bottom):
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        color = lerp_color(
            top,
            bottom,
            y / max(1, H - 1),
        )

        draw.line(
            (0, y, W, y),
            fill=color,
        )

    return img


def add_glow(img, box, color, blur=55):
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)

    glow_draw.ellipse(
        box,
        fill=(*color, 115),
    )

    glow = glow.filter(
        ImageFilter.GaussianBlur(blur)
    )

    return Image.alpha_composite(
        img.convert("RGBA"),
        glow,
    ).convert("RGB")


# =========================================================
# خلفيات مصرية سينمائية
# =========================================================
PALETTES = [
    ((20, 31, 66), (190, 104, 82)),
    ((20, 62, 91), (105, 158, 155)),
    ((42, 30, 70), (176, 94, 117)),
    ((27, 43, 65), (135, 140, 157)),
    ((42, 36, 60), (207, 137, 83)),
]


def make_background(scene_index):
    top, bottom = PALETTES[
        scene_index % len(PALETTES)
    ]

    img = make_gradient(top, bottom)

    img = add_glow(
        img,
        (120, 150, 600, 630),
        (255, 204, 132),
        70,
    )

    draw = ImageDraw.Draw(img)

    # مبانٍ مصرية متدرجة في العمق
    for i in range(16):
        x = i * 72 - 10

        building_height = (
            170 + ((i * 59 + scene_index * 31) % 250)
        )

        y = 870 - building_height

        shade = (
            37 + (i % 4) * 5,
            43 + (i % 3) * 5,
            62 + (i % 4) * 4,
        )

        draw.rectangle(
            (x, y, x + 82, 875),
            fill=shade,
        )

        # خزانات مياه وهوائيات
        if i % 3 == 0:
            draw.rectangle(
                (x + 25, y - 25, x + 53, y),
                fill=(34, 39, 56),
            )

            draw.line(
                (x + 39, y - 48, x + 39, y - 25),
                fill=(34, 39, 56),
                width=4,
            )

        # شبابيك مضيئة
        for wy in range(y + 28, 845, 43):
            for wx in range(x + 12, x + 70, 26):
                if (wx + wy + scene_index) % 4:
                    draw.rounded_rectangle(
                        (wx, wy, wx + 10, wy + 16),
                        radius=2,
                        fill=(232, 186, 111),
                    )

    # واجهة محل في بعض المشاهد
    if scene_index % 2 == 0:
        draw.rectangle(
            (35, 650, 310, 895),
            fill=(103, 68, 54),
        )

        draw.rectangle(
            (55, 690, 290, 855),
            fill=(32, 43, 55),
        )

        draw.rectangle(
            (35, 625, 310, 680),
            fill=(225, 170, 77),
        )

        draw.text(
            (172, 652),
            "بقالة",
            font=small_font,
            fill=(48, 37, 34),
            anchor="mm",
            direction="rtl",
            language="ar",
        )

        for x in range(45, 305, 42):
            color = (
                (181, 72, 67)
                if (x // 42) % 2
                else (240, 211, 151)
            )

            draw.polygon(
                [
                    (x, 680),
                    (x + 22, 680),
                    (x + 32, 707),
                    (x + 10, 707),
                ],
                fill=color,
            )

    # أرضية الشارع
    draw.polygon(
        [(0, 825), (W, 825), (W, H), (0, H)],
        fill=(47, 50, 64),
    )

    draw.polygon(
        [(0, 910), (W, 910), (W, 1050), (0, 1050)],
        fill=(61, 63, 75),
    )

    # خطوط المنظور
    for i in range(8):
        y = 920 + i * 125

        draw.line(
            (0, y, W, y + 55),
            fill=(76, 78, 88),
            width=3,
        )

    draw.line(
        (W // 2, 845, 290, H),
        fill=(86, 84, 91),
        width=5,
    )

    draw.line(
        (W // 2, 845, 850, H),
        fill=(86, 84, 91),
        width=5,
    )

    # أعمدة إنارة
    for lx in (75, 990):
        draw.line(
            (lx, 570, lx, 870),
            fill=(30, 34, 47),
            width=11,
        )

        end_x = lx + (
            50 if lx < W // 2 else -50
        )

        draw.line(
            (lx, 575, end_x, 575),
            fill=(30, 34, 47),
            width=9,
        )

        draw.ellipse(
            (
                end_x - 13,
                562,
                end_x + 13,
                588,
            ),
            fill=(255, 218, 145),
        )

    # تظليل خفيف على الأطراف
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)

    mask_draw.ellipse(
        (-220, -180, W + 220, H + 220),
        fill=210,
    )

    mask = mask.filter(
        ImageFilter.GaussianBlur(130)
    )

    dark = Image.new(
        "RGB",
        (W, H),
        (10, 12, 24),
    )

    return Image.composite(
        img,
        dark,
        mask,
    )


# =========================================================
# رسم شخصية كرتونية بتأثير شبه ثلاثي الأبعاد
# =========================================================
def draw_character(
    base,
    cx,
    cy,
    scale,
    shirt_color,
    hair_color,
    mood,
    elapsed,
    role=0,
):
    s = scale

    cx = int(cx)
    cy = int(cy)

    # حركة مستمرة مع الزمن
    bob = (
        math.sin(elapsed * 2 * math.pi * 1.35 + role)
        * 8 * s
    )

    walk = math.sin(
        elapsed * 2 * math.pi * 1.1 + role
    )

    cy += int(bob)

    arm_swing = int(18 * walk * s)
    leg_swing = int(11 * walk * s)

    outline = (37, 29, 39, 255)

    skin = (235, 171, 128, 255)
    skin_light = (255, 210, 164, 255)
    skin_shadow = (190, 116, 88, 255)

    shirt_light = tuple(
        min(255, c + 36)
        for c in shirt_color
    ) + (255,)

    shirt_dark = tuple(
        max(0, c - 45)
        for c in shirt_color
    ) + (255,)

    shirt = tuple(shirt_color) + (255,)

    layer = Image.new(
        "RGBA",
        base.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(layer)

    # ظل أسفل الشخصية
    shadow = Image.new(
        "RGBA",
        base.size,
        (0, 0, 0, 0),
    )

    shadow_draw = ImageDraw.Draw(shadow)

    shadow_draw.ellipse(
        (
            int(cx - 105 * s),
            int(cy + 240 * s),
            int(cx + 105 * s),
            int(cy + 278 * s),
        ),
        fill=(4, 7, 15, 100),
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(
            max(3, int(12 * s))
        )
    )

    layer = Image.alpha_composite(
        layer,
        shadow,
    )

    draw = ImageDraw.Draw(layer)

    # الرجلان
    draw.line(
        (
            int(cx - 28 * s),
            int(cy + 185 * s),
            int(cx - 36 * s + leg_swing),
            int(cy + 245 * s),
        ),
        fill=outline,
        width=max(7, int(16 * s)),
    )

    draw.line(
        (
            int(cx + 28 * s),
            int(cy + 185 * s),
            int(cx + 36 * s - leg_swing),
            int(cy + 245 * s),
        ),
        fill=outline,
        width=max(7, int(16 * s)),
    )

    # الحذاء
    draw.ellipse(
        (
            int(cx - 66 * s + leg_swing),
            int(cy + 235 * s),
            int(cx - 22 * s + leg_swing),
            int(cy + 258 * s),
        ),
        fill=(35, 33, 42, 255),
        outline=outline,
        width=3,
    )

    draw.ellipse(
        (
            int(cx + 17 * s - leg_swing),
            int(cy + 235 * s),
            int(cx + 63 * s - leg_swing),
            int(cy + 258 * s),
        ),
        fill=(35, 33, 42, 255),
        outline=outline,
        width=3,
    )

    # الذراعان
    left_y = cy + int(
        (95 if mood == "surprised" else 135) * s
    )

    right_y = cy + int(
        (95 if mood == "worried" else 135) * s
    )

    draw.line(
        (
            int(cx - 57 * s),
            int(cy + 72 * s),
            int(cx - 92 * s - arm_swing),
            left_y,
        ),
        fill=outline,
        width=max(8, int(22 * s)),
    )

    draw.line(
        (
            int(cx + 57 * s),
            int(cy + 72 * s),
            int(cx + 92 * s + arm_swing),
            right_y,
        ),
        fill=outline,
        width=max(8, int(22 * s)),
    )

    draw.line(
        (
            int(cx - 57 * s),
            int(cy + 72 * s),
            int(cx - 92 * s - arm_swing),
            left_y,
        ),
        fill=skin,
        width=max(5, int(13 * s)),
    )

    draw.line(
        (
            int(cx + 57 * s),
            int(cy + 72 * s),
            int(cx + 92 * s + arm_swing),
            right_y,
        ),
        fill=skin,
        width=max(5, int(13 * s)),
    )

    # الجسم
    draw.rounded_rectangle(
        (
            int(cx - 70 * s),
            int(cy + 42 * s),
            int(cx + 70 * s),
            int(cy + 205 * s),
        ),
        radius=int(28 * s),
        fill=shirt,
        outline=outline,
        width=max(3, int(5 * s)),
    )

    # إضاءة على جانب القميص
    draw.rounded_rectangle(
        (
            int(cx - 59 * s),
            int(cy + 53 * s),
            int(cx - 31 * s),
            int(cy + 190 * s),
        ),
        radius=int(12 * s),
        fill=shirt_light,
    )

    # ظل على الجانب الآخر
    draw.polygon(
        [
            (int(cx + 34 * s), int(cy + 48 * s)),
            (int(cx + 66 * s), int(cy + 57 * s)),
            (int(cx + 66 * s), int(cy + 190 * s)),
            (int(cx + 42 * s), int(cy + 198 * s)),
        ],
        fill=shirt_dark,
    )

    # ياقة القميص
    draw.polygon(
        [
            (int(cx - 20 * s), int(cy + 43 * s)),
            (cx, int(cy + 69 * s)),
            (int(cx + 20 * s), int(cy + 43 * s)),
            (int(cx + 10 * s), int(cy + 81 * s)),
            (int(cx - 10 * s), int(cy + 81 * s)),
        ],
        fill=(246, 229, 205, 255),
    )

    # الرقبة
    draw.rounded_rectangle(
        (
            int(cx - 18 * s),
            int(cy + 17 * s),
            int(cx + 18 * s),
            int(cy + 65 * s),
        ),
        radius=int(8 * s),
        fill=skin_shadow,
    )

    draw.rectangle(
        (
            int(cx - 13 * s),
            int(cy + 20 * s),
            int(cx + 11 * s),
            int(cy + 57 * s),
        ),
        fill=skin,
    )

    # الرأس
    r = int(72 * s)

    draw.ellipse(
        (
            int(cx - r + 5 * s),
            int(cy - r + 8 * s),
            int(cx + r + 8 * s),
            int(cy + r + 11 * s),
        ),
        fill=(15, 15, 27, 90),
    )

    draw.ellipse(
        (
            cx - r,
            cy - r,
            cx + r,
            cy + r,
        ),
        fill=skin,
        outline=outline,
        width=max(3, int(5 * s)),
    )

    # إضاءة الوجه
    draw.ellipse(
        (
            int(cx - r + 9 * s),
            int(cy - r + 8 * s),
            int(cx + 18 * s),
            int(cy + 30 * s),
        ),
        fill=skin_light,
    )

    # ظل الوجه
    draw.ellipse(
        (
            int(cx + 20 * s),
            int(cy - 10 * s),
            int(cx + r - 7 * s),
            int(cy + r - 4 * s),
        ),
        fill=skin_shadow,
    )

    # الشعر
    draw.pieslice(
        (
            cx - r - 3,
            int(cy - r - 10 * s),
            cx + r + 3,
            int(cy + 45 * s),
        ),
        start=180,
        end=360,
        fill=tuple(hair_color) + (255,),
        outline=outline,
        width=max(2, int(3 * s)),
    )

    draw.polygon(
        [
            (int(cx - 55 * s), int(cy - r + 26 * s)),
            (int(cx - 22 * s), int(cy - r + 8 * s)),
            (int(cx + 4 * s), int(cy - r + 30 * s)),
            (int(cx + 33 * s), int(cy - r + 18 * s)),
            (int(cx + 52 * s), int(cy - r + 44 * s)),
            (int(cx - 50 * s), int(cy - r + 48 * s)),
        ],
        fill=tuple(hair_color) + (255,),
    )

    # العينان والحواجب
    eye_y = int(cy - 7 * s)
    eye_r = max(4, int(8 * s))

    for side in (-1, 1):
        ex = int(cx + side * 25 * s)

        brow_y = int(
            eye_y - (
                25 * s
                if mood == "surprised"
                else 18 * s
            )
        )

        draw.line(
            (
                ex - int(11 * s),
                brow_y,
                ex + int(10 * s),
                brow_y + int(2 * s),
            ),
            fill=outline,
            width=max(2, int(5 * s)),
        )

        draw.ellipse(
            (
                ex - eye_r - int(3 * s),
                eye_y - eye_r - int(4 * s),
                ex + eye_r + int(3 * s),
                eye_y + eye_r + int(5 * s),
            ),
            fill=(255, 251, 241, 255),
        )

        pupil_shift = int(
            2 * s * math.sin(elapsed * 1.8 + role)
        )

        draw.ellipse(
            (
                ex - 4 + pupil_shift,
                eye_y - 4,
                ex + 4 + pupil_shift,
                eye_y + 5,
            ),
            fill=(34, 30, 38, 255),
        )

        draw.ellipse(
            (
                ex - 2 + pupil_shift,
                eye_y - 3,
                ex + 1 + pupil_shift,
                eye_y,
            ),
            fill=(255, 255, 255, 255),
        )

    # الأنف
    draw.ellipse(
        (
            int(cx - 5 * s),
            int(cy + 3 * s),
            int(cx + 7 * s),
            int(cy + 18 * s),
        ),
        fill=skin_shadow,
    )

    # تعبيرات الفم
    if mood == "surprised":
        draw.ellipse(
            (
                int(cx - 10 * s),
                int(cy + 27 * s),
                int(cx + 10 * s),
                int(cy + 50 * s),
            ),
            fill=(103, 35, 47, 255),
            outline=outline,
            width=2,
        )

    elif mood in ("worried", "sad"):
        draw.arc(
            (
                int(cx - 24 * s),
                int(cy + 31 * s),
                int(cx + 24 * s),
                int(cy + 62 * s),
            ),
            start=205,
            end=335,
            fill=outline,
            width=max(3, int(5 * s)),
        )

    else:
        draw.arc(
            (
                int(cx - 28 * s),
                int(cy + 10 * s),
                int(cx + 28 * s),
                int(cy + 51 * s),
            ),
            start=10,
            end=170,
            fill=outline,
            width=max(3, int(5 * s)),
        )

    # الخدود
    for side in (-1, 1):
        ex = int(cx + side * 43 * s)

        draw.ellipse(
            (
                ex - int(9 * s),
                int(cy + 14 * s),
                ex + int(8 * s),
                int(cy + 23 * s),
            ),
            fill=(238, 120, 126, 145),
        )

    return Image.alpha_composite(
        base.convert("RGBA"),
        layer,
    ).convert("RGB")


# =========================================================
# توليد الصوت باستخدام Gemini
# =========================================================
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
            "Gemini ملقاش صوت في الاستجابة!"
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


# =========================================================
# توزيع زمن الصوت على المشاهد
# =========================================================
narration = " ".join(lines)
audio_duration = make_voice(narration)

target_frames = max(
    len(lines),
    round(audio_duration * FPS),
)

weights = [
    max(1, len(line.split()))
    for line in lines
]

total_words = sum(weights)

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

scene_frames[-1] += target_frames - sum(scene_frames)


# =========================================================
# إنشاء الإطارات
# =========================================================
if FRAMES.exists():
    shutil.rmtree(FRAMES)

FRAMES.mkdir(parents=True)

moods = [
    "happy",
    "worried",
    "surprised",
    "sad",
    "happy",
]

main_shirt = (221, 83, 73)
main_hair = (54, 34, 29)

second_shirt = (56, 133, 205)
second_hair = (39, 31, 28)

frame_number = 0

for scene_index, text in enumerate(lines):
    base = make_background(scene_index)

    # لوحة العنوان والنص
    overlay = Image.new(
        "RGBA",
        (W, H),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(overlay)

    draw.rounded_rectangle(
        (28, 35, W - 28, 115),
        radius=25,
        fill=(18, 22, 43, 225),
        outline=(235, 204, 151, 255),
        width=3,
    )

    draw.text(
        (W // 2, 75),
        title,
        font=title_font,
        fill=(255, 244, 219),
        anchor="mm",
        direction="rtl",
        language="ar",
    )

    draw.rounded_rectangle(
        (345, 140, 735, 200),
        radius=22,
        fill=(238, 177, 78, 245),
    )

    draw.text(
        (W // 2, 170),
        f"المشهد {scene_index + 1}",
        font=small_font,
        fill=(40, 30, 42),
        anchor="mm",
        direction="rtl",
        language="ar",
    )

    draw.rounded_rectangle(
        (28, 1430, W - 28, 1730),
        radius=32,
        fill=(15, 20, 37, 218),
        outline=(236, 204, 157, 255),
        width=4,
    )

    wrapped = wrap_arabic(
        draw,
        text,
        font,
        W - 105,
    )

    draw.multiline_text(
        (W // 2, 1580),
        wrapped,
        font=font,
        fill=(255, 249, 234),
        anchor="mm",
        align="center",
        spacing=14,
        direction="rtl",
        language="ar",
    )

    count = scene_frames[scene_index]

    for local_frame in range(count):
        elapsed = frame_number / FPS

        progress = local_frame / max(1, count - 1)
        zoom = 1.0 + 0.035 * progress

        frame = base.copy()

        # الشخصية الأولى
        frame = draw_character(
            frame,
            cx=310 + 15 * math.sin(elapsed * 0.8),
            cy=560,
            scale=1.03,
            shirt_color=main_shirt,
            hair_color=main_hair,
            mood=moods[scene_index % len(moods)],
            elapsed=elapsed,
            role=0,
        )

        # الشخصية الثانية
        frame = draw_character(
            frame,
            cx=710 - 13 * math.sin(elapsed * 0.8),
            cy=600,
            scale=0.82,
            shirt_color=second_shirt,
            hair_color=second_hair,
            mood=(
                "surprised"
                if scene_index in (1, 2)
                else "happy"
            ),
            elapsed=elapsed,
            role=1,
        )

        frame = Image.alpha_composite(
            frame.convert("RGBA"),
            overlay,
        ).convert("RGB")

        # تقريب الكاميرا تدريجيًا
        new_w = int(W * zoom)
        new_h = int(H * zoom)

        if new_w != W or new_h != H:
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
            quality=93,
            optimize=True,
        )

        frame_number += 1


# =========================================================
# تجميع الفيديو والصوت
# =========================================================
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
