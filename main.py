import logging
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

# from config import setup_logging
from api.routes import auth, signals, mentor, codegen, backtest, news
from api.middleware.auth_middleware import get_current_user
from models.user import JWTPayload
# from api.routes import quant_finance 

# setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ForexGPT API",
    description="Backend for ForexGPT — signal extraction, mentor, code generation, and backtesting.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(signals.router)
app.include_router(mentor.router)
app.include_router(codegen.router)
app.include_router(backtest.router)
app.include_router(news.router)
# app.include_router(quant_finance.router)


@app.get("/health", tags=["Health"])
def health_check(_: JWTPayload = Depends(get_current_user)):
    logger.info("Health check called.")
    return {"status": "running"}






