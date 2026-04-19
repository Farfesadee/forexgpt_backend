# """
# Code Generation Service - Strategy Translation with Conversational Debugging
# Handles initial code generation and follow-up troubleshooting conversations
# """

# import uuid
# from datetime import datetime
# from typing import Dict, Optional, List
# import logging
# from prompts.codegen_prompt import CODEGEN_SYSTEM_PROMPT
# import asyncio

# logger = logging.getLogger(__name__)


# class CodeGenService:
#     """
#     Code generation service with conversational debugging support.
#     Generates trading strategy code and helps troubleshoot issues.
#     """
    
#     def __init__(self, hf_client, db, model_id="mistralai/Mistral-7B-Instruct-v0.3"):
#         """
#         Initialize code generation service
        
#         Args:
#             hf_client: Hugging Face inference client
#             db: Database connection (Supabase or similar)
#         """
#         self.hf_client = hf_client
#         self.db = db
#         self.model_id = model_id
#         self.system_prompt = CODEGEN_SYSTEM_PROMPT
    
#     async def generate_code(
#         self,
#         user_id: str,
#         strategy_description: str,
#         conversation_id: Optional[str] = None,
#         previous_code: Optional[str] = None,
#         error_message: Optional[str] = None
#     ) -> Dict:
#         """
#         Generate or debug trading strategy code
        
#         Args:
#             user_id: User's unique identifier
#             strategy_description: Strategy description or debugging request
#             conversation_id: Optional conversation ID for follow-ups
#             previous_code: Previously generated code (for debugging)
#             error_message: Error message if debugging
            
#         Returns:
#             Dict containing:
#                 - code: Generated Python code
#                 - explanation: Brief explanation of the code
#                 - conversation_id: ID for follow-up questions
#                 - language: Programming language (always 'python')
#         """
#         try:
#             # Load or create conversation
#             if conversation_id:
#                 logger.info(f"Loading code gen conversation {conversation_id}")
#                 history = await self._load_conversation_history(conversation_id, user_id)
#                 if history is None:
#                     conversation_id = str(uuid.uuid4())
#                     history = []
#             else:
#                 logger.info(f"Creating new code gen conversation for user {user_id}")
#                 conversation_id = str(uuid.uuid4())
#                 history = []
            
#             # Build user message
#             user_message = self._build_user_message(
#                 strategy_description,
#                 previous_code,
#                 error_message
#             )
            
#             # Build messages with conversation history
#             messages = [
#                 {"role": "system", "content": self.system_prompt},
#                 *history,
#                 {"role": "user", "content": user_message}
#             ]
            
#             # Generate code
#             logger.info(f"Generating code for conversation {conversation_id}")
#             response = await self._generate_response(messages)
            
#             # Extract code and explanation from response
#             code, explanation = self._parse_response(response)
            
#             # Save to database
#             await self._save_message(
#                 conversation_id, 
#                 user_id, 
#                 "user", 
#                 user_message
#             )
#             await self._save_message(
#                 conversation_id,
#                 user_id,
#                 "assistant",
#                 response
#             )
            
#             # Save generated code separately for easy retrieval
#             await self._save_generated_code(
#                 conversation_id,
#                 user_id,
#                 code,
#                 strategy_description
#             )
            
#             logger.info(f"Successfully generated code for conversation {conversation_id}")
            
#             return {
#                 "code": code,
#                 "explanation": explanation,
#                 "conversation_id": conversation_id,
#                 "language": "python",
#                 "timestamp": datetime.utcnow().isoformat()
#             }
            
#         except Exception as e:
#             logger.error(f"Error in generate_code: {str(e)}", exc_info=True)
#             raise
    
#     async def get_conversation_history(
#         self,
#         conversation_id: str,
#         user_id: str
#     ) -> Optional[List[Dict]]:
#         """
#         Retrieve code generation conversation history
        
