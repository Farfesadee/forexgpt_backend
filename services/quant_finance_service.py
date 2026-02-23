import logging
from core.hf_client import hf_client
from core.llm_router import RequestType, get_system_prompt
from core.database import get_supabase

logger = logging.getLogger(__name__)

# ─── 50 Quant Finance Topics ─────────────────────────────────

QUANT_TOPICS = [
    # Beginner
    {"id": "time_value_money", "title": "Time Value of Money", "difficulty": "beginner", "category": "Fundamentals", "description": "The concept that money available now is worth more than the same amount in the future."},
    {"id": "risk_return", "title": "Risk and Return", "difficulty": "beginner", "category": "Fundamentals", "description": "The tradeoff between the potential return on an investment and its risk."},
    {"id": "diversification", "title": "Diversification", "difficulty": "beginner", "category": "Portfolio Theory", "description": "Spreading investments to reduce exposure to any single asset."},
    {"id": "compound_interest", "title": "Compound Interest", "difficulty": "beginner", "category": "Fundamentals", "description": "Interest calculated on both principal and accumulated interest."},
    {"id": "present_value", "title": "Present Value & Discounting", "difficulty": "beginner", "category": "Fundamentals", "description": "Calculating the current worth of future cash flows."},
    {"id": "yield_curve", "title": "Yield Curve", "difficulty": "beginner", "category": "Fixed Income", "description": "A graph showing interest rates across different maturities."},
    {"id": "correlation", "title": "Correlation & Covariance", "difficulty": "beginner", "category": "Statistics", "description": "Measuring the relationship between two variables."},
    {"id": "normal_distribution", "title": "Normal Distribution", "difficulty": "beginner", "category": "Statistics", "description": "The bell curve distribution fundamental to finance models."},
    {"id": "expected_value", "title": "Expected Value", "difficulty": "beginner", "category": "Statistics", "description": "The probability-weighted average of all possible outcomes."},
    {"id": "leverage", "title": "Leverage & Margin", "difficulty": "beginner", "category": "Fundamentals", "description": "Using borrowed capital to amplify potential returns."},

    # Intermediate
    {"id": "capm", "title": "CAPM", "difficulty": "intermediate", "category": "Portfolio Theory", "description": "Capital Asset Pricing Model — relates expected return to systematic risk."},
    {"id": "sharpe_ratio", "title": "Sharpe Ratio", "difficulty": "intermediate", "category": "Portfolio Theory", "description": "Risk-adjusted return metric dividing excess return by standard deviation."},
    {"id": "markowitz", "title": "Markowitz Portfolio Theory", "difficulty": "intermediate", "category": "Portfolio Theory", "description": "Mean-variance optimization framework for portfolio construction."},
    {"id": "efficient_frontier", "title": "Efficient Frontier", "difficulty": "intermediate", "category": "Portfolio Theory", "description": "Set of optimal portfolios offering highest return for each risk level."},
    {"id": "var", "title": "Value at Risk (VaR)", "difficulty": "intermediate", "category": "Risk Management", "description": "Maximum expected loss at a given confidence level over a time period."},
    {"id": "monte_carlo", "title": "Monte Carlo Simulation", "difficulty": "intermediate", "category": "Quantitative Methods", "description": "Using random sampling to model probability distributions of outcomes."},
    {"id": "regression", "title": "Linear Regression", "difficulty": "intermediate", "category": "Statistics", "description": "Modeling the relationship between dependent and independent variables."},
    {"id": "factor_models", "title": "Factor Models", "difficulty": "intermediate", "category": "Portfolio Theory", "description": "Explaining asset returns using common risk factors."},
    {"id": "duration", "title": "Duration & Convexity", "difficulty": "intermediate", "category": "Fixed Income", "description": "Measuring bond price sensitivity to interest rate changes."},
    {"id": "options_basics", "title": "Options Basics", "difficulty": "intermediate", "category": "Derivatives", "description": "Calls, puts, strikes, expiry, and basic payoff structures."},
    {"id": "futures_forwards", "title": "Futures & Forwards", "difficulty": "intermediate", "category": "Derivatives", "description": "Contracts to buy/sell assets at predetermined future prices."},
    {"id": "hedging", "title": "Hedging Strategies", "difficulty": "intermediate", "category": "Risk Management", "description": "Using financial instruments to offset potential losses."},
    {"id": "volatility", "title": "Volatility Measurement", "difficulty": "intermediate", "category": "Risk Management", "description": "Historical vs implied volatility and their uses."},
    {"id": "arbitrage", "title": "Arbitrage", "difficulty": "intermediate", "category": "Fundamentals", "description": "Exploiting price differences for risk-free profit."},
    {"id": "carry_trade", "title": "Carry Trade", "difficulty": "intermediate", "category": "Forex", "description": "Borrowing in low-rate currencies to invest in high-rate ones."},

    # Advanced
    {"id": "black_scholes", "title": "Black-Scholes Model", "difficulty": "advanced", "category": "Derivatives", "description": "Mathematical model for pricing European options."},
    {"id": "greeks", "title": "The Greeks", "difficulty": "advanced", "category": "Derivatives", "description": "Delta, gamma, theta, vega, rho — option price sensitivities."},
    {"id": "stochastic_calculus", "title": "Stochastic Calculus", "difficulty": "advanced", "category": "Mathematical Finance", "description": "Calculus for systems with random components — foundation of quant finance."},
    {"id": "ito_lemma", "title": "Itô's Lemma", "difficulty": "advanced", "category": "Mathematical Finance", "description": "The chain rule for stochastic processes — central to derivatives pricing."},
    {"id": "brownian_motion", "title": "Brownian Motion", "difficulty": "advanced", "category": "Mathematical Finance", "description": "Continuous-time random process used to model asset price movements."},
    {"id": "risk_neutral", "title": "Risk-Neutral Pricing", "difficulty": "advanced", "category": "Derivatives", "description": "Pricing derivatives using risk-neutral probability measures."},
    {"id": "martingale", "title": "Martingale Theory", "difficulty": "advanced", "category": "Mathematical Finance", "description": "A stochastic process where expected future value equals current value."},
    {"id": "volatility_surface", "title": "Volatility Surface", "difficulty": "advanced", "category": "Derivatives", "description": "3D representation of implied volatility across strikes and maturities."},
    {"id": "term_structure", "title": "Term Structure Models", "difficulty": "advanced", "category": "Fixed Income", "description": "Models for the evolution of interest rates over time."},
    {"id": "cvar", "title": "Conditional VaR (CVaR)", "difficulty": "advanced", "category": "Risk Management", "description": "Expected loss given that loss exceeds VaR — also called Expected Shortfall."},
    {"id": "copulas", "title": "Copulas", "difficulty": "advanced", "category": "Statistics", "description": "Functions for modeling dependency structures between variables."},
    {"id": "jump_diffusion", "title": "Jump-Diffusion Models", "difficulty": "advanced", "category": "Mathematical Finance", "description": "Asset price models incorporating sudden jumps alongside continuous diffusion."},
    {"id": "heston_model", "title": "Heston Model", "difficulty": "advanced", "category": "Derivatives", "description": "Stochastic volatility model for option pricing."},
    {"id": "pca", "title": "PCA in Finance", "difficulty": "advanced", "category": "Quantitative Methods", "description": "Principal Component Analysis for yield curves and factor extraction."},
    {"id": "pairs_trading", "title": "Pairs Trading & Cointegration", "difficulty": "advanced", "category": "Quantitative Methods", "description": "Statistical arbitrage strategy based on cointegrated asset pairs."},
    {"id": "kalman_filter", "title": "Kalman Filter", "difficulty": "advanced", "category": "Quantitative Methods", "description": "Recursive algorithm for estimating hidden states in financial time series."},
    {"id": "regime_switching", "title": "Regime-Switching Models", "difficulty": "advanced", "category": "Quantitative Methods", "description": "Models where parameters switch between different market regimes."},
    {"id": "garch", "title": "GARCH Models", "difficulty": "advanced", "category": "Statistics", "description": "Generalized AutoRegressive Conditional Heteroskedasticity for volatility modeling."},
    {"id": "optimal_execution", "title": "Optimal Execution", "difficulty": "advanced", "category": "Market Microstructure", "description": "Minimizing market impact when trading large orders."},
    {"id": "market_microstructure", "title": "Market Microstructure", "difficulty": "advanced", "category": "Market Microstructure", "description": "How trading mechanisms affect price formation and liquidity."},
    {"id": "high_freq", "title": "High-Frequency Trading", "difficulty": "advanced", "category": "Market Microstructure", "description": "Algorithmic trading at very high speeds using quantitative strategies."},
    {"id": "ml_in_finance", "title": "Machine Learning in Finance", "difficulty": "advanced", "category": "Quantitative Methods", "description": "Applications of ML to prediction, risk, and portfolio management."},
    {"id": "reinforcement_learning", "title": "Reinforcement Learning for Trading", "difficulty": "advanced", "category": "Quantitative Methods", "description": "Training agents to make trading decisions through reward-based learning."},
    {"id": "crypto_quant", "title": "Crypto Quantitative Finance", "difficulty": "advanced", "category": "Forex", "description": "Applying quant methods to cryptocurrency markets."},
]


