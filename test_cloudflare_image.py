import os
import requests
from pathlib import Path

account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
api_token = os.environ["CLOUDFLARE_API_TOKEN"]

url = (
    "https://api.cloudflare.com/client/v4/accounts/"
    f"{account_id}/ai/run/@cf/bytedance/stable-diffusion-xl-lightning"
)

prompt = """
A cinematic high quality 3D cartoon scene, Egyptian teenage boy
standing in a narrow Cairo street at sunset, expressive face,
stylized animated movie character, beautiful detailed buildings,
dramatic cinematic lighting, depth of field, vibrant colors,
professional animation film quality, vertical composition,
no text, no letters, no watermark.
"""

print("Generating test image...")

response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    },
    json={
        "prompt": prompt,
        "width": 576,
        "height": 1024,
        "num_steps": 4,
        "negative_prompt": (
            "blurry, low quality, distorted face, extra fingers, "
            "text, watermark, duplicate characters"
        ),
    },
    timeout=240,
)

if not response.ok:
    raise RuntimeError(
        f"Cloudflare API error {response.status_code}: "
        f"{response.text[:1500]}"
    )

if not response.content.startswith(b"\xff\xd8"):
    raise RuntimeError(
        "The response does not appear to be a JPEG image. "
        f"Content-Type: {response.headers.get('Content-Type')}"
    )

output = Path("output")
output.mkdir(exist_ok=True)

image_path = output / "cloudflare-test.jpg"
image_path.write_bytes(response.content)

print(f"SUCCESS: Image saved to {image_path}")
print(f"Image size: {len(response.content)} bytes")