#         Args:
#             conversation_id: Conversation ID
#             user_id: User ID (for authorization)
            
#         Returns:
#             List of messages or None if not found
#         """
#         try:
#             history = await self._load_conversation_history(conversation_id, user_id)
#             if history is None:
#                 return None
            
#             return [
#                 {
#                     "role": msg["role"],
#                     "content": msg["content"],
#                     "timestamp": msg.get("timestamp", "")
#                 }
#                 for msg in history
#             ]
            
#         except Exception as e:
#             logger.error(f"Error retrieving conversation history: {str(e)}", exc_info=True)
#             raise
    
#     async def list_generated_codes(
#         self,
#         user_id: str,
#         limit: int = 20
#     ) -> List[Dict]:
#         """
#         List all code generations for a user
        
#         Args:
#             user_id: User's unique identifier
#             limit: Maximum number to return
            
#         Returns:
#             List of generated code summaries
#         """
#         try:
#             result = await self.db.from_("generated_codes") \
#                 .select("id, conversation_id, description, created_at") \
#                 .eq("user_id", user_id) \
#                 .order("created_at", desc=True) \
#                 .limit(limit) \
#                 .execute()
            
#             return [
#                 {
#                     "id": row["id"],
#                     "conversation_id": row["conversation_id"],
#                     "description": row["description"][:100] + "..." if len(row["description"]) > 100 else row["description"],
#                     "created_at": row["created_at"]
#                 }
#                 for row in result.data
#             ]
            
#         except Exception as e:
#             logger.error(f"Error listing generated codes: {str(e)}", exc_info=True)
#             raise
    
#     async def get_generated_code(
#         self,
#         code_id: str,
#         user_id: str
#     ) -> Optional[Dict]:
#         """
#         Retrieve a specific generated code
        
#         Args:
#             code_id: Code generation ID
#             user_id: User ID (for authorization)
            
#         Returns:
#             Dict with code details or None if not found
#         """
#         try:
#             result = await self.db.from_("generated_codes") \
#                 .select("*") \
#                 .eq("id", code_id) \
#                 .eq("user_id", user_id) \
#                 .single() \
#                 .execute()
            
#             if not result.data:
#                 return None
            
#             return {
#                 "id": result.data["id"],
#                 "code": result.data["code"],
#                 "description": result.data["description"],
#                 "conversation_id": result.data["conversation_id"],
#                 "created_at": result.data["created_at"]
#             }
            
#         except Exception as e:
#             logger.error(f"Error retrieving generated code: {str(e)}", exc_info=True)
#             raise
    
#     # ========================================================================
#     # PRIVATE HELPER METHODS
#     # ========================================================================
    
#     def _build_user_message(
#         self,
#         description: str,
#         previous_code: Optional[str],
#         error_message: Optional[str]
#     ) -> str:
#         """
#         Build user message based on context
        
#         Args:
#             description: Strategy description or debugging request
#             previous_code: Previously generated code
#             error_message: Error message if debugging
            
#         Returns:
#             Formatted user message
#         """
#         if error_message and previous_code:
#             # Debugging scenario
#             return f"""I got an error with the code you generated. Please help me fix it.

# Previous code:
# ```python
# {previous_code}
# ```

# Error message:
# ```
# {error_message}
# ```

# Issue: {description}

# Please provide the corrected code and explain what was wrong."""
        
#         elif previous_code:
#             # Modification request
#             return f"""I need to modify the previous code.

# Current code:
# ```python
# {previous_code}
# ```

# Requested changes: {description}

# Please provide the updated code."""
        
#         else:
#             # Initial generation
#             return f"""Please generate Python code for the following trading strategy:

# {description}

# Requirements:
# • Use pandas for data handling
# • Include clear entry and exit logic
# • Add proper risk management
# • Make it backtesting-ready
# • Include docstrings and comments"""
    
