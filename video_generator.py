import os
import math
import shutil
import subprocess
import urllib.request
import urllib.error
import json
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageOps


# =========================
# إعدادات الفيديو
# =========================

W, H = 720, 1280
FPS = 24

OUT = Path("output")
FRAMES = OUT / "frames"
IMAGES = OUT / "scene_images"

OUT.mkdir(exist_ok=True)

FONT_PATH = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"

font = ImageFont.truetype(FONT_PATH, 30)
title_font = ImageFont.truetype(FONT_BOLD, 36)
small_font = ImageFont.truetype(FONT_BOLD, 23)


# =========================
# الشخصيات المعروفة
# =========================

CHARACTERS = {
    "تفاحة": (
        "a cute anthropomorphic red apple character, "
        "small green leaf, expressive large eyes"
    ),
    "الفراولة": (
        "a cute anthropomorphic red strawberry character, "
        "tiny green leaves, expressive large eyes"
    ),
    "موزة": (
        "a cute anthropomorphic yellow banana character, "
        "friendly expressive face"
    ),
    "الليمونة": (
        "a cute anthropomorphic yellow lemon character, "
        "expressive eyes and a friendly face"
    ),
    "قطة صغيرة": (
        "a small adorable orange kitten, expressive eyes"
    ),
    "كلب شقي": (
        "a playful small cartoon puppy, expressive eyes"
    ),
    "ولد ذكي": (
        "a clever Egyptian cartoon teenage boy, "
        "short dark hair, casual clothes"
    ),
    "صاحبه": (
        "another Egyptian cartoon teenage boy, "
        "short dark hair, casual clothes"
    ),
    "أرنب": (
        "a cute white cartoon rabbit, expressive eyes"
    ),
    "ثعلب": (
        "an orange cartoon fox, expressive eyes"
    ),
}


# =========================
# قراءة القصة وتقسيمها
# =========================

story_file = OUT / "story.txt"

if not story_file.exists():
    raise FileNotFoundError("ملف output/story.txt مش موجود!")

story = story_file.read_text(encoding="utf-8")

title = "حكايات كرتونية"
scene_blocks = []
current_scene = None

for raw_line in story.splitlines():
    line = raw_line.strip()

    if not line:
        continue

    if line.startswith("عنوان القصة:"):
        title = line.split(":", 1)[1].strip()
        continue

    if line.startswith("المشهد"):
        if current_scene:
            scene_blocks.append(" ".join(current_scene))

        current_scene = []
        continue

    if line.startswith("النهاية:"):
        if current_scene:
            scene_blocks.append(" ".join(current_scene))

        current_scene = []
        continue

    if current_scene is not None:
        current_scene.append(line)

if current_scene:
    scene_blocks.append(" ".join(current_scene))

scenes = [
    text.strip()
    for text in scene_blocks
    if text.strip()
]

# ضمان عدم فقد القصة لو تنسيقها مختلف
if not scenes:
    scenes = [
        line.strip()
        for line in story.splitlines()
        if line.strip()
        and not line.startswith("عنوان القصة:")
        and not line.startswith("المشهد")
        and not line.startswith("النهاية:")
    ]

scenes = scenes[:5]

if not scenes:
    raise ValueError("القصة لا تحتوي على مشاهد صالحة!")

print(f"Story title: {title}")
print(f"Scenes found: {len(scenes)}")


# =========================
# تجهيز وصف الشخصيات
# =========================

found_characters = [
    description
    for name, description in CHARACTERS.items()
    if name in title
]

if not found_characters:
    found_characters = [
        "a cute expressive 3D cartoon character"
    ]

character_description = "; ".join(found_characters[:2])


# =========================
# تجهيز وصف مختلف لكل مشهد
# =========================

