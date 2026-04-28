# """
# Signal Extraction Service - Forex Signal Detection from Earnings Transcripts
# Uses fine-tuned Mistral model to extract currency exposure signals
# """

# import uuid
# import json
# from datetime import datetime
# from typing import Dict, List, Optional
# import logging
# import asyncio

# logger = logging.getLogger(__name__)


# class SignalService:
#     """
#     Service for extracting forex trading signals from earnings call transcripts.
#     Uses the fine-tuned ForexGPT model.
#     """
    
#     def __init__(self, hf_client, db, model_id: str = "forexgpt/mistral-7b-forex-signals"):
#         """
#         Initialize signal extraction service
        
#         Args:
#             hf_client: Hugging Face inference client
#             db: Database connection (Supabase or similar)
#             model_id: Hugging Face model ID for fine-tuned model
#         """
#         self.hf_client = hf_client
#         self.db = db
#         self.model_id = model_id
        
#         # System prompt for signal extraction
#         self.system_prompt = """You are ForexGPT, a specialized AI assistant for extracting forex trading signals from corporate earnings call transcripts.

# When given an earnings transcript excerpt, you analyze it for currency exposure information and return a structured JSON response with the following fields:
# - signal (boolean): Whether a valid forex signal exists
# - currency_pair (string or null): The currency pair (e.g., "EUR/USD"), or null if not specified
# - direction (string or null): Trading direction - "LONG", "SHORT", "NEUTRAL", or null if unclear
# - confidence (float or null): Confidence score between 0.0 and 1.0, or null if not determinable
# - reasoning (string): Clear explanation of why this signal exists
# - magnitude (string or null): Impact level - "low", "moderate", "high", or null
# - time_horizon (string or null): Expected timeframe - "current_quarter", "long_term", "next_quarter", "full_term", "short_term", "full_year" or null

# Only extract signals when there is clear forex exposure mentioned. Be conservative with confidence scores."""
    
#     async def extract_signal(
#         self,
#         user_id: str,
#         transcript: str,
#         company_name: Optional[str] = None,
#         save_to_db: bool = True
#     ) -> Dict:
#         """
#         Extract forex signal from earnings transcript
        
#         Args:
#             user_id: User's unique identifier
#             transcript: Earnings call transcript or excerpt
#             company_name: Optional company name for context
#             save_to_db: Whether to save signal to database
            
#         Returns:
#             Dict containing:
#                 - signal: Whether a signal exists
#                 - currency_pair: Currency pair (e.g., "EUR/USD")
#                 - direction: LONG/SHORT/NEUTRAL
#                 - confidence: 0.0 to 1.0
#                 - reasoning: Explanation
#                 - magnitude: low/moderate/high
#                 - time_horizon: Timeframe
#                 - raw_response: Full model output
#                 - signal_id: Database ID if saved
#         """
#         try:
#             logger.info(f"Extracting signal for user {user_id}")
            
#             # Build prompt
#             user_message = self._build_extraction_prompt(transcript, company_name)
            
#             messages = [
#                 {"role": "system", "content": self.system_prompt},
#                 {"role": "user", "content": user_message}
#             ]
            
#             # Call fine-tuned model
#             logger.info(f"Calling fine-tuned model {self.model_id}")
#             raw_response = await self._generate_signal(messages)
            
#             # Parse JSON response
#             signal_data = self._parse_signal_response(raw_response)
            
#             # Add metadata
#             signal_data["raw_response"] = raw_response
#             signal_data["company_name"] = company_name
#             signal_data["timestamp"] = datetime.utcnow().isoformat()
            
#             # Save to database if requested
#             if save_to_db and signal_data["signal"]:
#                 signal_id = await self._save_signal(user_id, signal_data, transcript)
#                 signal_data["signal_id"] = signal_id
            
#             logger.info(f"Successfully extracted signal: {signal_data['signal']}")
            
#             return signal_data
            
#         except Exception as e:
#             logger.error(f"Error extracting signal: {str(e)}", exc_info=True)
#             raise
    
#     async def batch_extract_signals(
#         self,
#         user_id: str,
#         transcripts: List[Dict],
#         save_to_db: bool = True
#     ) -> List[Dict]:
#         """
#         Extract signals from multiple transcripts
        
#         Args:
#             user_id: User's unique identifier
#             transcripts: List of dicts with 'text' and optional 'company_name'
#             save_to_db: Whether to save signals to database
            
#         Returns:
#             List of extracted signals
#         """
#         signals = []
        
