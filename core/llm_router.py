import logging
from enum import Enum
from core.system_prompts import (
    SIGNAL_EXTRACTION_PROMPT,
    MENTOR_PROMPT,
    CODEGEN_PROMPT,
    QUANT_FINANCE_PROMPT,
)

logger = logging.getLogger(__name__)


class RequestType(Enum):
    SIGNAL_EXTRACTION = "signal_extraction"
    MENTOR = "mentor"
    CODEGEN = "codegen"
    QUANT_FINANCE = "quant_finance"


# Keywords that identify quant finance questions
QUANT_KEYWORDS = [
    "itô", "ito", "stochastic", "brownian", "black-scholes", "black scholes",
    "derivative", "option pricing", "portfolio", "sharpe", "volatility surface",
    "monte carlo", "value at risk", "var", "greeks", "delta", "gamma", "vega",
    "theta", "rho", "hedging", "arbitrage", "martingale", "risk neutral",
    "yield curve", "duration", "convexity", "correlation", "covariance",
    "regression", "factor model", "capm", "efficient frontier", "markowitz",
]


def identify_request_type(text: str) -> RequestType:
    """
    Identifies what type of request this is based on keywords.
    Used to route to the correct system prompt and model config.
    """
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in QUANT_KEYWORDS):
        logger.info("Request identified as: QUANT_FINANCE")
        return RequestType.QUANT_FINANCE
    return RequestType.MENTOR


def get_system_prompt(request_type: RequestType) -> str:
    """Returns the appropriate system prompt for the request type."""
    prompts = {
        RequestType.SIGNAL_EXTRACTION: SIGNAL_EXTRACTION_PROMPT,
        RequestType.MENTOR: MENTOR_PROMPT,
        RequestType.CODEGEN: CODEGEN_PROMPT,
        RequestType.QUANT_FINANCE: QUANT_FINANCE_PROMPT,
    }
    return prompts[request_type]