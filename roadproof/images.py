"""Validate uploads and create explicitly synthetic road illustrations."""
from io import BytesIO
from pathlib import Path
import uuid
import warnings

from PIL import Image, ImageDraw, ImageFont, ImageOps

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def clean_image(raw: bytes) -> bytes:
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("Choose a JPG or PNG image smaller than 10 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise ValueError("Only genuine JPG and PNG images are supported.")
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("Choose an image smaller than 24 megapixels.")
                source.load()
                result = ImageOps.exif_transpose(source).convert("RGB")
                result.thumbnail((1800, 1800))
                output = BytesIO()
                result.save(output, format="JPEG", quality=88)
                return output.getvalue()
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("This image could not be read safely. Try a different JPG or PNG.") from exc


def save_image(raw: bytes, directory: Path) -> str:
    cleaned = clean_image(raw)
    from .settings import backend_settings
    settings = backend_settings()
    if settings.backend == "supabase":
        from .cloud import PrivateStorage
        return PrivateStorage(settings).upload(cleaned)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}.jpg"
    path.write_bytes(cleaned)
    return str(path.resolve())


def read_image(reference):
    if not reference:
        return None
    if str(reference).startswith("supabase://"):
        from .cloud import PrivateStorage
        return PrivateStorage().download(reference)
    path = Path(reference)
    return path.read_bytes() if path.is_file() else None


def remove_image(reference):
    if str(reference).startswith("supabase://"):
        from .cloud import PrivateStorage
        PrivateStorage().remove(reference)
    else:
        Path(reference).unlink(missing_ok=True)


def road_illustration(repaired: bool = False) -> bytes:
    image = Image.new("RGB", (1200, 740), "#252729")
    draw = ImageDraw.Draw(image)
    for y in range(0, 740, 32):
        draw.line((0, y, 1200, y + 170), fill="#2b2d2f", width=1)
    draw.polygon([(150, 740), (390, 0), (810, 0), (1100, 740)], fill="#353739")
    draw.line((150, 740, 390, 0), fill="#777776", width=5)
    draw.line((1100, 740, 810, 0), fill="#777776", width=5)
    for y in range(30, 740, 150):
        draw.rectangle((590, y, 603, y + 75), fill="#c8c5b9")
    outline = [(720, 350), (835, 315), (930, 380), (943, 483), (852, 549), (732, 508), (682, 421)]
    draw.polygon(outline, fill="#444847" if repaired else "#17191a")
    draw.line(outline + [outline[0]], fill="#16834A" if repaired else "#FF5A1F", width=6)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 22)
        large = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 30)
    except OSError:
        font = ImageFont.load_default(size=22)
        large = ImageFont.load_default(size=30)
    draw.rectangle((36, 36, 620, 88), fill="#111111")
    draw.text((52, 48), "SYNTHETIC DEMONSTRATION / NOT A PHOTO", font=font, fill="#ffffff")
    draw.text((48, 638), "ROADPROOF / EVIDENCE WORKSPACE", font=large, fill="#ffffff")
    draw.text((48, 688), "ILLUSTRATIVE REPAIR" if repaired else "ILLUSTRATIVE ROAD DAMAGE", font=font, fill="#ff794b")
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()