#         for transcript in transcripts:
#             try:
#                 signal = await self.extract_signal(
#                     user_id=user_id,
#                     transcript=transcript["text"],
#                     company_name=transcript.get("company_name"),
#                     save_to_db=save_to_db
#                 )
#                 signals.append(signal)
                
#             except Exception as e:
#                 logger.error(f"Error processing transcript: {str(e)}")
#                 signals.append({
#                     "signal": False,
#                     "error": str(e),
#                     "company_name": transcript.get("company_name")
#                 })
        
#         return signals
    
#     async def get_user_signals(
#         self,
#         user_id: str,
#         limit: int = 50,
#         currency_pair: Optional[str] = None,
#         direction: Optional[str] = None
#     ) -> List[Dict]:
#         """
#         Retrieve user's saved signals with optional filters
        
#         Args:
#             user_id: User's unique identifier
#             limit: Maximum number of signals to return
#             currency_pair: Optional filter by currency pair
#             direction: Optional filter by direction (LONG/SHORT/NEUTRAL)
            
#         Returns:
#             List of signals
#         """
#         try:
#             query = self.db.from_("signals") \
#                 .select("*") \
#                 .eq("user_id", user_id) \
#                 .order("created_at", desc=True) \
#                 .limit(limit)
            
#             if currency_pair:
#                 query = query.eq("currency_pair", currency_pair)
            
#             if direction:
#                 query = query.eq("direction", direction)
            
#             result = await query.execute()
            
#             return [
#                 {
#                     "signal_id": row["id"],
#                     "currency_pair": row["currency_pair"],
#                     "direction": row["direction"],
#                     "confidence": row["confidence"],
#                     "reasoning": row["reasoning"],
#                     "magnitude": row["magnitude"],
#                     "time_horizon": row["time_horizon"],
#                     "company_name": row.get("company_name"),
#                     "created_at": row["created_at"]
#                 }
#                 for row in result.data
#             ]
            
#         except Exception as e:
#             logger.error(f"Error retrieving signals: {str(e)}", exc_info=True)
#             raise
    
#     async def get_signal_by_id(
#         self,
#         signal_id: str,
#         user_id: str
#     ) -> Optional[Dict]:
#         """
#         Retrieve a specific signal
        
#         Args:
#             signal_id: Signal ID
#             user_id: User ID (for authorization)
            
#         Returns:
#             Signal details or None if not found
#         """
#         try:
#             result = await self.db.from_("signals") \
#                 .select("*") \
#                 .eq("id", signal_id) \
#                 .eq("user_id", user_id) \
#                 .limit(1) \
#                 .execute()
            
#             if not result.data:
#                 return None
            
#             row = result.data[0]    # access first item from list

#             # return {
#             #     "signal_id": result.data["id"],
#             #     "currency_pair": result.data["currency_pair"],
#             #     "direction": result.data["direction"],
#             #     "confidence": result.data["confidence"],
#             #     "reasoning": result.data["reasoning"],
#             #     "magnitude": result.data["magnitude"],
#             #     "time_horizon": result.data["time_horizon"],
#             #     "company_name": result.data.get("company_name"),
#             #     "transcript_excerpt": result.data.get("transcript_excerpt"),
#             #     "created_at": result.data["created_at"]
#             # }
#             return {
#                 "signal_id": row["id"],
#                 "currency_pair": row["currency_pair"],
#                 "direction": row["direction"],
#                 "confidence": row["confidence"],
#                 "reasoning": row["reasoning"],
#                 "magnitude": row["magnitude"],
#                 "time_horizon": row["time_horizon"],
#                 "company_name": row.get("company_name"),
#                 "transcript_excerpt": row.get("transcript_excerpt"),
#                 "created_at": row["created_at"]
#             }
            
#         except Exception as e:
#             logger.error(f"Error retrieving signal: {str(e)}", exc_info=True)
#             raise
    
#     async def delete_signal(
#         self,
#         signal_id: str,
#         user_id: str
#     ) -> bool:
#         """
#         Delete a signal
        
#         Args:
#             signal_id: Signal to delete
#             user_id: User ID (for authorization)
            
#         Returns:
#             True if deleted, False if not found
#         """
#         try:
#             check = await self.db.from_("signals") \
#                 .select("id") \
#                 .eq("id", signal_id) \
#                 .eq("user_id", user_id) \
#                 .limit(1) \
#                 .execute()

#             if not check.data:
#                 logger.warning(f"Signal {signal_id} not found or unauthorized")
#                 return False
            