#     def _parse_response(self, response: str) -> tuple[str, str]:
#         """
#         Extract code and explanation from LLM response
        
#         Args:
#             response: Full LLM response
            
#         Returns:
#             Tuple of (code, explanation)
#         """
#         # Look for code blocks
#         if "```python" in response:
#             # Extract code between ```python and ```
#             start = response.find("```python") + len("```python")
#             end = response.find("```", start)
#             code = response[start:end].strip()
            
#             # Everything else is explanation
#             explanation = response[:response.find("```python")] + response[end + 3:]
#             explanation = explanation.strip()
        
#         elif "```" in response:
#             # Generic code block
#             start = response.find("```") + 3
#             end = response.find("```", start)
#             code = response[start:end].strip()
            
#             explanation = response[:response.find("```")] + response[end + 3:]
#             explanation = explanation.strip()
        
#         else:
#             # No code blocks found - treat entire response as code
#             code = response.strip()
#             explanation = "Generated trading strategy code."
        
#         return code, explanation
    
#     async def _generate_response(self, messages: List[Dict]) -> str:
#         """
#         Generate response from LLM
        
#         Args:
#             messages: Conversation history
            
#         Returns:
#             Generated response
#         """
#         last_error =None

#         for attempt in range(3):
#             try:
#                 # response = await self.hf_client.chat_completetion(
#                 #     messages=messages,
#                 #     model=self.model_id,
#                 #     max_tokens=2500,  # Longer for code + explanation
#                 #     temperature=0.3,   # Lower temperature for more deterministic code
#                 #     top_p=0.9
#                 # )
#                 response = await self.hf_client.chat.complete_async(
#                     messages=messages,
#                     model=self.model_id,
#                     max_tokens=2500,  # Longer for code + explanation
#                     temperature=0.3,   # Lower temperature for more deterministic code
#                     top_p=0.9
#                 )
                
#                 # return response["choices"][0]["message"]["content"]
#                 return response.choices[0].message.content

                
#             except Exception as e:
#                 last_error = e
#                 # logger.error(f"Error generating LLM response: {str(e)}", exc_info=True)
#                 logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
#                 if attempt < 2:
#                     await asyncio.sleep(2)
        
#         logger.error(f"All retries failed: {str(last_error)}", exc_info=True)
#         raise last_error
    
#     async def _load_conversation_history(
#         self,
#         conversation_id: str,
#         user_id: str
#     ) -> Optional[List[Dict]]:
#         """
#         Load conversation history from database
        
#         Args:
#             conversation_id: Conversation ID
#             user_id: User ID
            
#         Returns:
#             List of messages or None if not found
#         """
#         try:
#             result = await self.db.from_("codegen_conversations") \
#                 .select("role, content, created_at") \
#                 .eq("conversation_id", conversation_id) \
#                 .eq("user_id", user_id) \
#                 .order("created_at", desc=False) \
#                 .execute()
            
#             if not result.data:
#                 return None
            
#             return [
#                 {
#                     "role": msg["role"],
#                     "content": msg["content"],
#                     "timestamp": msg["created_at"]
#                 }
#                 for msg in result.data
#             ]
            
#         except Exception as e:
#             logger.error(f"Error loading conversation history: {str(e)}", exc_info=True)
#             raise
    
#     async def _save_message(
#         self,
#         conversation_id: str,
#         user_id: str,
#         role: str,
#         content: str
#     ):
#         """
#         Save message to database
        
#         Args:
#             conversation_id: Conversation ID
#             user_id: User ID
#             role: Message role
#             content: Message content
#         """
#         try:
#             await self.db.from_("codegen_conversations").insert({
#                 "id": str(uuid.uuid4()),
#                 "conversation_id": conversation_id,
#                 "user_id": user_id,
#                 "role": role,
#                 "content": content,
#                 "created_at": datetime.utcnow().isoformat()
#             }).execute()
            
