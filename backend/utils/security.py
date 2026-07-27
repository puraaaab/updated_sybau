import os
from pathlib import Path
from typing import Union
from fastapi import HTTPException

def safe_join_path(base_dir: Union[str, Path], *paths: str) -> str:
    """
    Safely joins paths ensuring that the resolved target path is strictly inside base_dir.
    Raises HTTPException 400/404 if path traversal is detected.
    """
    base_path = Path(base_dir).resolve()
    target_path = base_path.joinpath(*paths).resolve()
    
    # Check if target_path starts with base_path
    try:
        target_path.relative_to(base_path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path parameter or path traversal detected.")
    
    return str(target_path)