#             await self.db.from_("signals") \
#                 .delete() \
#                 .eq("id", signal_id) \
#                 .eq("user_id", user_id) \
#                 .execute()
            
#             # return len(result.data) > 0
#             logger.info(f"Deleted signal {signal_id}")
#             return True
            
#         except Exception as e:
#             logger.error(f"Error deleting signal: {str(e)}", exc_info=True)
#             raise
    
#     async def get_signal_statistics(self, user_id: str) -> Dict:
#         """
#         Get statistics on user's signals
        
#         Args:
#             user_id: User's unique identifier
            
#         Returns:
#             Dict with signal statistics
#         """
#         try:
#             # Get all user signals
#             result = await self.db.from_("signals") \
#                 .select("currency_pair, direction, confidence, magnitude") \
#                 .eq("user_id", user_id) \
#                 .execute()
            
#             if not result.data:
#                 return {
#                     "total_signals": 0,
#                     "by_currency_pair": {},
#                     "by_direction": {},
#                     "by_magnitude": {},
#                     "average_confidence": 0
#                 }
            
#             signals = result.data
            
#             # Calculate statistics
#             # Filter out None values for confidence calculation
#             confidences = [s["confidence"] for s in signals if s["confidence"] is not None]
#             avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
#             stats = {
#                 "total_signals": len(signals),
#                 "by_currency_pair": {},
#                 "by_direction": {"LONG": 0, "SHORT": 0, "NEUTRAL": 0, "UNKNOWN": 0},
#                 "by_magnitude": {"low": 0, "moderate": 0, "high": 0, "UNKNOWN": 0},
#                 "average_confidence": avg_confidence
#             }
            
#             # Count by categories
#             for signal in signals:
#                 # Currency pair (including None)
#                 pair = signal["currency_pair"] if signal["currency_pair"] else "UNKNOWN"
#                 stats["by_currency_pair"][pair] = stats["by_currency_pair"].get(pair, 0) + 1
                
#                 # Direction (including None)
#                 direction = signal["direction"] if signal["direction"] else "UNKNOWN"
#                 if direction in stats["by_direction"]:
#                     stats["by_direction"][direction] += 1
#                 else:
#                     stats["by_direction"]["UNKNOWN"] += 1
                
#                 # Magnitude (including None)
#                 magnitude = signal["magnitude"] if signal["magnitude"] else "UNKNOWN"
#                 if magnitude in stats["by_magnitude"]:
#                     stats["by_magnitude"][magnitude] += 1
#                 else:
#                     stats["by_magnitude"]["UNKNOWN"] += 1
            
#             return stats
            
#         except Exception as e:
#             logger.error(f"Error calculating statistics: {str(e)}", exc_info=True)
#             raise
    
#     # ========================================================================
#     # PRIVATE HELPER METHODS
#     # ========================================================================
    
#     def _build_extraction_prompt(
#         self,
#         transcript: str,
#         company_name: Optional[str]
#     ) -> str:
#         """
#         Build extraction prompt from transcript
        
#         Args:
#             transcript: Earnings transcript
#             company_name: Optional company name
            
#         Returns:
#             Formatted prompt
#         """
#         if company_name:
#             return f"""Extract forex trading signals from this {company_name} earnings call transcript. Return a structured JSON response.

# Transcript:
# {transcript}"""
#         else:
#             return f"""Extract forex trading signals from this earnings call transcript. Return a structured JSON response.

# Transcript:
# {transcript}"""
    
#     def _parse_signal_response(self, response: str) -> Dict:
#         """
#         Parse JSON response from model

#         Properly handles null values in all fields
        
#         Args:
#             response: Model output
            
#         Returns:
#             Parsed signal data with proper null handling
#         """
#         try:
#             # Try to find JSON in response
#             if "{" in response and "}" in response:
#                 start = response.find("{")
#                 end = response.rfind("}") + 1
#                 json_str = response[start:end]
#                 signal_data = json.loads(json_str)
#             else:
#                 signal_data = json.loads(response)
            
#             # Validate that 'signal' and 'reasoning' are present (only truly required fields)
#             if "signal" not in signal_data:
#                 raise ValueError("Missing required field: signal")
#             if "reasoning" not in signal_data:
#                 raise ValueError("Missing required field: reasoning")
            
#             # Convert signal to boolean (handle string "true"/"false")
#             if not isinstance(signal_data["signal"], bool):
#                 signal_data["signal"] = str(signal_data["signal"]).lower() == "true"
            