#         except Exception as e:
#             logger.error(f"Error saving message: {str(e)}", exc_info=True)
#             raise
    
#     async def _save_generated_code(
#         self,
#         conversation_id: str,
#         user_id: str,
#         code: str,
#         description: str
#     ):
#         """
#         Save generated code for easy retrieval
        
#         Args:
#             conversation_id: Conversation ID
#             user_id: User ID
#             code: Generated code
#             description: Strategy description
#         """
#         try:
#             await self.db.from_("generated_codes").insert({
#                 "id": str(uuid.uuid4()),
#                 "conversation_id": conversation_id,
#                 "user_id": user_id,
#                 "code": code,
#                 "description": description,
#                 "created_at": datetime.utcnow().isoformat()
#             }).execute()
            
#         except Exception as e:
#             logger.error(f"Error saving generated code: {str(e)}", exc_info=True)
#             raise


"""
Code Generation Service - Strategy Translation with Conversational Debugging
Handles initial generation, debugging, and modification of trading strategy code.
DB calls use public.generated_codes and public.codegen_conversations.
"""

import uuid
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from prompts.codegen_prompt import CODEGEN_SYSTEM_PROMPT
import logging

from core.database import get_db
from services.ai_errors import (
    AIServiceUnavailableError,
    is_capacity_exceeded_error,
    is_temporary_ai_unavailable_error,
)

logger = logging.getLogger(__name__)

_PROMPT_ECHO_MARKERS = (
    "ORIGINAL CODE:",
    "BACKTEST RESULTS:",
    "EXPERT ANALYSIS:",
    "ADDITIONAL REQUIREMENTS:",
    "Please improve this strategy.",
)