def build_prompt(index, scene_text):
    scene_directions = [
        (
            "Show the main character enjoying an ordinary day "
            "in a colorful Egyptian neighborhood, wide establishing shot."
        ),
        (
            "Show the characters meeting unexpectedly in a Cairo street, "
            "expressive faces, dynamic composition."
        ),
        (
            "Show the main character discovering a mysterious problem, "
            "dramatic lighting, suspenseful atmosphere."
        ),
        (
            "Show a surprising revelation between the characters, "
            "strong emotions, cinematic close-up."
        ),
        (
            "Show a mysterious cliffhanger with a glowing object or "
            "a strange discovery, dramatic cinematic composition."
        ),
    ]

    direction = scene_directions[min(index, 4)]

    # تفاصيل إضافية حسب أحداث القصة
    if "صندوق" in scene_text:
        direction += (
            " Include a mysterious old box with a soft glowing light."
        )

    if "منتصف الليل" in scene_text or "الليل" in scene_text:
        direction += (
            " It is nighttime, with moonlight and dramatic shadows."
        )

    if "مسابقة" in scene_text:
        direction += (
            " Show a colorful competition stage and a small audience."
        )

    if "سر" in scene_text or "الحقيقة" in scene_text:
        direction += (
            " Include a mysterious clue and surprised character expressions."
        )

    return f"""
Create a polished, high-quality 3D animated movie frame.

Characters:
{character_description}

Scene:
{direction}

Story context:
{scene_text}

Visual requirements:
- Consistent character designs and clothing across scenes.
- Expressive faces and clear body language.
- Detailed cinematic environment.
- Professional 3D cartoon movie aesthetic.
- Beautiful cinematic lighting and depth.
- Rich colors and realistic soft shadows.
- Portrait 9:16 composition.
- Keep the main characters clearly visible.
- No text, no captions, no letters, no watermark.
"""


# =========================
# توليد الصور باستخدام Cloudflare
# =========================

def generate_image(prompt, index):
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not account_id or not api_token:
        raise RuntimeError(
            "تأكد من إضافة CLOUDFLARE_ACCOUNT_ID "
            "وCLOUDFLARE_API_TOKEN في GitHub Secrets "
            "وتمريرهما إلى خطوة تشغيل الفيديو."
        )

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/ai/run/"
        "@cf/bytedance/stable-diffusion-xl-lightning"
    )

    payload = {
        "prompt": prompt,
        "width": 576,
        "height": 1024,
        "num_steps": 4,
        "negative_prompt": (
            "blurry, low quality, distorted face, "
            "extra limbs, extra fingers, duplicate characters, "
            "text, letters, watermark"
        ),
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    print(f"Generating image {index + 1}/{len(scenes)}...")

    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            image_bytes = response.read()

    except urllib.error.HTTPError as error:
        error_text = error.read().decode(
            "utf-8", errors="replace"
        )

        raise RuntimeError(
            f"Cloudflare image generation failed "
            f"(HTTP {error.code}): {error_text[:1000]}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"تعذر الاتصال بـ Cloudflare: {error.reason}"
        ) from error

    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as error:
        raise RuntimeError(
            "Cloudflare لم يرجع صورة صالحة. "
            "راجع رسالة الخطأ وحدود الاستخدام."
        ) from error

    IMAGES.mkdir(parents=True, exist_ok=True)

    image_path = IMAGES / f"scene_{index + 1}.jpg"
    image.save(image_path, quality=95)

    print(f"Image saved: {image_path}")

    return image_path


# =========================
# توليد التعليق الصوتي
# =========================

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
            "Gemini لم يرجع صوتًا صالحًا. "
            "راجع الموديل وحدود الـ API."
        )

    audio_path = OUT / "narration.wav"
    audio_path.write_bytes(audio_data)

    print("Voice generated:", audio_path)


# =========================
# أدوات مساعدة للنص العربي
# =========================

def wrap_arabic(draw, text, selected_font, max_width):
    words = text.split()
    result = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()

        width = draw.textbbox(
            (0, 0),
            candidate,
            font=selected_font,
            direction="rtl",
        )[2]

        if width <= max_width or not current:
            current = candidate
        else:
            result.append(current)
            current = word

    if current:
        result.append(current)

    return "\n".join(result)


# =========================
# رسم النص فوق الصورة
# =========================