#             # FIX 2: Handle null values for optional fields with proper defaults
#             signal_data.setdefault("currency_pair", None)
#             signal_data.setdefault("direction", None)
#             signal_data.setdefault("confidence", None)
#             signal_data.setdefault("magnitude", None)
#             signal_data.setdefault("time_horizon", None)
            
#             # Type conversion for confidence - only if not None
#             if signal_data["confidence"] is not None:
#                 if not isinstance(signal_data["confidence"], (int, float)):
#                     try:
#                         signal_data["confidence"] = float(signal_data["confidence"])
#                     except (ValueError, TypeError):
#                         logger.warning(f"Could not convert confidence to float: {signal_data['confidence']}")
#                         signal_data["confidence"] = None
#                 else:
#                     # Clamp confidence to 0-1 range
#                     signal_data["confidence"] = max(0.0, min(1.0, signal_data["confidence"]))
            
#             # Validate direction - allow None
#             if signal_data["direction"] is not None:
#                 valid_directions = ["LONG", "SHORT", "NEUTRAL"]
#                 if signal_data["direction"] not in valid_directions:
#                     logger.warning(f"Invalid direction: {signal_data['direction']}, setting to None")
#                     signal_data["direction"] = None
            
#             # Validate magnitude - allow None
#             if signal_data["magnitude"] is not None:
#                 valid_magnitudes = ["low", "moderate", "high"]
#                 if signal_data["magnitude"] not in valid_magnitudes:
#                     logger.warning(f"Invalid magnitude: {signal_data['magnitude']}, setting to None")
#                     signal_data["magnitude"] = None
            
#             # Validate time_horizon - allow None
#             if signal_data["time_horizon"] is not None:
#                 valid_time_horizons = ["current_quarter", "long_term", "next_quarter"]
#                 if signal_data["time_horizon"] not in valid_time_horizons:
#                     logger.warning(f"Invalid time_horizon: {signal_data['time_horizon']}, setting to None")
#                     signal_data["time_horizon"] = None
            
#             return signal_data
            
#         except json.JSONDecodeError as e:
#             logger.error(f"Failed to parse JSON response: {response}")
#             # Return a "no signal" response if parsing fails
#             return {
#                 "signal": False,
#                 "currency_pair": None,
#                 "direction": None,
#                 "confidence": None,
#                 "reasoning": f"Failed to parse model output: {str(e)}",
#                 "magnitude": None,
#                 "time_horizon": None
#             }
#         except Exception as e:
#             logger.error(f"Error parsing signal response: {str(e)}")
#             raise
    
#     async def _generate_signal(self, messages: List[Dict]) -> str:
#         """
#         Generate signal from fine-tuned model
        
#         Args:
#             messages: Conversation messages
            
#         Returns:
#             Model response
#         """
#         last_error = None

#         for attempt in range(3):
#             try:
#                 # Use inference endpoint for fine-tuned model
#                 response = await self.hf_client.chat_completion(
#                     messages=messages,
#                     model=self.model_id,
#                     max_tokens=300,
#                     temperature=0.1,  # Low temperature for consistent output
#                     top_p=0.9
#                 )
                
#                 return response.choices[0].message.content
                
#             except Exception as e:
#                 last_error = e
#                 # logger.error(f"Error calling fine-tuned model: {str(e)}", exc_info=True)
#                 logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
#                 if attempt < 2:
#                     await asyncio.sleep(2)

#         logger.error(f"All retries failed: {str(last_error)}", exc_info=True)
#         raise last_error
    
#     async def _save_signal(
#         self,
#         user_id: str,
#         signal_data: Dict,
#         transcript: str
#     ) -> str:
#         """
#         Save extracted signal to database
        
#         Args:
#             user_id: User ID
#             signal_data: Extracted signal data
#             transcript: Original transcript
            
#         Returns:
#             Signal ID
#         """
#         try:
#             signal_id = str(uuid.uuid4())
            
#             # Truncate transcript for storage
#             transcript_excerpt = transcript[:500] + "..." if len(transcript) > 500 else transcript
            
#             await self.db.from_("signals").insert({
#                 "id": signal_id,
#                 "user_id": user_id,
#                 "currency_pair": signal_data["currency_pair"],  # Can be None
#                 "direction": signal_data["direction"],  # Can be None
#                 "confidence": signal_data["confidence"],    # Can be None
#                 "reasoning": signal_data["reasoning"],
#                 "magnitude": signal_data["magnitude"],  # Can be None
#                 "time_horizon": signal_data["time_horizon"],    # Can be None
#                 "company_name": signal_data.get("company_name"),
#                 "transcript_excerpt": transcript_excerpt,
#                 "created_at": datetime.utcnow().isoformat()
#             }).execute()
            
