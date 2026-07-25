import logging
import random

import cv2
import numpy as np
import torch
from PIL import Image

from ...config.service import get_models
from ..model_manager import model_manager

logger = logging.getLogger(__name__)

MOCK_DESCRIPTIONS = [
    "A person with a backpack walking slowly near the entrance.",
    "A white car entering the loading dock area.",
    "Two people chatting near the office doorway.",
    "A person carrying a cardboard box heading toward the exit.",
    "A blue sedan parked near the pedestrian walkway.",
    "An operator walking past the camera range."
]

CAPTION_PROMPT = "<MORE_DETAILED_CAPTION>"


def pre_warm():
    """
    Pre-load the Florence-2 model in the main thread at application startup.
    This avoids thread-safety issues with transformers' lazy module imports
    when the model is first needed inside a background worker thread.
    """
    cfg = get_models()
    if cfg.get("demo_mode", False):
        return  # No model to warm in demo mode
    try:
        logger.info("Pre-warming Florence-2 model at startup...")
        model_manager.get_florence()
        logger.info("Florence-2 model pre-warm complete.")
    except Exception:
        logger.exception(
            "Florence-2 pre-warm failed. Scene captioning will be skipped "
            "for frames until the model loads."
        )


def generate_scene_caption(frame: np.ndarray) -> str | None:
    """
    Generates a textual description of the frame using Florence-2.
    Returns None if captioning fails (caller should treat this as
    "no caption available for this frame", not a fatal error).
    """
    cfg = get_models()
    if cfg.get("demo_mode", False):
        # Return a random surveillance caption to simulate real-time scene understanding
        return random.choice(MOCK_DESCRIPTIONS)

    try:
        model, processor = model_manager.get_florence()

        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_image)

        inputs = processor(text=CAPTION_PROMPT, images=pil_img, return_tensors="pt")

        device = next(model.parameters()).device
        dtype = next(model.parameters()).dtype
        inputs = {k: v.to(device) for k, v in inputs.items()}
        if "pixel_values" in inputs:
            inputs["pixel_values"] = inputs["pixel_values"].to(dtype)

        with torch.inference_mode():
            generated_ids = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                early_stopping=False,
                do_sample=False,
                num_beams=3,
            )

        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
        return generated_text

    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        logger.error("Florence-2 captioning hit CUDA OOM; skipping this frame.")
        return None
    except Exception:
        logger.exception("Error executing Florence captioner")
        return None