def decorate_frame(image, scene_text, scene_index, total_scenes):
    frame = image.convert("RGB")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # شريط العنوان
    draw.rounded_rectangle(
        (22, 25, W - 22, 105),
        radius=24,
        fill=(0, 0, 0, 155),
    )

    title_text = wrap_arabic(
        draw, title, title_font, W - 70
    )

    draw.multiline_text(
        (W // 2, 65),
        title_text,
        font=title_font,
        fill=(255, 255, 255),
        anchor="mm",
        align="center",
        direction="rtl",
        language="ar",
    )

    # رقم المشهد
    draw.rounded_rectangle(
        (W // 2 - 100, 120, W // 2 + 100, 165),
        radius=18,
        fill=(0, 0, 0, 125),
    )

    draw.text(
        (W // 2, 142),
        f"المشهد {scene_index + 1} من {total_scenes}",
        font=small_font,
        fill=(255, 255, 255),
        anchor="mm",
        direction="rtl",
        language="ar",
    )

    # لوحة التعليق المكتوب
    draw.rounded_rectangle(
        (24, 865, W - 24, 1235),
        radius=30,
        fill=(0, 0, 0, 175),
        outline=(255, 255, 255, 90),
        width=2,
    )

    wrapped_text = wrap_arabic(
        draw, scene_text, font, W - 90
    )

    draw.multiline_text(
        (W // 2, 1045),
        wrapped_text,
        font=font,
        fill=(255, 255, 255),
        anchor="mm",
        align="center",
        spacing=9,
        direction="rtl",
        language="ar",
    )

    return Image.alpha_composite(
        frame.convert("RGBA"), overlay
    ).convert("RGB")


# =========================
# تنفيذ الفيديو
# =========================

def main():
    narration = " ".join(scenes)

    # إنشاء الصوت أولًا لمعرفة مدته
    make_voice(narration)

    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(OUT / "narration.wav"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    audio_duration = float(probe.stdout.strip())

    total_frames = max(
        FPS * len(scenes),
        round(audio_duration * FPS),
    )

    # توزيع مدة الفيديو على المشاهد حسب طول النص
    weights = [max(1, len(scene.split())) for scene in scenes]
    weight_total = sum(weights)

    frame_counts = [
        max(1, round(total_frames * weight / weight_total))
        for weight in weights
    ]

    frame_counts[-1] += total_frames - sum(frame_counts)

    if frame_counts[-1] < 1:
        raise RuntimeError(
            "مدة الصوت قصيرة جدًا لعدد المشاهد."
        )

    # حذف الإطارات والصور القديمة
    for folder in (FRAMES, IMAGES):
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)

    # توليد صورة مستقلة لكل مشهد
    scene_images = []

    for index, scene_text in enumerate(scenes):
        prompt = build_prompt(index, scene_text)
        path = generate_image(prompt, index)
        scene_images.append(path)

    frame_number = 0
    previous_scene_frame = None
    transition_frames = max(1, FPS // 3)

    for scene_index, (scene_text, image_path, count) in enumerate(
        zip(scenes, scene_images, frame_counts)
    ):
        print(f"Rendering scene {scene_index + 1}/{len(scenes)}")

        source = Image.open(image_path).convert("RGB")

        base = ImageOps.fit(
            source,
            (W, H),
            method=Image.Resampling.LANCZOS,
        )

        scene_last_frame = None

        for local_frame in range(count):
            progress = local_frame / max(1, count - 1)

            # حركة تقريب تدريجية مع تحريك بسيط للكاميرا
            zoom = 1.0 + 0.075 * progress

            new_w = int(W * zoom)
            new_h = int(H * zoom)

            enlarged = base.resize(
                (new_w, new_h),
                Image.Resampling.LANCZOS,
            )

            max_left = new_w - W
            max_top = new_h - H

            left = int(
                max_left * (
                    0.5 + 0.15 * math.sin(progress * math.pi)
                )
            )

            top = int(
                max_top * (
                    0.5 + 0.15 * math.cos(progress * math.pi)
                )
            )

            left = max(0, min(left, max_left))
            top = max(0, min(top, max_top))

            frame = enlarged.crop(
                (left, top, left + W, top + H)
            )

            frame = decorate_frame(
                frame,
                scene_text,
                scene_index,
                len(scenes),
            )

            # انتقال تدريجي بين المشاهد
            if (
                previous_scene_frame is not None
                and local_frame < transition_frames
            ):
                alpha = (
                    local_frame + 1
                ) / transition_frames

                frame = Image.blend(
                    previous_scene_frame,
                    frame,
                    alpha,
                )

            frame.save(
                FRAMES / f"{frame_number:05d}.jpg",
                quality=90,
            )

            scene_last_frame = frame
            frame_number += 1

        previous_scene_frame = scene_last_frame

    # تجميع الفيديو والصوت
    output_video = OUT / "short.mp4"

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate", str(FPS),
            "-i", str(FRAMES / "%05d.jpg"),
            "-i", str(OUT / "narration.wav"),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-af", "aresample=async=1:first_pts=0",
            "-shortest",
            "-movflags", "+faststart",
            str(output_video),
        ],
        check=True,
    )

    print("Video created:", output_video)


if __name__ == "__main__":
    main()
