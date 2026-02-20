from fastapi import FastAPI
from config import setup_logging
from routers.analyze import router as analyze_router
import logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="ForexGPT Backend")

# ✅ THIS LINE WAS MISSING
app.include_router(analyze_router)

@app.get("/health")
def health_check():
    logger.info("Health check endpoint called")
    return {"status": "running"}