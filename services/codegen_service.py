"""
Code Generation Service - Strategy Translation with Conversational Debugging
Handles initial code generation and follow-up troubleshooting conversations
"""

import uuid
from datetime import datetime
from typing import Dict, Optional, List
import logging
from prompts.codegen_prompt import CODEGEN_SYSTEM_PROMPT
import asyncio

logger = logging.getLogger(__name__)


class CodeGenService:
    """
    Code generation service with conversational debugging support.
    Generates trading strategy code and helps troubleshoot issues.
    """
    
    def __init__(self, hf_client, db, model_id="mistralai/Mistral-7B-Instruct-v0.3"):
        """
        Initialize code generation service
        
        Args:
            hf_client: Hugging Face inference client
            db: Database connection (Supabase or similar)
        """
        self.hf_client = hf_client
        self.db = db
        self.model_id = model_id
        self.system_prompt = CODEGEN_SYSTEM_PROMPT
    
    async def generate_code(
        self,
        user_id: str,
        strategy_description: str,
        conversation_id: Optional[str] = None,
        previous_code: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Dict:
        """
        Generate or debug trading strategy code
        
        Args:
            user_id: User's unique identifier
            strategy_description: Strategy description or debugging request
            conversation_id: Optional conversation ID for follow-ups
            previous_code: Previously generated code (for debugging)
            error_message: Error message if debugging
            
        Returns:
            Dict containing:
                - code: Generated Python code
                - explanation: Brief explanation of the code
                - conversation_id: ID for follow-up questions
                - language: Programming language (always 'python')
        """
        try:
            # Load or create conversation
            if conversation_id:
                logger.info(f"Loading code gen conversation {conversation_id}")
                history = await self._load_conversation_history(conversation_id, user_id)
                if history is None:
                    conversation_id = str(uuid.uuid4())
                    history = []
            else:
                logger.info(f"Creating new code gen conversation for user {user_id}")
                conversation_id = str(uuid.uuid4())
                history = []
            
            # Build user message
            user_message = self._build_user_message(
                strategy_description,
                previous_code,
                error_message
            )
            
            # Build messages with conversation history
            messages = [
                {"role": "system", "content": self.system_prompt},
                *history,
                {"role": "user", "content": user_message}
            ]
            
            # Generate code
            logger.info(f"Generating code for conversation {conversation_id}")
            response = await self._generate_response(messages)
            
            # Extract code and explanation from response
            code, explanation = self._parse_response(response)
            
            # Save to database
            await self._save_message(
                conversation_id, 
                user_id, 
                "user", 
                user_message
            )
            await self._save_message(
                conversation_id,
                user_id,
                "assistant",
                response
            )
            
            # Save generated code separately for easy retrieval
            await self._save_generated_code(
                conversation_id,
                user_id,
                code,
                strategy_description
            )
            
            logger.info(f"Successfully generated code for conversation {conversation_id}")
            
            return {
                "code": code,
                "explanation": explanation,
                "conversation_id": conversation_id,
                "language": "python",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in generate_code: {str(e)}", exc_info=True)
            raise
    
    async def get_conversation_history(
        self,
        conversation_id: str,
        user_id: str
    ) -> Optional[List[Dict]]:
        """
        Retrieve code generation conversation history
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID (for authorization)
            
        Returns:
            List of messages or None if not found
        """
        try:
            history = await self._load_conversation_history(conversation_id, user_id)
            if history is None:
                return None
            
            return [
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": msg.get("timestamp", "")
                }
                for msg in history
            ]
            
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {str(e)}", exc_info=True)
            raise
    
    async def list_generated_codes(
        self,
        user_id: str,
        limit: int = 20
    ) -> List[Dict]:
        """
        List all code generations for a user
        
        Args:
            user_id: User's unique identifier
            limit: Maximum number to return
            
        Returns:
            List of generated code summaries
        """
        try:
            result = await self.db.from_("generated_codes") \
                .select("id, conversation_id, description, created_at") \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            return [
                {
                    "id": row["id"],
                    "conversation_id": row["conversation_id"],
                    "description": row["description"][:100] + "..." if len(row["description"]) > 100 else row["description"],
                    "created_at": row["created_at"]
                }
                for row in result.data
            ]
            
        except Exception as e:
            logger.error(f"Error listing generated codes: {str(e)}", exc_info=True)
            raise
    
    async def get_generated_code(
        self,
        code_id: str,
        user_id: str
    ) -> Optional[Dict]:
        """
        Retrieve a specific generated code
        
        Args:
            code_id: Code generation ID
            user_id: User ID (for authorization)
            
        Returns:
            Dict with code details or None if not found
        """
        try:
            result = await self.db.from_("generated_codes") \
                .select("*") \
                .eq("id", code_id) \
                .eq("user_id", user_id) \
                .single() \
                .execute()
            
            if not result.data:
                return None
            
            return {
                "id": result.data["id"],
                "code": result.data["code"],
                "description": result.data["description"],
                "conversation_id": result.data["conversation_id"],
                "created_at": result.data["created_at"]
            }
            
        except Exception as e:
            logger.error(f"Error retrieving generated code: {str(e)}", exc_info=True)
            raise
    
    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    def _build_user_message(
        self,
        description: str,
        previous_code: Optional[str],
        error_message: Optional[str]
    ) -> str:
        """
        Build user message based on context
        
        Args:
            description: Strategy description or debugging request
            previous_code: Previously generated code
            error_message: Error message if debugging
            
        Returns:
            Formatted user message
        """
        if error_message and previous_code:
            # Debugging scenario
            return f"""I got an error with the code you generated. Please help me fix it.

Previous code:
```python
{previous_code}
```

Error message:
```
{error_message}
```

Issue: {description}

Please provide the corrected code and explain what was wrong."""
        
        elif previous_code:
            # Modification request
            return f"""I need to modify the previous code.

Current code:
```python
{previous_code}
```

Requested changes: {description}

Please provide the updated code."""
        
        else:
            # Initial generation
            return f"""Please generate Python code for the following trading strategy:

{description}

Requirements:
• Use pandas for data handling
• Include clear entry and exit logic
• Add proper risk management
• Make it backtesting-ready
• Include docstrings and comments"""
    
    def _parse_response(self, response: str) -> tuple[str, str]:
        """
        Extract code and explanation from LLM response
        
        Args:
            response: Full LLM response
            
        Returns:
            Tuple of (code, explanation)
        """
        # Look for code blocks
        if "```python" in response:
            # Extract code between ```python and ```
            start = response.find("```python") + len("```python")
            end = response.find("```", start)
            code = response[start:end].strip()
            
            # Everything else is explanation
            explanation = response[:response.find("```python")] + response[end + 3:]
            explanation = explanation.strip()
        
        elif "```" in response:
            # Generic code block
            start = response.find("```") + 3
            end = response.find("```", start)
            code = response[start:end].strip()
            
            explanation = response[:response.find("```")] + response[end + 3:]
            explanation = explanation.strip()
        
        else:
            # No code blocks found - treat entire response as code
            code = response.strip()
            explanation = "Generated trading strategy code."
        
        return code, explanation
    
    async def _generate_response(self, messages: List[Dict]) -> str:
        """
        Generate response from LLM
        
        Args:
            messages: Conversation history
            
        Returns:
            Generated response
        """
        last_error =None

        for attempt in range(3):
            try:
                # response = await self.hf_client.chat_completetion(
                #     messages=messages,
                #     model=self.model_id,
                #     max_tokens=2500,  # Longer for code + explanation
                #     temperature=0.3,   # Lower temperature for more deterministic code
                #     top_p=0.9
                # )
                response = await self.hf_client.chat.complete_async(
                    messages=messages,
                    model=self.model_id,
                    max_tokens=2500,  # Longer for code + explanation
                    temperature=0.3,   # Lower temperature for more deterministic code
                    top_p=0.9
                )
                
                # return response["choices"][0]["message"]["content"]
                return response.choices[0].message.content

                
            except Exception as e:
                last_error = e
                # logger.error(f"Error generating LLM response: {str(e)}", exc_info=True)
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < 2:
                    await asyncio.sleep(2)
        
        logger.error(f"All retries failed: {str(last_error)}", exc_info=True)
        raise last_error
    
    async def _load_conversation_history(
        self,
        conversation_id: str,
        user_id: str
    ) -> Optional[List[Dict]]:
        """
        Load conversation history from database
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID
            
        Returns:
            List of messages or None if not found
        """
        try:
            result = await self.db.from_("codegen_conversations") \
                .select("role, content, created_at") \
                .eq("conversation_id", conversation_id) \
                .eq("user_id", user_id) \
                .order("created_at", desc=False) \
                .execute()
            
            if not result.data:
                return None
            
            return [
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": msg["created_at"]
                }
                for msg in result.data
            ]
            
        except Exception as e:
            logger.error(f"Error loading conversation history: {str(e)}", exc_info=True)
            raise
    
    async def _save_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str
    ):
        """
        Save message to database
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID
            role: Message role
            content: Message content
        """
        try:
            await self.db.from_("codegen_conversations").insert({
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            
        except Exception as e:
            logger.error(f"Error saving message: {str(e)}", exc_info=True)
            raise
    
    async def _save_generated_code(
        self,
        conversation_id: str,
        user_id: str,
        code: str,
        description: str
    ):
        """
        Save generated code for easy retrieval
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID
            code: Generated code
            description: Strategy description
        """
        try:
            await self.db.from_("generated_codes").insert({
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "user_id": user_id,
                "code": code,
                "description": description,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            
        except Exception as e:
            logger.error(f"Error saving generated code: {str(e)}", exc_info=True)
            raise


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

"""
# Initialize service
from huggingface_hub import InferenceClient
from supabase import create_client

hf_client = InferenceClient(token=HUGGING_FACE_TOKEN)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

codegen_service = CodeGenService(hf_client, supabase)

# Generate initial code
result = await codegen_service.generate_code(
    user_id="user_123",
    strategy_description="Create a mean reversion strategy using RSI. Buy when RSI < 30, sell when RSI > 70."
)

print(result["code"])
print(result["explanation"])
conversation_id = result["conversation_id"]

# Debug an error
result = await codegen_service.generate_code(
    user_id="user_123",
    strategy_description="I'm getting a KeyError on the 'close' column",
    conversation_id=conversation_id,
    previous_code=result["code"],
    error_message="KeyError: 'close'"
)

print("Fixed code:")
print(result["code"])

# Modify existing code
result = await codegen_service.generate_code(
    user_id="user_123",
    strategy_description="Add a stop loss at 2% below entry price",
    conversation_id=conversation_id,
    previous_code=result["code"]
)

print("Modified code:")
print(result["code"])

# List user's generated codes
codes = await codegen_service.list_generated_codes("user_123")
for code in codes:
    print(f"{code['created_at']}: {code['description']}")
"""
