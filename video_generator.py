import os
import math
import shutil
import subprocess
import urllib.request
import urllib.error
import json
import base64
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

# التعامل مع تنسيقات القصص المختلفة
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
# تحليل القصة باستخدام Gemini
# =========================

def generate_scene_prompts(scenes, title):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY مش موجود في GitHub Secrets."
        )

    client = genai.Client(api_key=api_key)

    story_scenes = "\n".join(
        f"Scene {i + 1}: {scene}"
        for i, scene in enumerate(scenes)
    )

    instructions = f"""
You are an expert storyboard artist and visual director
for high-quality 3D animated short films.

Your task is to turn an Egyptian Arabic story into a sequence
of visually accurate image-generation prompts.

STORY TITLE:
{title}

COMPLETE STORY:
{story_scenes}

Create exactly {len(scenes)} image prompts.

CRITICAL STORY ACCURACY RULES:

1. Each prompt must illustrate the actual events of its
   corresponding scene.

2. Never use generic scene descriptions that could belong
   to any unrelated story.

3. Identify the characters actually present in each scene.

4. Describe what each character is physically doing.
   Show the specific action, not merely the character standing.

5. Describe facial expressions, emotions, body language,
   camera angle, environment, and relevant objects.

6. If a character discovers something, show the discovery.
   If characters argue, show the confrontation.
   If someone runs, show the movement.
   If a character feels sad, show the emotional situation.

7. Do not invent major events, characters, or objects
   that contradict the story.

CHARACTER CONSISTENCY:

8. Establish consistent visual designs for recurring characters.

9. Keep the same face, age, body proportions, hairstyle,
   clothing, and colors whenever a character reappears.

10. Include enough visual details in every prompt to help
    maintain character consistency across separate images.

VISUAL STYLE:

11. High-quality polished 3D animated movie aesthetic.
12. Expressive characters and natural body language.
13. Detailed environments appropriate to the actual story.
14. Cinematic composition and professional lighting.
15. Rich colors, depth, and soft realistic shadows.
16. Vertical portrait 9:16 composition.
17. Keep important characters and actions clearly visible.
18. No written text, subtitles, letters, logos, or watermarks.

IMPORTANT:

The image must communicate the main event of the scene
even without reading the story text.

Avoid unrelated Egyptian streets, random glowing objects,
random boxes, or generic dramatic scenes unless the actual
story specifically requires them.

Return ONLY valid JSON in this format:

{{
  "prompts": [
    "Detailed English image prompt for scene 1",
    "Detailed English image prompt for scene 2"
  ]
}}
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=instructions,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )

    try:
        result = json.loads(response.text)
        prompts = result["prompts"]

        if len(prompts) != len(scenes):
            raise ValueError(
                f"Expected {len(scenes)} prompts, "
                f"received {len(prompts)}."
            )

        if not all(
            isinstance(prompt, str) and prompt.strip()
            for prompt in prompts
        ):
            raise ValueError("A scene prompt is empty.")

        print("Gemini successfully analyzed the story.")

        for i, prompt in enumerate(prompts):
            print(f"Scene {i + 1} prompt: {prompt}")

        return prompts

    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Gemini returned invalid scene descriptions: {error}"
        ) from error


# =========================
# توليد الصور باستخدام Cloudflare
# =========================

def generate_image(prompt, index):
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not account_id or not api_token:
        raise RuntimeError(
            "تأكد من وجود CLOUDFLARE_ACCOUNT_ID "
            "وCLOUDFLARE_API_TOKEN في GitHub Secrets."
        )

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{account_id}/ai/run/"
        "@cf/bytedance/stable-diffusion-xl-lightning"
    )

    visual_prompt = (
        prompt
        + "\nHigh-quality 3D animated movie still, "
        "clear storytelling, coherent anatomy, "
        "consistent character appearance, "
        "portrait composition, no text."
    )

    payload = {
        "prompt": visual_prompt,
        "width": 576,
        "height": 1024,
        "num_steps": 4,
        "negative_prompt": (
            "blurry, low quality, distorted face, "
            "deformed anatomy, extra limbs, extra fingers, "
            "duplicate characters, incorrect objects, "
            "unrelated scene, text, letters, subtitles, watermark"
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
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Cloudflare image generation failed "
            f"(HTTP {error.code}): {error_text[:1500]}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"تعذر الاتصال بـ Cloudflare: {error.reason}"
        ) from error

    # بعض استجابات واجهات الصور قد تكون JSON بدل الصورة مباشرة
    content_type = ""

    try:
        content_type = response.headers.get("Content-Type", "")
    except Exception:
        pass

    if "application/json" in content_type:
        try:
            result = json.loads(image_bytes.decode("utf-8"))

            if not result.get("success", True):
                raise RuntimeError(
                    f"Cloudflare error: {result.get('errors')}"
                )

            image_data = result.get("result", {})

            if isinstance(image_data, dict):
                image_value = (
                    image_data.get("image")
                    or image_data.get("output")
                )

                if isinstance(image_value, list):
                    image_value = image_value[0] if image_value else None

                if isinstance(image_value, str):
                    image_bytes = base64.b64decode(image_value)
                else:
                    raise ValueError(
                        "لم يتم العثور على بيانات الصورة في الاستجابة."
                    )
            else:
                raise ValueError("تنسيق استجابة الصورة غير متوقع.")

        except Exception as error:
            raise RuntimeError(
                f"Cloudflare returned an invalid image response: {error}"
            ) from error

    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as error:
        raise RuntimeError(
            "Cloudflare لم يرجع صورة صالحة. "
            "راجع استجابة API وحدود الاستخدام."
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
        draw,
        title,
        title_font,
        W - 70,
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

    # لوحة النص
    draw.rounded_rectangle(
        (24, 865, W - 24, 1235),
        radius=30,
        fill=(0, 0, 0, 175),
        outline=(255, 255, 255, 90),
        width=2,
    )

    wrapped_text = wrap_arabic(
        draw,
        scene_text,
        font,
        W - 90,
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
        frame.convert("RGBA"),
        overlay,
    ).convert("RGB")


# =========================
# تنفيذ الفيديو
# =========================

def main():
    narration = " ".join(scenes)

    # إنشاء الصوت أولًا
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

    # توزيع مدة الفيديو حسب طول كل مشهد
    weights = [
        max(1, len(scene.split()))
        for scene in scenes
    ]

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

    # تحليل أحداث القصة وإنشاء وصف مخصص لكل مشهد
    print("Analyzing story scenes with Gemini...")

    scene_prompts = generate_scene_prompts(scenes, title)

    # توليد صورة مستقلة لكل مشهد باستخدام Cloudflare
    scene_images = []

    for index, prompt in enumerate(scene_prompts):
        path = generate_image(prompt, index)
        scene_images.append(path)

    # إنشاء الإطارات وحركة الكاميرا
    frame_number = 0
    previous_scene_frame = None
    transition_frames = max(1, FPS // 3)

    for scene_index, (scene_text, image_path, count) in enumerate(
        zip(scenes, scene_images, frame_counts)
    ):
        print(
            f"Rendering scene {scene_index + 1}/{len(scenes)}"
        )

        source = Image.open(image_path).convert("RGB")

        base = ImageOps.fit(
            source,
            (W, H),
            method=Image.Resampling.LANCZOS,
        )

        scene_last_frame = None

        for local_frame in range(count):
            progress = local_frame / max(1, count - 1)

            # تقريب تدريجي للكاميرا
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
