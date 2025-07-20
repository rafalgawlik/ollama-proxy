import os
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI(title="Ollama API Proxy")

API_KEY = os.getenv("PROXY_API_KEY", "supersecret")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://you-ollama:11434")

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path in ["/docs", "/openapi.json", "/"]:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Authorization header is missing")
    
    try:
        auth_type, token = auth_header.split(" ")
        if auth_type.lower() != "bearer" or token != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API Key or format")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Authorization header format. Use 'Bearer <token>'.")

    response = await call_next(request)
    return response

@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_to_ollama(request: Request, full_path: str):
    async with httpx.AsyncClient(timeout=None) as client:
        url = httpx.URL(f"{OLLAMA_URL}/{full_path}", params=request.query_params)
        headers_to_forward = {k: v for k, v in request.headers.items() if k.lower() not in [
            'host', 'connection', 'keep-alive', 'proxy-authenticate', 
            'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade',
            'content-length'
        ]}

        proxy_request = client.build_request(
            method=request.method,
            url=url,
            headers=headers_to_forward,
            content=request.stream()
        )

        try:
            response_from_ollama = await client.send(proxy_request, stream=True)
        except httpx.ConnectError as e:
            raise HTTPException(status_code=502, detail=f"Cannot connect to Ollama service at {OLLAMA_URL}. Error: {e}")
        except httpx.ReadError as e:
            raise HTTPException(status_code=504, detail=f"Timeout or read error from Ollama service. Error: {e}")

        return StreamingResponse(
            response_from_ollama.aiter_bytes(),
            status_code=response_from_ollama.status_code,
            headers=response_from_ollama.headers,
            media_type=response_from_ollama.headers.get("content-type")
        )

@app.get("/")
def read_root():
    return {"message": "Ollama API Proxy is running. Authenticate with 'Bearer <API_KEY>' to use."}