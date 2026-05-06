
from fastapi import FastAPI, Depends
import uvicorn
import logging
from fastapi.middleware.cors import CORSMiddleware

from routes.mentor_routes import router as mentor_router   # ← new mentor router
from api.routes import auth, signals, codegen, backtest, news
from api.middleware.auth_middleware import get_current_user
from api.middleware.error_handler import register_error_handlers
from models.user import JWTPayload
from core.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ForexGPT API",
    version="1.0.0",
    redirect_slashes=False
)

register_error_handlers(app)


def _build_allowed_origins() -> list[str]:
    origins = {
        settings.SITE_URL.rstrip("/"),
        "https://www.forexgpt.com.ng",
        "https://forexgpt.com.ng",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:8000",
    }
    return sorted(origin for origin in origins if origin)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers

app.include_router(auth.router)
app.include_router(mentor_router)   # new mentor — replaces api.routes.mentor
app.include_router(signals.router)
app.include_router(codegen.router)
app.include_router(backtest.router)
app.include_router(news.router)


# @app.on_event("startup")
# async def warmup_models():
#     """
#     Ping HuggingFace endpoints on startup to prevent cold start
#     delays for first users.
#     """
#     import httpx
#     import os

#     hf_token = os.getenv("HUGGING_FACE_TOKEN")
#     model_id  = os.getenv("SIGNAL_MODEL_ID", "mistral-small-latest")

#     try:
#         logger.info("Warming up HuggingFace endpoints...")
#         async with httpx.AsyncClient() as client:
#             await client.post(
#                 f"https://api-inference.huggingface.co/models/{model_id}",
#                 headers={"Authorization": f"Bearer {hf_token}"},
#                 json={"inputs": "warmup"},
#                 timeout=30.0
#             )
#         logger.info("HuggingFace warmup complete")
#     except Exception as e:
#         logger.warning(f"Warmup failed (non-critical): {e}")


@app.get("/health", tags=["Health"])
def health_check(_: JWTPayload = Depends(get_current_user)):
    logger.info("Health check called.")
    return {"status": "running"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
