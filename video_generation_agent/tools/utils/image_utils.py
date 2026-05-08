import os
import io
import base64
import logging
from pathlib import Path
import asyncio
from PIL import Image

from workspace_context import get_artifact_root

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash-image"

def get_default_images_dir() -> str:
    images_dir = get_artifact_root() / "generated_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return str(images_dir)


IMAGES_DIR = get_default_images_dir()

OUTPUT_FORMAT = "png"


def get_images_dir(product_name: str) -> str:
    """Return (and create) the images directory for a specific product."""
    images_dir = get_artifact_root() / product_name / "generated_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return str(images_dir)


def create_filename(file_name, variant_num, num_variants, output_format):
    if num_variants == 1:
        image_name = file_name
    else:
        image_name = f"{file_name}_variant_{variant_num}"
    filename = f"{image_name}.{output_format}"
    return image_name, filename


def load_image_by_name(image_name, images_dir, extensions=None):
    """Load an image by name, trying common extensions in order."""
    if extensions is None:
        extensions = ['.png', '.jpg', '.jpeg', '.webp']

    for ext in extensions:
        potential_path = os.path.join(images_dir, f"{image_name}{ext}")
        if os.path.exists(potential_path):
            try:
                image = Image.open(potential_path)
                return image, potential_path, None
            except Exception as e:
                return None, None, f"Error loading image {potential_path}: {str(e)}"

    return None, None, f"Error: Image file not found: {image_name} (tried {', '.join(extensions)})"


def extract_image_from_response(response):
    """Extract the first image and any text from a Gemini API response."""
    image = None
    text_output = ""

    for part in response.candidates[0].content.parts:
        if part.text is not None:
            text_output += part.text
        elif part.inline_data is not None:
            image = Image.open(io.BytesIO(part.inline_data.data))

    return image, text_output


def extract_image_parts_from_response(response):
    """Extract raw image bytes from a Gemini API response."""
    return [
        part.inline_data.data
        for part in response.candidates[0].content.parts
        if part.inline_data
    ]


def extract_usage_metadata(response):
    usage_metadata = getattr(response, "usage_metadata", {}) or {}
    if usage_metadata and not isinstance(usage_metadata, dict):
        if hasattr(usage_metadata, "model_dump"):
            usage_metadata = usage_metadata.model_dump()
        elif hasattr(usage_metadata, "__dict__"):
            usage_metadata = vars(usage_metadata)
        else:
            try:
                usage_metadata = dict(usage_metadata)
            except (TypeError, ValueError):
                usage_metadata = {}
    return usage_metadata


def split_results_and_usage(raw_results):
    results = []
    total_prompt_tokens = 0.0
    total_candidate_tokens = 0.0

    for item in raw_results:
        result = dict(item)
        total_prompt_tokens += float(result.pop("prompt_tokens", 0.0) or 0.0)
        total_candidate_tokens += float(result.pop("candidate_tokens", 0.0) or 0.0)
        results.append(result)

    usage_metadata = {
        "prompt_token_count": total_prompt_tokens,
        "candidates_token_count": total_candidate_tokens,
    }
    return results, usage_metadata


def process_variant_result(variant_num, image, file_name, num_variants, compress_func, images_dir=None):
    """Save a variant image and return its result dict."""
    save_dir = images_dir if images_dir is not None else get_default_images_dir()
    image_name, filename = create_filename(file_name, variant_num, num_variants, OUTPUT_FORMAT)
    filepath = os.path.join(save_dir, filename)
    image.save(filepath, OUTPUT_FORMAT)
    compressed_b64 = compress_func(image)
    return {
        "variant": variant_num,
        "file_path": filepath,
        "image_name": image_name,
        "base64": compressed_b64,
    }


async def run_parallel_variants(variant_func, num_variants):
    """Run variant_func for each variant concurrently in a thread pool."""
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, variant_func, i + 1) for i in range(num_variants)]
    completed = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in completed if r is not None and not isinstance(r, Exception)]


def compress_image_for_base64(image: Image.Image, max_size: int = 1024) -> str:
    """Resize and JPEG-compress an image, returning a base64-encoded string."""
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    width, height = image.size
    if max(width, height) > max_size:
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


def combine_image_parts(image_parts):
    """Combine multiple raw image parts into a single horizontally-stitched image."""
    if not image_parts:
        return None

    images = [Image.open(io.BytesIO(part)) for part in image_parts]

    if len(images) == 1:
        return images[0]

    total_width = sum(img.width for img in images)
    max_height = max(img.height for img in images)
    combined = Image.new('RGB', (total_width, max_height))

    x_offset = 0
    for img in images:
        combined.paste(img, (x_offset, 0))
        x_offset += img.width

    return combined
