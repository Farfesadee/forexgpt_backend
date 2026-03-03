
# """
# models/__init__.py — Central re-export point for all Pydantic models.

# Import from here for clean, consistent imports across the codebase:
#     from models import SignalExtractionRequest, BacktestRunRequest, QuantAskRequest
#     from models import UserProfile, MentorAskRequest, StrategyGenerateRequest

# Models are organised by module, matching the folder structure:
#     models/user.py          ← auth.py route
#     models/signal.py        ← signals.py route + signal_service.py
#     models/mentor.py        ← mentor.py route + mentor_service.py
#     models/quant_finance.py ← quant_finance.py route + quant_finance_service.py
#     models/strategy.py      ← codegen.py route + codegen_service.py
#     models/backtest.py      ← backtest.py route + backtest_service.py
# """

# # User / Auth 
# from models.user import (
#     ExperienceLevel,
#     RegisterRequest,
#     RegisterResponse,
#     LoginRequest,
#     LoginResponse,
#     RefreshRequest,
#     TokenPair,
#     LogoutResponse,
#     PasswordResetRequest,
#     PasswordUpdateRequest,
#     OAuthCallbackRequest,
#     ProfileUpdateRequest,
#     ProfileUpdateResponse,
#     UserProfile,
#     UserDashboard,
#     JWTPayload,
# )

# # Signals 
# from models.signal import (
#     Signal,
#     Direction,
#     Magnitude,
#     Time_Horizon,
#     HFExtractionRequest,
#     HFExtractionResponse,
#     ExtractedSignal,
#     ExtractionResult,
#     SignalExtractionRequest,
#     SignalUpdateRequest,
#     SignalFilterParams,
#     SignalResponse,
#     SignalListItem,
#     SignalListResponse,
# )

# # Mentor 
# from models.mentor import (
#     DifficultyLevel,
#     MessageRole,
#     ConversationCreate,
#     ConversationResponse,
#     ConversationListItem,
#     ConversationListResponse,
#     MentorAskRequest,
#     MentorMessageResponse,
#     MentorAskResponse,
#     MessageFeedbackRequest,
#     MessageHistoryResponse,
#     LLMMessage,
#     MentorLLMContext,
# )



# # Strategies
# from models.strategy import (
#     StrategyType,
#     ComplexityLevel,
#     Timeframe,
#     StrategyParameter,
#     StrategyGenerateRequest,
#     StrategyValidateRequest,
#     StrategyUpdateRequest,
#     SandboxResult,
#     StrategyResponse,
#     StrategyGenerateResponse,
#     StrategyValidateResponse,
#     StrategyListItem,
#     StrategyListResponse,
#     LeaderboardEntry,
#     LeaderboardResponse,
#     StrategyTemplate,
# )

# # Backtests 
# from models.backtest import (
#     BacktestStatus,
#     TradeDirection,
#     BacktestTimeframe,
#     TradingCosts,
#     BacktestMetrics,
#     EquityCurvePoint,
#     BacktestRunRequest,
#     BacktestFilterParams,
#     BacktestTrade,
#     BacktestResponse,
#     BacktestListItem,
#     BacktestListResponse,
#     BacktestTradeListResponse,
#     BacktestUpdateRequest,
#     MetricInterpretation,
#     BacktestInterpretation,
# )

# __all__ = [
#     # User
#     "ExperienceLevel", 
#     "RegisterRequest", "RegisterResponse",
#     "LoginRequest", "LoginResponse",
#     "RefreshRequest", "TokenPair", "LogoutResponse",
#     "PasswordResetRequest", "PasswordUpdateRequest", "OAuthCallbackRequest",
#     "ProfileUpdateRequest", "ProfileUpdateResponse",
#     "UserProfile", "UserDashboard", "JWTPayload",
#     # Signal
#     "SourceType", "Signal", "Direction", "Magnitude", "Time_Horizon",
#     "HFExtractionRequest", "HFExtractionResponse",
#     "ExtractedSignal", "ExtractionResult",
#     "SignalExtractionRequest", "SignalUpdateRequest", "SignalFilterParams",
#     "SignalResponse", "SignalListItem", "SignalListResponse",
#     # Mentor
#     "DifficultyLevel", "MessageRole",
#     "ConversationCreate", "ConversationResponse",
#     "ConversationListItem", "ConversationListResponse",
#     "MentorAskRequest", "MentorMessageResponse", "MentorAskResponse",
#     "MessageFeedbackRequest", "MessageHistoryResponse",
#     "LLMMessage", "MentorLLMContext",
#     # Quant Finance
#     "QuantDomain",
#     "QuantSessionCreate", "QuantSessionResponse",
#     "QuantSessionListItem", "QuantSessionListResponse", "QuantDomainStat",
#     "QuantAskRequest", "QuantMessageResponse", "QuantAskResponse",
#     "QuantMessageFeedbackRequest", "QuantMessageHistoryResponse",
#     "QuantLLMContext", "ParsedQuantResponse",
#     # Strategy
#     "StrategyType", "ComplexityLevel", "Timeframe", "StrategyParameter",
#     "StrategyGenerateRequest", "StrategyValidateRequest", "StrategyUpdateRequest",
#     "SandboxResult",
#     "StrategyResponse", "StrategyGenerateResponse", "StrategyValidateResponse",
#     "StrategyListItem", "StrategyListResponse",
#     "LeaderboardEntry", "LeaderboardResponse", "StrategyTemplate",
#     # Backtest
#     "BacktestStatus", "TradeDirection", "BacktestTimeframe",
#     "TradingCosts", "BacktestMetrics", "EquityCurvePoint",
#     "BacktestRunRequest", "BacktestFilterParams",
#     "BacktestTrade", "BacktestResponse",
#     "BacktestListItem", "BacktestListResponse",
#     "BacktestTradeListResponse", "BacktestUpdateRequest",
#     "MetricInterpretation", "BacktestInterpretation",
# ]