def search_topics(query: str) -> list[dict]:
    """Search topics by title, category, or description."""
    query_lower = query.lower()
    return [
        t for t in QUANT_TOPICS
        if query_lower in t["title"].lower()
        or query_lower in t["category"].lower()
        or query_lower in t["description"].lower()
    ]


def get_topic(topic_id: str) -> dict | None:
    """Get a single topic by ID."""
    return next((t for t in QUANT_TOPICS if t["id"] == topic_id), None)


def get_related_topics(topic_id: str) -> list[dict]:
    """Get topics in the same category, excluding the current one."""
    topic = get_topic(topic_id)
    if not topic:
        return []
    return [
        t for t in QUANT_TOPICS
        if t["category"] == topic["category"] and t["id"] != topic_id
    ][:5]


async def ask_quant(
    question: str,
    topic_id: str | None,
    conversation_history: list[dict] | None,
    user_id: str | None,
) -> dict:
    """
    Answers a quantitative finance question using base Mistral
    with the quant finance system prompt.
    Saves the conversation to Supabase if user is authenticated.
    """
    from core.system_prompts import QUANT_FINANCE_PROMPT

    # Build message with optional topic context
    user_message = question
    if topic_id:
        topic = get_topic(topic_id)
        if topic:
            user_message = (
                f"Topic: {topic['title']}\n"
                f"Context: {topic['description']}\n\n"
                f"Question: {question}"
            )

    # Include conversation history if provided
    if conversation_history:
        history_text = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}"
            for msg in conversation_history[-4:]  # Last 4 exchanges
        ])
        user_message = f"Previous conversation:\n{history_text}\n\nNew question: {question}"

    try:
        answer = await hf_client.call_base_model(QUANT_FINANCE_PROMPT, user_message)
        logger.info("Quant finance response generated.")
    except Exception as e:
        logger.error(f"Quant finance HF call failed: {e}")
        answer = "I'm sorry, I couldn't process your question right now. Please try again."

    # Get related topics
    related = get_related_topics(topic_id) if topic_id else []
    related_ids = [t["id"] for t in related]

    # Save to Supabase
    conversation_id = None
    if user_id:
        try:
            db = get_supabase()
            record = db.table("conversations").insert({
                "user_id": user_id,
                "question": question,
                "answer": answer,
                "type": "quant_finance",
            }).execute()
            conversation_id = record.data[0]["id"]
        except Exception as e:
            logger.warning(f"Could not save quant conversation to DB: {e}")

    return {
        "answer": answer,
        "topic_id": topic_id,
        "related_topics": related_ids,
        "conversation_id": conversation_id,
    }