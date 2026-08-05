import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

print("====================================================")
print("Warming up VMS AI models (Downloading weights)...")
print("====================================================")

print("\n[1/2] Loading SentenceTransformer (all-MiniLM-L6-v2)...")
try:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("-> SentenceTransformer loaded successfully!")
except Exception as e:
    print(f"Error loading SentenceTransformer: {e}")

print("\n[2/2] Loading Florence-2 (microsoft/Florence-2-base)...")
try:
    from transformers import AutoProcessor, AutoModelForCausalLM
    import torch
    import sys
    from unittest.mock import MagicMock
    if "flash_attn" not in sys.modules:
        mock = MagicMock()
        mock.__spec__ = MagicMock()
        sys.modules["flash_attn"] = mock
        sys.modules["flash_attn.bert_padding"] = mock
        sys.modules["flash_attn.flash_attn_interface"] = mock
        sys.modules["flash_attn.flash_attn_triton"] = mock

    print("-> Downloading processor config...")
    processor = AutoProcessor.from_pretrained("microsoft/Florence-2-base", trust_remote_code=True)
    print("-> Downloading model weights (~1.5GB)...")
    model = AutoModelForCausalLM.from_pretrained(
        "microsoft/Florence-2-base",
        trust_remote_code=True,
        torch_dtype=torch.float32
    )
    print("-> Florence-2 loaded successfully!")
except Exception as e:
    print(f"Error loading Florence-2: {e}")

print("\n====================================================")
print("All model weights are downloaded and warmed up!")
print("====================================================")
