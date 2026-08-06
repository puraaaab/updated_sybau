import urllib.parse
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..auth.helpers import verify_viewer
from ..utils.ssrf import validate_proxy_url

router = APIRouter(prefix="/proxy", tags=["Stream Proxy"])


@router.get("/m3u8")
async def proxy_m3u8(url: str, request: Request, user=Depends(verify_viewer)):
    validated_url = validate_proxy_url(url)
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as client:
        res = await client.get(validated_url, timeout=12)
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail="Failed to fetch manifest")

        base_url = str(request.base_url).rstrip("/")
        lines = res.text.split("\n")
        rewritten_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("http"):
                encoded = urllib.parse.quote_plus(stripped)
                if ".ts" in stripped or "seg.ts" in stripped:
                    rewritten_lines.append(f"{base_url}/api/v1/proxy/ts?url={encoded}")
                elif ".m3u8" in stripped:
                    rewritten_lines.append(f"{base_url}/api/v1/proxy/m3u8?url={encoded}")
                else:
                    rewritten_lines.append(f"{base_url}/api/v1/proxy/ts?url={encoded}")
            elif stripped and not stripped.startswith("#"):
                rewritten_lines.append(stripped)
            else:
                rewritten_lines.append(line)

        return Response(content="\n".join(rewritten_lines), media_type="application/vnd.apple.mpegurl")


@router.get("/ts")
async def proxy_ts(url: str, user=Depends(verify_viewer)):
    validated_url = validate_proxy_url(url)
    async def stream_ts():
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as client:
            async with client.stream("GET", validated_url, timeout=18) as r:
                async for chunk in r.aiter_bytes(chunk_size=32768):
                    yield chunk

    return StreamingResponse(stream_ts(), media_type="video/mp2t")
