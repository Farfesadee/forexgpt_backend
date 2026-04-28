import time

import pandas as pd
import pytest

from api.middleware import auth_middleware
from backtesting.data_fetcher import DataFetcher
from services.mentor_service import MentorService
from services.backtest_service import _build_strategy
from services.codegen_service import CodeGenService


class DummyCodeGenService(CodeGenService):
    def __init__(self):
        super().__init__(mistral_client=None)
        self.captured_kwargs = None

    async def generate_code(self, **kwargs):
        self.captured_kwargs = kwargs
        return kwargs


@pytest.mark.asyncio
async def test_generate_improvement_persists_clean_summary():
    service = DummyCodeGenService()

    result = await service.generate_improvement(
        user_id="user-123",
        original_code="def generate_signals(data):\n    return [0] * len(data)",
        backtest_results={
            "strategy_name": "custom",
            "pair": "EURUSD",
            "total_return_pct": -12.5,
        },
        mentor_analysis="Add a trend filter and stronger exits.",
        additional_requirements="Keep the strategy simple",
    )

    assert result["strategy_description"].startswith("Improve my custom strategy for EURUSD")
    assert "EXPERT ANALYSIS:" in result["llm_user_message"]
    assert result["stored_user_message"] == result["strategy_description"]
    assert result["stored_description"] == result["strategy_description"]
    assert "Add a trend filter" not in result["stored_description"]


def test_yfinance_auto_formats_unknown_forex_pair():
    fetcher = DataFetcher()
    assert fetcher._to_yfinance_ticker("GBPJPY") == "GBPJPY=X"
    assert fetcher._to_yfinance_ticker("EUR/USD") == "EURUSD=X"


def test_sma_defaults_can_trigger_with_documented_shorter_windows():
    strategy = _build_strategy("sma", {})
    data = pd.DataFrame(
        {
            "close": ([1.0] * 30) + [10.0],
        }
    )

    signal, reason = strategy(data)

    assert signal == "buy"
    assert "MA10" in reason
    assert "MA30" in reason


def test_sma_alias_params_are_respected():
    strategy = _build_strategy("moving_average_crossover", {"fast": 3, "slow": 5})
    data = pd.DataFrame(
        {
            "close": [1.0, 1.0, 1.0, 1.0, 1.0, 10.0],
        }
    )

    signal, reason = strategy(data)

    assert signal == "buy"
    assert "MA3" in reason
    assert "MA5" in reason


def test_sma_cross_alias_is_accepted():
    strategy = _build_strategy("sma_cross", {"fast": 3, "slow": 5})
    data = pd.DataFrame(
        {
            "close": [1.0, 1.0, 1.0, 1.0, 1.0, 10.0],
        }
    )

    signal, reason = strategy(data)

    assert signal == "buy"
    assert "MA3" in reason
    assert "MA5" in reason


def test_data_fetcher_auto_sources_skip_cooldown_and_missing_keys(monkeypatch):
    monkeypatch.setattr("backtesting.data_fetcher.settings.TWELVE_DATA_KEY", "td-key")
    monkeypatch.setattr("backtesting.data_fetcher.settings.ALPHA_VANTAGE_KEY", None)
    monkeypatch.setattr(DataFetcher, "_source_disabled_until", {"twelvedata": time.time() + 60})

    fetcher = DataFetcher()

    assert fetcher._get_auto_sources() == ["yfinance", "csv"]


def test_verify_jwt_prefers_jwks_when_secret_missing_for_asymmetric_tokens(monkeypatch):
    expected = auth_middleware.JWTPayload(
        sub="user-123",
        email="trader@example.com",
        role="authenticated",
        exp=9999999999,
        iat=1,
        aud="authenticated",
    )

    monkeypatch.setattr(auth_middleware.settings, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(auth_middleware.jwt, "get_unverified_header", lambda token: {"alg": "RS256"})
    monkeypatch.setattr(auth_middleware, "_verify_with_jwks", lambda token, alg: expected)

    def fail_introspection(token):
        raise AssertionError("Supabase introspection should not run for RS256 tokens when JWKS succeeds.")

    monkeypatch.setattr(auth_middleware, "_verify_with_supabase", fail_introspection)

    payload = auth_middleware._verify_jwt("fake-token")

    assert payload == expected


def test_verify_jwt_falls_back_to_supabase_when_jwks_fails_without_secret(monkeypatch):
    expected = auth_middleware.JWTPayload(
        sub="user-456",
        email="fallback@example.com",
        role="authenticated",
        exp=9999999999,
        iat=1,
        aud="authenticated",
    )

    monkeypatch.setattr(auth_middleware.settings, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(auth_middleware.jwt, "get_unverified_header", lambda token: {"alg": "RS256"})

    def fail_jwks(token, alg):
        raise auth_middleware.HTTPException(status_code=401, detail="jwks failed")

    monkeypatch.setattr(auth_middleware, "_verify_with_jwks", fail_jwks)
    monkeypatch.setattr(auth_middleware, "_verify_with_supabase", lambda token: expected)

    payload = auth_middleware._verify_jwt("fake-token")

    assert payload == expected


@pytest.mark.asyncio
async def test_ask_question_creates_missing_conversation_row_before_saving_messages(monkeypatch):
    class FakeMentorRepo:
        def __init__(self):
            self.created = []
            self.messages = []

        def create_conversation(self, id, user_id, title, signal_id=None):
            self.created.append(
                {
                    "id": id,
                    "user_id": user_id,
                    "title": title,
                    "signal_id": signal_id,
                }
            )

        def add_message(self, conversation_id, user_id, role, content, **meta):
            record = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                **meta,
            }
            self.messages.append(record)
            return record

    class FakeDB:
        def __init__(self):
            self.mentor = FakeMentorRepo()

    service = MentorService(mistral_client=None, db=FakeDB())

    monkeypatch.setattr(service, "_load_conversation", lambda conversation_id, user_id: ([], None))
    monkeypatch.setattr(service, "_conversation_exists", lambda conversation_id: False)

    async def fake_generate_response(messages, max_tokens=600):
        return "This is a complete mentor response used to validate message persistence."

    monkeypatch.setattr(service, "_generate_response", fake_generate_response)

    result = await service.ask_question(
        user_id="user-123",
        message="Explain RSI mean reversion",
        conversation_id="conv-123",
    )

    assert result["conversation_id"] == "conv-123"
    assert service.db.mentor.created == [
        {
            "id": "conv-123",
            "user_id": "user-123",
            "title": None,
            "signal_id": None,
        }
    ]
    assert [message["role"] for message in service.db.mentor.messages] == ["user", "assistant"]
