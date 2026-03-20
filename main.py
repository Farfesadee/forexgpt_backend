
from fastapi import FastAPI, Depends
import uvicorn
import logging
from fastapi.middleware.cors import CORSMiddleware

from routes.mentor_routes import router as mentor_router   # ← new mentor router
from api.routes import auth, signals, codegen, backtest, news
from api.middleware.auth_middleware import get_current_user
from models.user import JWTPayload

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ForexGPT API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(mentor_router)   # new mentor — replaces api.routes.mentor
app.include_router(auth.router)
app.include_router(signals.router)
app.include_router(codegen.router)
app.include_router(backtest.router)
app.include_router(news.router)


@app.get("/health", tags=["Health"])
def health_check(_: JWTPayload = Depends(get_current_user)):
    logger.info("Health check called.")
    return {"status": "running"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)