#             return signal_id
            
#         except Exception as e:
#             logger.error(f"Error saving signal: {str(e)}", exc_info=True)
#             raise

"""
Signal Extraction Service - Forex Signal Detection from Earnings Transcripts
Uses fine-tuned ForexGPT model to extract currency exposure signals.
DB calls use db.signals repo from core.database.
"""

import json
import asyncio
import re
from typing import Dict, List, Optional
import logging

from core.database import db
from services.ai_errors import AIServiceUnavailableError, is_temporary_ai_unavailable_error

logger = logging.getLogger(__name__)


class SignalService:
    """
    Service for extracting forex trading signals from earnings call transcripts.
    Uses the fine-tuned ForexGPT model hosted on HuggingFace.
    All database operations go through db.signals (SignalsRepo).
    """
    # def __init__(self, hf_client, model_id: str = "forexgpt/forexgpt-mistral-7b-forex-signals-v1.0"):
    #     """
    #     Args:
    #         hf_client: HuggingFace AsyncInferenceClient
    #         model_id:  HuggingFace model ID for the fine-tuned signal model
    #     """
    def __init__(self, mistral_client, model_id: str = "mistral-small-latest"):
        """
        Args:
            mistral_client: Mistral async client instance
            model_id:       Mistral model ID (swap for HuggingFace model when ready)
        """
        # self.hf_client = hf_client
        self.mistral_client = mistral_client
        self.model_id  = model_id

        self.system_prompt = (
            'You are ForexGPT, a specialized AI assistant for extracting forex trading signals '
            'from corporate earnings call transcripts.\n\n'
            'When given an earnings transcript excerpt, analyze it for currency exposure and return '
            'a structured JSON response with these fields:\n'
            '- signal (boolean): Whether a valid forex signal exists\n'
            '- currency_pair (string or null): e.g. "EUR/USD", null if not specified\n'
            '- direction (string or null): "LONG", "SHORT", "NEUTRAL", or null if unclear\n'
            '- confidence (float or null): 0.0-1.0, null if not determinable\n'
            '- reasoning (string): Why this signal exists\n'
            '- magnitude (string or null): "low", "moderate", "high", or null\n'
            '- time_horizon (string or null): "current_quarter", "long_term", "next_quarter", "full_term", "short_term", "full_year" or null\n\n'
            'Only extract signals when there is clear forex exposure. Be conservative with confidence scores.'
        )

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    async def extract_signal(
        self,
        user_id: str,
        transcript: str,
        company_name: Optional[str] = None,
        save_to_db: bool = True,
    ) -> Dict:
        """
        Extract a forex signal from an earnings transcript.
        Only persists to DB when signal=True and save_to_db=True.
        """
        try:
            logger.info(f"Extracting signal for user {user_id}")

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user",   "content": self._build_extraction_prompt(transcript, company_name)},
            ]

            raw_response = await self._generate_signal(messages)
            signal_data  = self._parse_signal_response(raw_response)

            signal_data["raw_response"] = raw_response
            signal_data["company_name"] = company_name

            signal_data["currency_pair"] = self._normalize_currency_pair(
                signal_data.get("currency_pair")
            )

            if not signal_data["signal"]:
                signal_data["currency_pair"] = None
                signal_data["direction"] = None
                signal_data["confidence"] = None
                signal_data["magnitude"] = None
                signal_data["time_horizon"] = None

            if save_to_db and signal_data["signal"] and signal_data.get("currency_pair"):
                excerpt = transcript[:500] + "..." if len(transcript) > 500 else transcript
                saved = db.signals.create(user_id, {
                    "currency_pair":      [signal_data.get("currency_pair")] if signal_data.get("currency_pair") else None, # signal_data.get("currency_pair"),
                    "direction":          signal_data.get("direction").lower() if signal_data.get("direction") else None, # signal_data.get("direction"),
                    "confidence":         signal_data.get("confidence"),
                    "reasoning":          signal_data["reasoning"],
                    "magnitude":          signal_data.get("magnitude"),
                    "time_horizon":       signal_data.get("time_horizon"),
                    "company_name":       company_name,
                    "transcript_excerpt": excerpt,
                    "extraction_result":  signal_data,
                })
                signal_data["signal_id"] = saved["id"]
                signal_data["timestamp"] = saved.get("created_at")

            logger.info(f"Signal extraction complete — signal={signal_data['signal']}")
            return signal_data

        except Exception as e:
            logger.error(f"Error extracting signal: {e}", exc_info=True)
            raise

    # async def save_signal_result(self, user_id: str, signal_data: Dict) -> Dict:
    #     """Persist an already extracted signal result to the database."""
    #     try:
    #         logger.info(f"Saving signal result for user {user_id}")
    #         reasoning = signal_data.get("reasoning", "No further analysis available.")
    #         excerpt = reasoning[:500] + "..." if len(reasoning) > 500 else reasoning
            
    #         saved = db.signals.create(user_id, {
    #             "currency_pair":      signal_data.get("currency_pair"),
    #             "direction":          signal_data.get("direction").lower() if signal_data.get("direction") else None,
    #             "confidence":         signal_data.get("confidence"),
    #             "reasoning":          reasoning,
    #             "magnitude":          signal_data.get("magnitude"),
    #             "time_horizon":       signal_data.get("time_horizon"),
    #             "company_name":       signal_data.get("company_name"),
    #             "transcript_excerpt": excerpt,
    #             "extraction_result":  signal_data,
    #         })
    #         return {
    #             "message": "Signal saved successfully",
    #             "signal_id": saved["id"],
    #             "timestamp": saved.get("created_at")
    #         }
    #     except Exception as e:
    #         logger.error(f"Error saving signal result: {e}", exc_info=True)
    #         raise

    async def batch_extract_signals(
        self,
        user_id: str,
        transcripts: List[Dict],
        save_to_db: bool = True,
    ) -> List[Dict]:
        """
        Extract signals from multiple transcripts.
        A failure on one transcript does not stop the rest.
        Each item in transcripts must have 'text' and optionally 'company_name'.
        """
        signals = []
        for item in transcripts:
            try:
                signal = await self.extract_signal(
                    user_id=user_id,
                    transcript=item["text"],
                    company_name=item.get("company_name"),
                    save_to_db=save_to_db,
                )
                signals.append(signal)
            except Exception as e:
                logger.error(f"Batch item failed: {e}")
                signals.append({
                    "signal":       False,
                    "error":        str(e),
                    "company_name": item.get("company_name"),
                })
        return signals

    def get_user_signals(
        self,
        user_id: str,
        limit: int = 50,
        currency_pair: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> List[Dict]:
        """Return saved signals for a user with optional pair/direction filters."""
        try:
            rows = db.signals.list(user_id=user_id, pair=currency_pair, direction=direction, limit=limit)
            for row in rows:
                row["currency_pair"] = self._normalize_currency_pair(row.get("currency_pair"))
            return rows
        except Exception as e:
            logger.error(f"Error retrieving signals: {e}", exc_info=True)
            raise

    # def get_signal_by_id(self, signal_id: str, user_id: str) -> Optional[Dict]:
    #     """Return a signal by ID. Returns None if not found or owned by another user."""
    #     try:
    #         row = db.signals.get(signal_id)
    #         if not row or row.get("user_id") != user_id:
    #             return None
    #         return row
    #     except Exception as e:
    #         logger.error(f"Error retrieving signal: {e}", exc_info=True)
    #         raise

    def get_signal_by_id(self, signal_id: str, user_id: str) -> Optional[Dict]:
        """Return a signal by ID. Returns None if not found or owned by another user."""
        try:
            row = db.signals.get(signal_id)
            if not row or row.get("user_id") != user_id:
                return None
            
            row["currency_pair"] = self._normalize_currency_pair(row.get("currency_pair"))
            
            # Add signal_id field for Pydantic model
            row["signal_id"] = str(row["id"])
            
            return row
        except Exception as e:
            logger.error(f"Error retrieving signal: {e}", exc_info=True)
            raise

    def delete_signal(self, signal_id: str, user_id: str) -> bool:
        """
        Delete (unsave) a signal.
        Returns False if not found or not owned by this user.
        """
        try:
            try:
                row = db.signals.get(signal_id)
            except Exception:
                logger.warning(f"Signal {signal_id} not found")
                return False
            if not row or row.get("user_id") != user_id:
                logger.warning(f"Signal {signal_id} not found or unauthorized")
                return False
            db.signals.delete(signal_id)
            logger.info(f"Deleted signal {signal_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting signal: {e}", exc_info=True)
            raise

    def get_signal_statistics(self, user_id: str) -> Dict:
        """
        Calculate summary statistics across all of a user's saved signals.
        Returns breakdowns by currency pair, direction, magnitude, and average confidence.
        """
        try:
            signals = db.signals.list(user_id=user_id, limit=1000)

            if not signals:
                return {
                    "total_signals":    0,
                    "by_currency_pair": {},
                    "by_direction":     {},
                    "by_magnitude":     {},
                    "average_confidence": 0,
                }

            confidences   = [s["confidence"] for s in signals if s.get("confidence") is not None]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            stats = {
                "total_signals":    len(signals),
                "by_currency_pair": {},
                "by_direction":     {"LONG": 0, "SHORT": 0, "NEUTRAL": 0, "UNKNOWN": 0},
                "by_magnitude":     {"low": 0, "moderate": 0, "high": 0, "UNKNOWN": 0},
                "average_confidence": avg_confidence,
            }

            # for s in signals:
            #     # Handle potential list if DB still has old format
            #     raw_pair = s.get("currency_pair")
            #     if isinstance(raw_pair, list):
            #         pair = raw_pair[0] if raw_pair else "UNKNOWN"
            #     else:
            #         pair = raw_pair or "UNKNOWN"
                
            #     stats["by_currency_pair"][pair] = stats["by_currency_pair"].get(pair, 0) + 1

            #     direction = s.get("primary_direction") or "UNKNOWN"
            #     if direction in stats["by_direction"]:
            #         stats["by_direction"][direction] += 1
            #     else:
            #         stats["by_direction"]["UNKNOWN"] += 1

            #     magnitude = s.get("magnitude") or "UNKNOWN"
            #     if magnitude in stats["by_magnitude"]:
            #         stats["by_magnitude"][magnitude] += 1
            #     else:
            #         stats["by_magnitude"]["UNKNOWN"] += 1

            # return stats

            for s in signals:
                pair = self._normalize_currency_pair(s.get("currency_pair")) or "UNKNOWN"
                stats["by_currency_pair"][pair] = stats["by_currency_pair"].get(pair, 0) + 1

                direction = (s.get("direction") or "UNKNOWN").upper()
                if direction in stats["by_direction"]:
                    stats["by_direction"][direction] += 1
                else:
                    stats["by_direction"]["UNKNOWN"] += 1

                magnitude = s.get("magnitude") or "UNKNOWN"
                if magnitude in stats["by_magnitude"]:
                    stats["by_magnitude"][magnitude] += 1
                else:
                    stats["by_magnitude"]["UNKNOWN"] += 1

            return stats

        except Exception as e:
            logger.error(f"Error calculating statistics: {e}", exc_info=True)
            raise

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _build_extraction_prompt(self, transcript: str, company_name: Optional[str]) -> str:
        prefix = f"Extract forex trading signals from this {company_name} earnings call transcript." \
                 if company_name else \
                 "Extract forex trading signals from this earnings call transcript."
        return f"{prefix} Return a structured JSON response.\n\nTranscript:\n{transcript}"

    def _normalize_currency_pair(self, value: object) -> Optional[str]:
        """
        Normalize model or DB currency pair values into a consistent XXX/YYY format.
        Returns None for malformed values so they do not pollute saved history.
        """
        if isinstance(value, list):
            value = value[0] if value else None

        if value is None:
            return None

        text = str(value).strip().upper()
        if not text:
            return None

        # Drop common placeholders and labels produced by model formatting.
        text = re.sub(r"^\s*(CURRENCY_?PAIR|PAIR)\s*[:=\-]*\s*", "", text)
        if text in {"N/A", "NA", "NONE", "NULL", "UNKNOWN"}:
            return None

        for slash in ("\\", "-", "–", "—", "／", "|"):
            text = text.replace(slash, "/")
        text = re.sub(r"\s+", "", text)

        matched_pair = re.search(r"\b([A-Z]{3})/([A-Z]{3})\b", text)
        if matched_pair:
            return f"{matched_pair.group(1)}/{matched_pair.group(2)}"

        collapsed = re.sub(r"[^A-Z]", "", text)
        if len(collapsed) == 6:
            return f"{collapsed[:3]}/{collapsed[3:]}"

        return None

    def _parse_signal_response(self, response: str) -> Dict:
        """
        Parse and validate the JSON output from the model.
        All optional fields are nullable — only 'signal' and 'reasoning' are required.
        Invalid values are set to None with a warning rather than crashing.
        """
        try:
            if "{" in response and "}" in response:
                start = response.find("{")
                end   = response.rfind("}") + 1
                data  = json.loads(response[start:end])
            else:
                data = json.loads(response)

            if "signal" not in data:
                raise ValueError("Missing required field: signal")
            if "reasoning" not in data:
                raise ValueError("Missing required field: reasoning")

            # Normalise signal to bool
            if not isinstance(data["signal"], bool):
                data["signal"] = str(data["signal"]).lower() == "true"

            # Default all optional fields to None
            for field in ("currency_pair", "direction", "confidence", "magnitude", "time_horizon"):
                data.setdefault(field, None)

            data["currency_pair"] = self._normalize_currency_pair(data["currency_pair"])

            # Validate confidence
            if data["confidence"] is not None:
                if not isinstance(data["confidence"], (int, float)):
                    try:
                        data["confidence"] = float(data["confidence"])
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid confidence value: {data['confidence']}")
                        data["confidence"] = None
                else:
                    data["confidence"] = max(0.0, min(1.0, data["confidence"]))

            # Validate direction
            if data["direction"] is not None and data["direction"] not in ("LONG", "SHORT", "NEUTRAL"):
                logger.warning(f"Invalid direction: {data['direction']}")
                data["direction"] = None

            # Validate magnitude
            if data["magnitude"] is not None and data["magnitude"] not in ("low", "moderate", "high"):
                logger.warning(f"Invalid magnitude: {data['magnitude']}")
                data["magnitude"] = None

            # Validate time_horizon
            valid_horizons = (
                "current_quarter",
                "long_term",
                "next_quarter",
                "full_term",
                "short_term",
                "full_year",
            )
            if data["time_horizon"] is not None and data["time_horizon"] not in valid_horizons:
                logger.warning(f"Invalid time_horizon: {data['time_horizon']}")
                data["time_horizon"] = None

            return data

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error. Raw response: {response}")
            return {
                "signal":        False,
                "currency_pair": None,
                "direction":     None,
                "confidence":    None,
                "reasoning":     f"Failed to parse model output: {e}",
                "magnitude":     None,
                "time_horizon":  None,
            }
        except Exception as e:
            logger.error(f"Error parsing signal response: {e}")
            raise
 
    # def _messages_to_prompt(self, messages: List[Dict]) -> str:
    #     """
    #     Convert chat-style messages into a single text prompt for a
    #     causal LM (AutoModelForCausalLM) that doesn't support chat format.

    #     Format:
    #         System: ...
    #         User: ...
    #         Assistant:
    #     """
    #     parts = []
    #     for msg in messages:
    #         role = msg["role"].capitalize()
    #         parts.append(f"{role}: {msg['content']}")
    #     # Add the assistant prefix so the model continues from here
    #     parts.append("Assistant:")
    #     return "\n\n".join(parts)

    async def _generate_signal(self, messages: List[Dict]) -> str:
        """
        Call the HuggingFace causal LM model with up to 3 retries.
        Uses text_generation instead of chat_completion because the
        fine-tuned model is AutoModelForCausalLM, not a chat model.

        Call Mistral API with up to 3 retries.
        Placeholder until fine-tuned model has a dedicated HuggingFace
        Inference Endpoint. Swap mistral_client for hf_client when ready.
        """
        # print(f"DEBUG provider: {self.hf_client.provider}")
        # prompt = self._messages_to_prompt(messages)
        last_error = None
        for attempt in range(3):
            try:
                # response = await self.hf_client.chat_completion(
                #     messages=messages,
                #     model=self.model_id,
                #     max_tokens=300,
                #     temperature=0.1,
                #     top_p=0.9,
                # )
                # return response.choices[0].message.content
                response = await self.mistral_client.chat.complete_async(
                    model=self.model_id,
                    messages=messages,
                    max_tokens=300,
                    temperature=0.1,
                    top_p=0.9,
                )
                return response.choices[0].message.content
                # response = await self.hf_client.text_generation(
                #     prompt,
                #     model=self.model_id,
                #     max_new_tokens=300,
                #     temperature=0.1,
                #     top_p=0.9,
                #     do_sample=True,
                #     return_full_text=False,  # only return the generated part
                # )
                # return response
            except Exception as e:
                last_error = e
                logger.warning(f"_generate_signal attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2)

        logger.error(f"All retries exhausted: {last_error}", exc_info=True)
        if last_error and is_temporary_ai_unavailable_error(last_error):
            raise AIServiceUnavailableError(
                "The signal extraction model is temporarily at capacity. Please try again in a moment."
            )
        raise last_error
