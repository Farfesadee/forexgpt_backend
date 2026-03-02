"""
Signal Extraction Service - Forex Signal Detection from Earnings Transcripts
Uses fine-tuned Mistral model to extract currency exposure signals
"""

import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional
import logging
import asyncio

logger = logging.getLogger(__name__)


class SignalService:
    """
    Service for extracting forex trading signals from earnings call transcripts.
    Uses the fine-tuned ForexGPT model.
    """
    
    def __init__(self, hf_client, db, model_id: str = "forexgpt/mistral-7b-forex-signals"):
        """
        Initialize signal extraction service
        
        Args:
            hf_client: Hugging Face inference client
            db: Database connection (Supabase or similar)
            model_id: Hugging Face model ID for fine-tuned model
        """
        self.hf_client = hf_client
        self.db = db
        self.model_id = model_id
        
        # System prompt for signal extraction
        self.system_prompt = """You are ForexGPT, a specialized AI assistant for extracting forex trading signals from corporate earnings call transcripts.

When given an earnings transcript excerpt, you analyze it for currency exposure information and return a structured JSON response with the following fields:
- signal (boolean): Whether a valid forex signal exists
- currency_pair (string or null): The currency pair (e.g., "EUR/USD"), or null if not specified
- direction (string or null): Trading direction - "LONG", "SHORT", "NEUTRAL", or null if unclear
- confidence (float or null): Confidence score between 0.0 and 1.0, or null if not determinable
- reasoning (string): Clear explanation of why this signal exists
- magnitude (string or null): Impact level - "low", "moderate", "high", or null
- time_horizon (string or null): Expected timeframe - "current_quarter", "long_term", "next_quarter", "full_term", "short_term", "full_year" or null

Only extract signals when there is clear forex exposure mentioned. Be conservative with confidence scores."""
    
    async def extract_signal(
        self,
        user_id: str,
        transcript: str,
        company_name: Optional[str] = None,
        save_to_db: bool = True
    ) -> Dict:
        """
        Extract forex signal from earnings transcript
        
        Args:
            user_id: User's unique identifier
            transcript: Earnings call transcript or excerpt
            company_name: Optional company name for context
            save_to_db: Whether to save signal to database
            
        Returns:
            Dict containing:
                - signal: Whether a signal exists
                - currency_pair: Currency pair (e.g., "EUR/USD")
                - direction: LONG/SHORT/NEUTRAL
                - confidence: 0.0 to 1.0
                - reasoning: Explanation
                - magnitude: low/moderate/high
                - time_horizon: Timeframe
                - raw_response: Full model output
                - signal_id: Database ID if saved
        """
        try:
            logger.info(f"Extracting signal for user {user_id}")
            
            # Build prompt
            user_message = self._build_extraction_prompt(transcript, company_name)
            
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message}
            ]
            
            # Call fine-tuned model
            logger.info(f"Calling fine-tuned model {self.model_id}")
            raw_response = await self._generate_signal(messages)
            
            # Parse JSON response
            signal_data = self._parse_signal_response(raw_response)
            
            # Add metadata
            signal_data["raw_response"] = raw_response
            signal_data["company_name"] = company_name
            signal_data["timestamp"] = datetime.utcnow().isoformat()
            
            # Save to database if requested
            if save_to_db and signal_data["signal"]:
                signal_id = await self._save_signal(user_id, signal_data, transcript)
                signal_data["signal_id"] = signal_id
            
            logger.info(f"Successfully extracted signal: {signal_data['signal']}")
            
            return signal_data
            
        except Exception as e:
            logger.error(f"Error extracting signal: {str(e)}", exc_info=True)
            raise
    
    async def batch_extract_signals(
        self,
        user_id: str,
        transcripts: List[Dict],
        save_to_db: bool = True
    ) -> List[Dict]:
        """
        Extract signals from multiple transcripts
        
        Args:
            user_id: User's unique identifier
            transcripts: List of dicts with 'text' and optional 'company_name'
            save_to_db: Whether to save signals to database
            
        Returns:
            List of extracted signals
        """
        signals = []
        
        for transcript in transcripts:
            try:
                signal = await self.extract_signal(
                    user_id=user_id,
                    transcript=transcript["text"],
                    company_name=transcript.get("company_name"),
                    save_to_db=save_to_db
                )
                signals.append(signal)
                
            except Exception as e:
                logger.error(f"Error processing transcript: {str(e)}")
                signals.append({
                    "signal": False,
                    "error": str(e),
                    "company_name": transcript.get("company_name")
                })
        
        return signals
    
    async def get_user_signals(
        self,
        user_id: str,
        limit: int = 50,
        currency_pair: Optional[str] = None,
        direction: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve user's saved signals with optional filters
        
        Args:
            user_id: User's unique identifier
            limit: Maximum number of signals to return
            currency_pair: Optional filter by currency pair
            direction: Optional filter by direction (LONG/SHORT/NEUTRAL)
            
        Returns:
            List of signals
        """
        try:
            query = self.db.from_("signals") \
                .select("*") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit)
            
            if currency_pair:
                query = query.eq("currency_pair", currency_pair)
            
            if direction:
                query = query.eq("direction", direction)
            
            result = await query.execute()
            
            return [
                {
                    "signal_id": row["id"],
                    "currency_pair": row["currency_pair"],
                    "direction": row["direction"],
                    "confidence": row["confidence"],
                    "reasoning": row["reasoning"],
                    "magnitude": row["magnitude"],
                    "time_horizon": row["time_horizon"],
                    "company_name": row.get("company_name"),
                    "created_at": row["created_at"]
                }
                for row in result.data
            ]
            
        except Exception as e:
            logger.error(f"Error retrieving signals: {str(e)}", exc_info=True)
            raise
    
    async def get_signal_by_id(
        self,
        signal_id: str,
        user_id: str
    ) -> Optional[Dict]:
        """
        Retrieve a specific signal
        
        Args:
            signal_id: Signal ID
            user_id: User ID (for authorization)
            
        Returns:
            Signal details or None if not found
        """
        try:
            result = await self.db.from_("signals") \
                .select("*") \
                .eq("id", signal_id) \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()
            
            if not result.data:
                return None
            
            row = result.data[0]    # access first item from list

            # return {
            #     "signal_id": result.data["id"],
            #     "currency_pair": result.data["currency_pair"],
            #     "direction": result.data["direction"],
            #     "confidence": result.data["confidence"],
            #     "reasoning": result.data["reasoning"],
            #     "magnitude": result.data["magnitude"],
            #     "time_horizon": result.data["time_horizon"],
            #     "company_name": result.data.get("company_name"),
            #     "transcript_excerpt": result.data.get("transcript_excerpt"),
            #     "created_at": result.data["created_at"]
            # }
            return {
                "signal_id": row["id"],
                "currency_pair": row["currency_pair"],
                "direction": row["direction"],
                "confidence": row["confidence"],
                "reasoning": row["reasoning"],
                "magnitude": row["magnitude"],
                "time_horizon": row["time_horizon"],
                "company_name": row.get("company_name"),
                "transcript_excerpt": row.get("transcript_excerpt"),
                "created_at": row["created_at"]
            }
            
        except Exception as e:
            logger.error(f"Error retrieving signal: {str(e)}", exc_info=True)
            raise
    
    async def delete_signal(
        self,
        signal_id: str,
        user_id: str
    ) -> bool:
        """
        Delete a signal
        
        Args:
            signal_id: Signal to delete
            user_id: User ID (for authorization)
            
        Returns:
            True if deleted, False if not found
        """
        try:
            check = await self.db.from_("signals") \
                .select("id") \
                .eq("id", signal_id) \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if not check.data:
                logger.warning(f"Signal {signal_id} not found or unauthorized")
                return False
            
            await self.db.from_("signals") \
                .delete() \
                .eq("id", signal_id) \
                .eq("user_id", user_id) \
                .execute()
            
            # return len(result.data) > 0
            logger.info(f"Deleted signal {signal_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting signal: {str(e)}", exc_info=True)
            raise
    
    async def get_signal_statistics(self, user_id: str) -> Dict:
        """
        Get statistics on user's signals
        
        Args:
            user_id: User's unique identifier
            
        Returns:
            Dict with signal statistics
        """
        try:
            # Get all user signals
            result = await self.db.from_("signals") \
                .select("currency_pair, direction, confidence, magnitude") \
                .eq("user_id", user_id) \
                .execute()
            
            if not result.data:
                return {
                    "total_signals": 0,
                    "by_currency_pair": {},
                    "by_direction": {},
                    "by_magnitude": {},
                    "average_confidence": 0
                }
            
            signals = result.data
            
            # Calculate statistics
            # Filter out None values for confidence calculation
            confidences = [s["confidence"] for s in signals if s["confidence"] is not None]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            stats = {
                "total_signals": len(signals),
                "by_currency_pair": {},
                "by_direction": {"LONG": 0, "SHORT": 0, "NEUTRAL": 0, "UNKNOWN": 0},
                "by_magnitude": {"low": 0, "moderate": 0, "high": 0, "UNKNOWN": 0},
                "average_confidence": avg_confidence
            }
            
            # Count by categories
            for signal in signals:
                # Currency pair (including None)
                pair = signal["currency_pair"] if signal["currency_pair"] else "UNKNOWN"
                stats["by_currency_pair"][pair] = stats["by_currency_pair"].get(pair, 0) + 1
                
                # Direction (including None)
                direction = signal["direction"] if signal["direction"] else "UNKNOWN"
                if direction in stats["by_direction"]:
                    stats["by_direction"][direction] += 1
                else:
                    stats["by_direction"]["UNKNOWN"] += 1
                
                # Magnitude (including None)
                magnitude = signal["magnitude"] if signal["magnitude"] else "UNKNOWN"
                if magnitude in stats["by_magnitude"]:
                    stats["by_magnitude"][magnitude] += 1
                else:
                    stats["by_magnitude"]["UNKNOWN"] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating statistics: {str(e)}", exc_info=True)
            raise
    
    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    def _build_extraction_prompt(
        self,
        transcript: str,
        company_name: Optional[str]
    ) -> str:
        """
        Build extraction prompt from transcript
        
        Args:
            transcript: Earnings transcript
            company_name: Optional company name
            
        Returns:
            Formatted prompt
        """
        if company_name:
            return f"""Extract forex trading signals from this {company_name} earnings call transcript. Return a structured JSON response.

Transcript:
{transcript}"""
        else:
            return f"""Extract forex trading signals from this earnings call transcript. Return a structured JSON response.

Transcript:
{transcript}"""
    
    def _parse_signal_response(self, response: str) -> Dict:
        """
        Parse JSON response from model

        Properly handles null values in all fields
        
        Args:
            response: Model output
            
        Returns:
            Parsed signal data with proper null handling
        """
        try:
            # Try to find JSON in response
            if "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
                signal_data = json.loads(json_str)
            else:
                signal_data = json.loads(response)
            
            # Validate that 'signal' and 'reasoning' are present (only truly required fields)
            if "signal" not in signal_data:
                raise ValueError("Missing required field: signal")
            if "reasoning" not in signal_data:
                raise ValueError("Missing required field: reasoning")
            
            # Convert signal to boolean (handle string "true"/"false")
            if not isinstance(signal_data["signal"], bool):
                signal_data["signal"] = str(signal_data["signal"]).lower() == "true"
            
            # FIX 2: Handle null values for optional fields with proper defaults
            signal_data.setdefault("currency_pair", None)
            signal_data.setdefault("direction", None)
            signal_data.setdefault("confidence", None)
            signal_data.setdefault("magnitude", None)
            signal_data.setdefault("time_horizon", None)
            
            # Type conversion for confidence - only if not None
            if signal_data["confidence"] is not None:
                if not isinstance(signal_data["confidence"], (int, float)):
                    try:
                        signal_data["confidence"] = float(signal_data["confidence"])
                    except (ValueError, TypeError):
                        logger.warning(f"Could not convert confidence to float: {signal_data['confidence']}")
                        signal_data["confidence"] = None
                else:
                    # Clamp confidence to 0-1 range
                    signal_data["confidence"] = max(0.0, min(1.0, signal_data["confidence"]))
            
            # Validate direction - allow None
            if signal_data["direction"] is not None:
                valid_directions = ["LONG", "SHORT", "NEUTRAL"]
                if signal_data["direction"] not in valid_directions:
                    logger.warning(f"Invalid direction: {signal_data['direction']}, setting to None")
                    signal_data["direction"] = None
            
            # Validate magnitude - allow None
            if signal_data["magnitude"] is not None:
                valid_magnitudes = ["low", "moderate", "high"]
                if signal_data["magnitude"] not in valid_magnitudes:
                    logger.warning(f"Invalid magnitude: {signal_data['magnitude']}, setting to None")
                    signal_data["magnitude"] = None
            
            # Validate time_horizon - allow None
            if signal_data["time_horizon"] is not None:
                valid_time_horizons = ["current_quarter", "long_term", "next_quarter"]
                if signal_data["time_horizon"] not in valid_time_horizons:
                    logger.warning(f"Invalid time_horizon: {signal_data['time_horizon']}, setting to None")
                    signal_data["time_horizon"] = None
            
            return signal_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {response}")
            # Return a "no signal" response if parsing fails
            return {
                "signal": False,
                "currency_pair": None,
                "direction": None,
                "confidence": None,
                "reasoning": f"Failed to parse model output: {str(e)}",
                "magnitude": None,
                "time_horizon": None
            }
        except Exception as e:
            logger.error(f"Error parsing signal response: {str(e)}")
            raise
    
    async def _generate_signal(self, messages: List[Dict]) -> str:
        """
        Generate signal from fine-tuned model
        
        Args:
            messages: Conversation messages
            
        Returns:
            Model response
        """
        last_error = None

        for attempt in range(3):
            try:
                # Use inference endpoint for fine-tuned model
                response = await self.hf_client.chat_completion(
                    messages=messages,
                    model=self.model_id,
                    max_tokens=300,
                    temperature=0.1,  # Low temperature for consistent output
                    top_p=0.9
                )
                
                return response.choices[0].message.content
                
            except Exception as e:
                last_error = e
                # logger.error(f"Error calling fine-tuned model: {str(e)}", exc_info=True)
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < 2:
                    await asyncio.sleep(2)

        logger.error(f"All retries failed: {str(last_error)}", exc_info=True)
        raise last_error
    
    async def _save_signal(
        self,
        user_id: str,
        signal_data: Dict,
        transcript: str
    ) -> str:
        """
        Save extracted signal to database
        
        Args:
            user_id: User ID
            signal_data: Extracted signal data
            transcript: Original transcript
            
        Returns:
            Signal ID
        """
        try:
            signal_id = str(uuid.uuid4())
            
            # Truncate transcript for storage
            transcript_excerpt = transcript[:500] + "..." if len(transcript) > 500 else transcript
            
            await self.db.from_("signals").insert({
                "id": signal_id,
                "user_id": user_id,
                "currency_pair": signal_data["currency_pair"],  # Can be None
                "direction": signal_data["direction"],  # Can be None
                "confidence": signal_data["confidence"],    # Can be None
                "reasoning": signal_data["reasoning"],
                "magnitude": signal_data["magnitude"],  # Can be None
                "time_horizon": signal_data["time_horizon"],    # Can be None
                "company_name": signal_data.get("company_name"),
                "transcript_excerpt": transcript_excerpt,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            
            return signal_id
            
        except Exception as e:
            logger.error(f"Error saving signal: {str(e)}", exc_info=True)
            raise


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

"""
# Initialize service
from huggingface_hub import AsyncInferenceClient
from supabase import create_client

hf_client = AsyncInferenceClient(token=HUGGING_FACE_TOKEN)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

signal_service = SignalService(hf_client, supabase, model_id="your-team/your-finetuned-model")

# Extract signal from transcript
transcript = '''
In Q1, we experienced a 4% revenue headwind from currency movements, 
primarily due to USD strength versus EUR. Our European operations represent 
approximately 35% of total revenue, and we expect this headwind to continue 
into Q2.
'''

signal = await signal_service.extract_signal(
    user_id="user_123",
    transcript=transcript,
    company_name="Microsoft"
)

print(f"Signal detected: {signal['signal']}")
print(f"Pair: {signal['currency_pair']}")
print(f"Direction: {signal['direction']}")
print(f"Confidence: {signal['confidence']}")
print(f"Reasoning: {signal['reasoning']}")

# Batch extraction
transcripts = [
    {"text": transcript1, "company_name": "Microsoft"},
    {"text": transcript2, "company_name": "Apple"},
    {"text": transcript3, "company_name": "Google"}
]

signals = await signal_service.batch_extract_signals(
    user_id="user_123",
    transcripts=transcripts
)

for signal in signals:
    if signal["signal"]:
        print(f"{signal['company_name']}: {signal['currency_pair']} {signal['direction']}")

# Get user's signals
user_signals = await signal_service.get_user_signals(
    user_id="user_123",
    currency_pair="EUR/USD"
)

print(f"Found {len(user_signals)} EUR/USD signals")

# Get statistics
stats = await signal_service.get_signal_statistics("user_123")
print(f"Total signals: {stats['total_signals']}")
print(f"Average confidence: {stats['average_confidence']:.2f}")
print(f"By direction: {stats['by_direction']}")
"""