def _normalize_timestamp(value) -> str:
    """
    Normalize DB timestamp values to ISO format (includes year).
    Keeps original value only when it cannot be parsed.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ""
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).isoformat()
        except ValueError:
            return raw
    return str(value)


class CodeGenService:
    """
    Code generation service with conversational debugging support.
    All DB operations go through:
      - get_db().table("generated_codes")
      - get_db().table("codegen_conversations")

    Three scenarios handled by generate_code():
        1. Initial generation  -- no previous_code
        2. Debugging           -- previous_code + error_message
        3. Modification        -- previous_code, no error_message
    """

    def __init__(
        self,
        mistral_client,
        model_id: str = "codestral-latest",
        fallback_model_ids: Optional[List[str]] = None,
    ):
        self.client        = mistral_client
        self.model_id      = model_id
        self.fallback_model_ids = [
            fallback_model_id.strip()
            for fallback_model_id in (fallback_model_ids or [])
            if fallback_model_id and fallback_model_id.strip() and fallback_model_id.strip() != model_id
        ]
        self.system_prompt = CODEGEN_SYSTEM_PROMPT

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    async def generate_code(
        self,
        user_id: str,
        strategy_description: str,
        conversation_id: Optional[str] = None,
        previous_code: Optional[str] = None,
        error_message: Optional[str] = None,
        llm_user_message: Optional[str] = None,
        stored_user_message: Optional[str] = None,
        stored_description: Optional[str] = None,
    ) -> Dict:
        """
        Generate, debug, or modify trading strategy code.

        Returns:
            code, explanation, conversation_id, code_id, language, timestamp
        """
        try:
            # Load or create conversation
            if conversation_id:
                logger.info(f"Continuing codegen conversation {conversation_id}")
                history = self._load_history(conversation_id, user_id)
                if history is None:
                    conversation_id = str(uuid.uuid4())
                    history = []
            else:
                logger.info(f"Starting new codegen conversation for user {user_id}")
                conversation_id = str(uuid.uuid4())
                history = []

            llm_message = llm_user_message or self._build_user_message(
                strategy_description, previous_code, error_message
            )
            persisted_user_message = stored_user_message or llm_message
            persisted_description = stored_description or strategy_description

            messages = [
                {"role": "system", "content": self.system_prompt},
                *history,
                {"role": "user", "content": llm_message},
            ]

            response = await self._generate_response(messages)
            code, explanation = self._parse_response(response)

            # Persist conversation turns
            self._save_message(conversation_id, user_id, "user", persisted_user_message)
            self._save_message(conversation_id, user_id, "assistant", response)

            # Save generated code to generated_codes table
            saved = (
                get_db().table("generated_codes")
                .insert({
                    "id":              str(uuid.uuid4()),
                    "user_id":         user_id,
                    "conversation_id": conversation_id,
                    "code":            code,
                    "description":     persisted_description,
                    "created_at":      datetime.utcnow().isoformat(),
                })
                .execute()
            )
            saved_row = saved.data[0] if saved and saved.data else {}

            logger.info(f"Code generated for conversation {conversation_id}")
            return {
                "code":            code,
                "explanation":     explanation,
                "conversation_id": conversation_id,
                "code_id":         saved_row.get("id"),
                "language":        "python",
                "timestamp":       datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error in generate_code: {e}", exc_info=True)
            raise

    async def list_generated_codes(self, user_id: str, limit: int = 100) -> List[Dict]:
        """List all generated strategy codes for a user (most recent first)."""
        try:
            result = (
                get_db().table("generated_codes")
                .select("id, conversation_id, description, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            rows = result.data or []
            return [
                {
                    "id":              r["id"],
                    "conversation_id": r.get("conversation_id"),
                    "description":     (r.get("description") or "")[:100],
                    "created_at":      _normalize_timestamp(r.get("created_at")),
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Error listing generated codes: {e}", exc_info=True)
            raise

    # async def list_user_conversations(self, user_id: str, limit: int = 20) -> List[Dict]:
    #     """
    #     List unique logic sessions for a user (most recent first).
    #     Groups by conversation_id.
    #     """
    #     try:
    #         # First, get the unique conversation IDs and their latest message
    #         result = (
    #             get_db().table("codegen_conversations")
    #             .select("conversation_id, content, created_at")
    #             .eq("user_id", user_id)
    #             .order("created_at", desc=True)
    #             .execute()
    #         )
    #         rows = result.data or []
    #         return [
    #             {
    #                 "id":          r["id"],
    #                 "conversation_id": r.get("conversation_id"),
    #                 "description": (r.get("description") or "")[:100],
    #                 "created_at":  _normalize_timestamp(r.get("created_at")),
    #             }
    #             for r in rows
    #         ]
    #     except Exception as e:
    #         logger.error(f"Error listing logic sessions: {e}", exc_info=True)
    #         raise

    async def get_generated_code(self, code_id: str, user_id: str) -> Optional[Dict]:
        """Return a specific strategy by ID. None if not found or unauthorized."""
        try:
            result = (
                get_db().table("generated_codes")
                .select("*")
                .eq("id", code_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            row = result.data[0]
            return {
                "id":              row["id"],
                "code":            row.get("code"),
                "description":     row.get("description"),
                "conversation_id": row.get("conversation_id"),
                "created_at":      _normalize_timestamp(row.get("created_at")),
            }
        except Exception as e:
            logger.error(f"Error retrieving generated code: {e}", exc_info=True)
            raise

    async def get_conversation_history(
        self, conversation_id: str, user_id: str
    ) -> Optional[List[Dict]]:
        """Return full message history. None if unauthorized, [] if not found."""
        try:
            history = self._load_history(conversation_id, user_id)
            if history is None:
                return None

            result = []
            for m in history:
                extracted_code = None
                if m["role"] == "assistant":
                    extracted_code, _ = self._parse_response(m["content"])
                    if not extracted_code or extracted_code == m["content"].strip():
                        extracted_code = None

                msg = {
                    "role":      m["role"],
                    "content":   m["content"],
                    "timestamp": _normalize_timestamp(m.get("timestamp")),
                    "code":      extracted_code,
                }
                result.append(msg)

            return result
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}", exc_info=True)
            raise

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """
        Delete all messages in a conversation.
        Returns False if conversation not found or unauthorized.
        """
        try:
            # Check conversation exists and belongs to user
            history = self._load_history(conversation_id, user_id)
            if history is None:
                return False  # Unauthorized
            if len(history) == 0:
                return False  # Not found

            # Delete all messages in the conversation
            get_db().table("codegen_conversations") \
                .delete() \
                .eq("conversation_id", conversation_id) \
                .eq("user_id", user_id) \
                .execute()

            logger.info(f"Deleted conversation {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            raise

    async def generate_improvement(
        self,
        user_id: str,
        original_code: str,
        backtest_results: Dict[str, Any],
        mentor_analysis: str,
        additional_requirements: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate improved strategy based on backtest results and mentor feedback.
        
        This is essentially a wrapper around generate_code() that builds a specific
        user message for improvement mode. All the actual work (calling Mistral,
        saving to DB, parsing response) is handled by generate_code().
        """
        
        # Build improvement mode user message
        improvement_message = self._build_improvement_message(
            original_code=original_code,
            backtest_results=backtest_results,
            mentor_analysis=mentor_analysis,
            additional_requirements=additional_requirements
        )
        stored_summary = self._build_improvement_summary(
            backtest_results=backtest_results,
            additional_requirements=additional_requirements,
        )

        # Keep the full prompt for the LLM, but persist a concise user-facing summary
        # so the frontend does not prefill the entire mentor response later.
        result = await self.generate_code(
            user_id=user_id,
            strategy_description=stored_summary,
            conversation_id=conversation_id,
            llm_user_message=improvement_message,
            stored_user_message=stored_summary,
            stored_description=stored_summary,
        )

        return result


    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _save_message(
        self, conversation_id: str, user_id: str, role: str, content: str
    ) -> None:
        """Persist a single conversation turn to codegen_conversations table."""
        try:
            get_db().table("codegen_conversations").insert({
                "id":              str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "user_id":         user_id,
                "role":            role,
                "content":         content,
                "created_at":      datetime.utcnow().isoformat(),
            }).execute()
        except Exception as e:
            logger.error(f"Error saving codegen message: {e}", exc_info=True)
            # Non-fatal -- conversation continues even if save fails

    def _load_history(
        self, conversation_id: str, user_id: str
    ) -> Optional[List[Dict]]:
        """
        Load codegen messages from DB.
        Returns [] if not found, None if unauthorized.
        """
        try:
            result = (
                get_db().table("codegen_conversations")
                .select("role, content, created_at, user_id")
                .eq("conversation_id", conversation_id)
                .order("created_at")
                .execute()
            )

            if not result.data:
                return []

            # Authorization check
            if result.data[0]["user_id"] != user_id:
                return None

            return [
                {
                    "role":      m["role"],
                    "content":   m["content"],
                    "timestamp": _normalize_timestamp(m.get("created_at")),
                }
                for m in result.data
            ]
        except Exception as e:
            logger.error(f"Error loading codegen history: {e}", exc_info=True)
            return []

    def _build_user_message(
        self,
        description: str,
        previous_code: Optional[str],
        error_message: Optional[str],
    ) -> str:
        """Build the correct prompt for each scenario."""
        if error_message and previous_code:
            # Scenario 2 -- Debugging
            return (
                f"I got an error with the code you generated. Please help me fix it.\n\n"
                f"Previous code:\n```python\n{previous_code}\n```\n\n"
                f"Error message:\n```\n{error_message}\n```\n\n"
                f"Issue: {description}\n\n"
                f"Please provide the corrected code and explain what was wrong."
            )
        elif previous_code:
            # Scenario 3 -- Modification
            return (
                f"I need to modify the previous code.\n\n"
                f"Current code:\n```python\n{previous_code}\n```\n\n"
                f"Requested changes: {description}\n\n"
                f"Please provide the updated code."
            )
        else:
            # Scenario 1 -- Initial generation
            return (
                f"Please generate Python code for the following trading strategy:\n\n"
                f"{description}\n\n"
                f"Requirements:\n"
                f"- Use pandas for data handling\n"
                f"- Include clear entry and exit logic\n"
                f"- Add proper risk management\n"
                f"- Make it backtesting-ready\n"
                f"- Include docstrings and comments"
            )
        
    def _normalize_code(self, code: str) -> str:
        """
        Auto-fix common indentation errors from LLM-generated code.
        Specifically targets lines that dropped to column 0 inside a function body.
        """
        import ast

        # First try — if code is already valid, return as-is
        try:
            ast.parse(code)
            return code
        except SyntaxError:
            pass

        lines = code.split("\n")
        fixed = []
        indent_stack = [0]  # track expected indentation levels
        inside_function = False
        expected_indent = 0

        for i, line in enumerate(lines):
            stripped = line.lstrip()

            # Blank lines pass through
            if not stripped:
                fixed.append(line)
                continue

            current_indent = len(line) - len(stripped)

            # Detect function/class definition — sets context
            if stripped.startswith(("def ", "class ")):
                inside_function = True
                expected_indent = current_indent + 4
                indent_stack = [current_indent]
                fixed.append(line)
                continue

            # If inside a function and line dropped to column 0 unexpectedly
            if inside_function and current_indent == 0 and not stripped.startswith(("def ", "class ", "#", "@")):
                # Re-indent to expected level
                fixed.append(" " * expected_indent + stripped)
            else:
                fixed.append(line)

        fixed_code = "\n".join(fixed)

        # Validate — if still broken, return original and let it fail naturally
        try:
            ast.parse(fixed_code)
            return fixed_code
        except SyntaxError:
            return code

    def _parse_response(self, response: str) -> Tuple[str, str]:
        """Split model response into (code, explanation)."""
        response = self._clean_response_text(response)

        if "```python" in response:
            start = response.find("```python") + len("```python")
            end   = response.find("```", start)
            code  = response[start:end].strip()
            explanation = (response[:response.find("```python")] + response[end + 3:]).strip()
        elif "```" in response:
            start = response.find("```") + 3
            end   = response.find("```", start)
            code  = response[start:end].strip()
            explanation = (response[:response.find("```")] + response[end + 3:]).strip()
        else:
            code        = response.strip()
            explanation = "Generated trading strategy code."

        code = self._normalize_code(code)
        return code, explanation

    async def _generate_response(self, messages: List[Dict]) -> str:
        """Call Mistral with retries and optional model fallback."""
        last_error = None
        model_ids = [self.model_id, *self.fallback_model_ids]

        for model_index, model_id in enumerate(model_ids):
            for attempt in range(2):
                try:
                    response = await self.client.chat.complete_async(
                        model=model_id,
                        messages=messages,
                        max_tokens=2500,
                        temperature=0.3,
                        top_p=0.9,
                    )
                    cleaned_text = self._clean_response_text(
                        response.choices[0].message.content
                    )
                    if not cleaned_text:
                        raise ValueError("Code generation returned an empty response.")
                    if model_id != self.model_id:
                        logger.info("Codegen request succeeded with fallback model %s", model_id)
                    return cleaned_text
                except Exception as e:
                    last_error = e
                    is_capacity_error = is_capacity_exceeded_error(e)
                    logger.warning(
                        "_generate_response attempt %s failed for model %s: %s",
                        attempt + 1,
                        model_id,
                        e,
                    )

                    if is_capacity_error and model_index < len(model_ids) - 1:
                        logger.info(
                            "Primary codegen model %s is at capacity; trying fallback model %s",
                            model_id,
                            model_ids[model_index + 1],
                        )
                        break

                    if attempt < 1:
                        await asyncio.sleep(1 + attempt)

        logger.error(f"All retries exhausted: {last_error}", exc_info=True)
        if last_error and is_temporary_ai_unavailable_error(last_error):
            raise AIServiceUnavailableError(
                "The code generation model is temporarily at capacity. Please try again in a moment."
            )
        raise last_error
    
    def _build_improvement_message(
        self,
        original_code: str,
        backtest_results: Dict[str, Any],
        mentor_analysis: str,
        additional_requirements: Optional[str] = None
    ) -> str:
        """
        Build the user message for improvement mode.
        
        This message triggers the IMPROVEMENT MODE section in the system prompt.
        """
        
        message = f"""I backtested this strategy and it underperformed:

ORIGINAL CODE:
```python
{original_code}
```

BACKTEST RESULTS:
- Strategy: {backtest_results.get('strategy_name', 'N/A')}
- Currency Pair: {backtest_results.get('pair', 'N/A')}
- Period: {backtest_results.get('start_date', 'N/A')} to {backtest_results.get('end_date', 'N/A')}
- Total Return: {backtest_results.get('total_return_pct', 'N/A')}%
- Sharpe Ratio: {backtest_results.get('sharpe_ratio', 'N/A')}
- Sortino Ratio: {backtest_results.get('sortino_ratio', 'N/A')}
- Max Drawdown: {backtest_results.get('max_drawdown_pct', 'N/A')}%
- Win Rate: {backtest_results.get('win_rate_pct', 'N/A')}%
- Total Trades: {backtest_results.get('total_trades', 'N/A')}
- Profit Factor: {backtest_results.get('profit_factor', 'N/A')}
- Average Risk/Reward: {backtest_results.get('avg_risk_reward', 'N/A')}
- CAGR: {backtest_results.get('cagr_pct', 'N/A')}%
- Annual Volatility: {backtest_results.get('volatility_annual_pct', 'N/A')}%

EXPERT ANALYSIS:
{mentor_analysis}
Please improve this strategy. Focus on:
1. Adding filters to avoid unfavorable market conditions
2. Improving risk management (stop losses, position sizing)
3. Optimizing entry/exit logic
"""
        if additional_requirements:
            message += f"\nADDITIONAL REQUIREMENTS:\n{additional_requirements}\n"
    
        message += """
Provide:
1. The improved code (complete, runnable)
2. Explanation of what changed and why
3. Expected improvements in metrics"""
    
        return message

    def _build_improvement_summary(
        self,
        backtest_results: Dict[str, Any],
        additional_requirements: Optional[str] = None,
    ) -> str:
        strategy_name = backtest_results.get("strategy_name") or "strategy"
        pair = backtest_results.get("pair") or "selected pair"
        total_return = backtest_results.get("total_return_pct")
        summary = (
            f"Improve my {strategy_name} strategy for {pair} "
            f"based on the latest backtest and mentor feedback"
        )
        if total_return is not None:
            summary += f" (return: {total_return}%)"
        if additional_requirements:
            summary += f". Extra requirements: {additional_requirements}"
        return summary

    def _clean_response_text(self, response: Optional[str]) -> str:
        text = (response or "").strip()
        if not text:
            return ""

        text = self._collapse_duplicate_paragraphs(text)

        first_code_block = text.find("```")
        if first_code_block > 0:
            prefix = text[:first_code_block]
            if any(marker in prefix for marker in _PROMPT_ECHO_MARKERS):
                text = text[first_code_block:].lstrip()

        return text.strip()

    @staticmethod
    def _collapse_duplicate_paragraphs(text: str) -> str:
        parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not parts:
            return text.strip()

        deduped_parts: List[str] = []
        for part in parts:
            if not deduped_parts or part != deduped_parts[-1]:
                deduped_parts.append(part)
        return "\n\n".join(deduped_parts)
