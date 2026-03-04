# """
# Mentor Service - Educational Q&A for Forex and Quantitative Finance
# Handles conversational interactions with conversation history persistence
# """

# import uuid
# from datetime import datetime
# from typing import List, Dict, Optional
# import logging
# import asyncio

# from prompts.mentor_system_prompt import MENTOR_SYSTEM_PROMPT

# logger = logging.getLogger(__name__)


# class MentorService:
#     """
#     Educational mentor service for forex and quantitative finance questions.
#     Maintains conversation history and provides structured educational responses.
#     """
    
#     def __init__(self, hf_client, db, model_id="mistralai/Mistral-7B-Instruct-v0.3"):
#         """
#         Initialize mentor service
        
#         Args:
#             hf_client: Hugging Face inference client
#             db: Database connection (Supabase or similar)
#             model_id: Hugging Face model ID to use
#         """
#         self.hf_client = hf_client
#         self.db = db
#         self.model_id = model_id
#         self.system_prompt = MENTOR_SYSTEM_PROMPT
#         self._deleted_conversations = set()
        
#     async def ask_question(
#         self,
#         user_id: str,
#         message: str,
#         conversation_id: Optional[str] = None
#     ) -> Dict:
#         """
#         Ask the mentor a question with conversation context
        
#         Args:
#             user_id: User's unique identifier
#             message: User's question
#             conversation_id: Optional conversation ID to continue existing chat
            
#         Returns:
#             Dict containing:
#                 - response: Mentor's answer
#                 - conversation_id: ID for continuing this conversation
#                 - message_count: Total messages in conversation
#         """
#         try:
#             # Load or create conversation
#             if conversation_id:
#                 logger.info(f"Loading conversation {conversation_id} for user {user_id}")
#                 history = await self._load_conversation_history(conversation_id, user_id)
#                 if history is None:
#                     # Conversation not found or doesn't belong to user
#                     logger.warning(f"Conversation {conversation_id} not found or unauthorized")
#                     conversation_id = str(uuid.uuid4())
#                     history = []
#             else:
#                 logger.info(f"Creating new conversation for user {user_id}")
#                 conversation_id = str(uuid.uuid4())
#                 history = []
            
#             # Build messages with full conversation history
#             messages = [
#                 {"role": "system", "content": self.system_prompt},
#                 *history,
#                 {"role": "user", "content": message}
#             ]
            
#             # Call LLM
#             logger.info(f"Generating response for conversation {conversation_id}")
#             response = await self._generate_response(messages)
            
#             # Save conversation to database
#             await self._save_message(conversation_id, user_id, "user", message)
#             await self._save_message(conversation_id, user_id, "assistant", response)
            
#             # Get updated message count
#             message_count = len(history) + 2  # +2 for current user message and response
            
#             logger.info(f"Successfully generated response for conversation {conversation_id}")
            
#             return {
#                 "response": response,
#                 "conversation_id": conversation_id,
#                 "message_count": message_count,
#                 "timestamp": datetime.utcnow().isoformat()
#             }
            
#         except Exception as e:
#             logger.error(f"Error in ask_question: {str(e)}", exc_info=True)
#             raise
    
#     async def get_conversation_history(
#         self,
#         conversation_id: str,
#         user_id: str
#     ) -> Optional[List[Dict]]:
#         """
#         Retrieve full conversation history
        
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
            
#             # Convert to user-friendly format
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
    
#     async def list_user_conversations(
#         self,
#         user_id: str,
#         limit: int = 20
#     ) -> List[Dict]:
#         """
#         List all conversations for a user
        
#         Args:
#             user_id: User's unique identifier
#             limit: Maximum number of conversations to return
            
#         Returns:
#             List of conversation summaries
#         """
#         try:
#             # Query database for user's conversations
#             result = await self.db.from_("mentor_conversations") \
#                 .select("conversation_id, created_at, content") \
#                 .eq("user_id", user_id) \
#                 .eq("role", "user") \
#                 .order("created_at", desc=True) \
#                 .limit(limit) \
#                 .execute()
            
#             # Group by conversation_id and get first message as preview
#             conversations = {}
#             for row in result.data:
#                 conv_id = row["conversation_id"]
#                 if conv_id not in conversations:
#                     conversations[conv_id] = {
#                         "conversation_id": conv_id,
#                         "started_at": row["created_at"],
#                         "preview": row["content"][:100] + "..." if len(row["content"]) > 100 else row["content"]
#                     }
            
#             # Get message counts
#             for conv_id in conversations:
#                 count_result = await self.db.from_("mentor_conversations") \
#                     .select("id", count="exact") \
#                     .eq("conversation_id", conv_id) \
#                     .execute()
#                 conversations[conv_id]["message_count"] = count_result.count
            
#             return list(conversations.values())
            
#         except Exception as e:
#             logger.error(f"Error listing conversations: {str(e)}", exc_info=True)
#             raise
    
#     async def delete_conversation(
#         self,
#         conversation_id: str,
#         user_id: str
#     ) -> bool:
#         """
#         Delete a conversation
        
#         Args:
#             conversation_id: Conversation to delete
#             user_id: User ID (for authorization)
            
#         Returns:
#             True if deleted, False if not found
#         """
#         try:
#             # Verify ownership
#             result = await self.db.from_("mentor_conversations") \
#                 .select("id") \
#                 .eq("conversation_id", conversation_id) \
#                 .eq("user_id", user_id) \
#                 .limit(1) \
#                 .execute()
            
#             if not result.data:
#                 logger.warning(f"Conversation {conversation_id} not found or unauthorized")
#                 return False
            
#             # Delete all messages in conversation
#             await self.db.from_("mentor_conversations") \
#                 .delete() \
#                 .eq("conversation_id", conversation_id) \
#                 .eq("user_id", user_id) \
#                 .execute()
            
#             logger.info(f"Deleted conversation {conversation_id}")
#             self._deleted_conversations.add(conversation_id)
#             return True
            
#         except Exception as e:
#             logger.error(f"Error deleting conversation: {str(e)}", exc_info=True)
#             raise
    
#     # ========================================================================
#     # PRIVATE HELPER METHODS
#     # ========================================================================
    
#     async def _generate_response(self, messages: List[Dict]) -> str:
#         """
#         Generate response from LLM
        
#         Args:
#             messages: Full conversation history including system prompt
            
#         Returns:
#             Generated response text
#         """
#         last_error = None

#         for attempt in range(3):
#             try:
#                 response = await self.hf_client.chat.complete_async(
#                     messages=messages,
#                     model=self.model_id,
#                     max_tokens=2000,  # Long educational answers
#                     temperature=0.7,   # Balanced creativity
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
#             user_id: User ID (for authorization)
            
#         Returns:
#             List of messages or None if not found
#         """
#         try:
#             if hasattr(self, "_deleted_conversations") and conversation_id in self._deleted_conversations:
#                 return []
        
#             # Query messages ordered by creation time
#             result = await self.db.from_("mentor_conversations") \
#                 .select("role, content, created_at") \
#                 .eq("conversation_id", conversation_id) \
#                 .eq("user_id", user_id) \
#                 .order("created_at", desc=False) \
#                 .execute()
            
#             if not result.data:
#                 # Check if conversation exists for ANY user
#                 check = await self.db.from_("mentor_conversations") \
#                     .select("id") \
#                     .eq("conversation_id", conversation_id) \
#                     .limit(1) \
#                     .execute()
#                 if not check.data:
#                     # Conversation truly does not exist (deleted)
#                     return []
#                 # Conversation exists but not for this user (unauthorized)
#                 return None
            
#             # Convert to message format (exclude system prompt from history)
#             history = [
#                 {
#                     "role": msg["role"],
#                     "content": msg["content"],
#                     "timestamp": msg["created_at"]
#                 }
#                 for msg in result.data
#             ]
            
#             return history
            
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
#         Save a single message to database
        
#         Args:
#             conversation_id: Conversation ID
#             user_id: User ID
#             role: Message role ('user' or 'assistant')
#             content: Message content
#         """
#         try:
#             await self.db.from_("mentor_conversations").insert({
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

"""
Mentor Service - Educational Q&A for Forex and Quantitative Finance
Handles multi-turn conversations with full history persistence.
DB calls use db.mentor repo from core.database.
"""

import uuid
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import logging

from prompts.mentor_system_prompt import MENTOR_SYSTEM_PROMPT
from core.database import db

logger = logging.getLogger(__name__)


class MentorService:
    """
    Educational mentor service for forex and quantitative finance questions.
    Maintains full conversation history per conversation_id.
    All database operations go through db.mentor (MentorRepo).
    """

    def __init__(self, mistral_client, model_id: str = "mistral-small-latest"):
        """
        Args:
            mistral_client: Mistral async client instance
            model_id:       Mistral model to use
        """
        self.client   = mistral_client
        self.model_id = model_id
        self.system_prompt = MENTOR_SYSTEM_PROMPT

        # In-memory set to track archived conversations in the current session
        self._archived_conversations: set = set()

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    async def ask_question(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
    ) -> Dict:
        try:
            # 1. Load existing conversation or start a new one
            if conversation_id:
                logger.info(f"Continuing conversation {conversation_id} for user {user_id}")
                history = self._load_history(conversation_id, user_id)
                if history is None:
                    logger.warning(f"Conversation {conversation_id} not found or unauthorized")
                    conversation_id = str(uuid.uuid4())
                    history = []
                    # INSERT HERE: The ID was missing or invalid, so we treat it as a new creation
                    db.mentor.create_conversation(id=conversation_id, user_id=user_id, title=message[:80])
            else:
                logger.info(f"Starting new conversation for user {user_id}")
                conversation_id = str(uuid.uuid4())
                history = []
                # INSERT HERE: This is a brand new conversation
                db.mentor.create_conversation(id=conversation_id, user_id=user_id, title=message[:80])

            # 2. Build full message array
            messages = [
                {"role": "system", "content": self.system_prompt},
                *history,
                {"role": "user", "content": message},
            ]

            # 3. Call Mistral
            response = await self._generate_response(messages)

            # 4. Persist both turns to DB
            # This will now succeed because the Foreign Key (conversation_id) exists!
            db.mentor.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=message,
            )
            db.mentor.add_message(
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=response,
            )
            
            # ... rest of the code

            message_count = len(history) + 2  # history + user msg + assistant msg

            logger.info(f"Response generated for conversation {conversation_id}")
            return {
                "response":        response,
                "conversation_id": conversation_id,
                "message_count":   message_count,
                "timestamp":       datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error in ask_question: {e}", exc_info=True)
            raise

    def list_user_conversations(self, user_id: str, limit: int = 20) -> List[Dict]:
        """
        List all conversations for a user (most recent first).
        Uses the mentor_history VIEW via MentorRepo.list_conversations.

        Returns list of:
            conversation_id, started_at, preview, message_count
        """
        try:
            rows = db.mentor.list_conversations(user_id=user_id, limit=limit)
            return [
                {
                    "conversation_id": r.get("conversation_id") or r.get("id"),
                    "started_at":      r.get("created_at"),
                    "preview":         r.get("preview", ""),
                    "message_count":   r.get("message_count", 0),
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Error listing conversations: {e}", exc_info=True)
            raise

    def get_conversation_history(
        self, conversation_id: str, user_id: str
    ) -> Optional[List[Dict]]:
        """
        Return the full message history for a conversation.
        Returns None if the conversation belongs to a different user.
        Returns [] if not found (e.g. was deleted).
        """
        try:
            history = self._load_history(conversation_id, user_id)
            if history is None:
                return None
            return [
                {
                    "role":      msg["role"],
                    "content":   msg["content"],
                    "timestamp": msg.get("timestamp", ""),
                }
                for msg in history
            ]
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}", exc_info=True)
            raise

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """
        Archive a conversation so it no longer appears in the user's list.
        Returns False if not found.
        """
        try:
            messages = db.mentor.get_history(conversation_id)
            if not messages:
                logger.warning(f"Conversation {conversation_id} not found")
                return False

            db.mentor.archive_conversation(conversation_id)
            self._archived_conversations.add(conversation_id)
            logger.info(f"Archived conversation {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"Error deleting conversation: {e}", exc_info=True)
            raise

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _load_history(self, conversation_id: str, user_id: str) -> Optional[List[Dict]]:
        """
        Load conversation messages from DB.

        Returns:
            List of message dicts if found and authorized
            []   if conversation was archived this session
            None if conversation belongs to a different user
        """
        # Skip DB call for conversations archived in this session
        if conversation_id in self._archived_conversations:
            return []

        messages = db.mentor.get_history(conversation_id)

        if not messages:
            return []

        # Authorization check — verify the first message belongs to this user
        first = db.mentor._msg \
            .select("user_id") \
            .eq("conversation_id", conversation_id) \
            .limit(1) \
            .execute()

        if first.data and first.data[0]["user_id"] != user_id:
            return None  # Belongs to another user

        return [
            {
                "role":      m["role"],
                "content":   m["content"],
                "timestamp": m.get("created_at", ""),
            }
            for m in messages
        ]

    async def _generate_response(self, messages: List[Dict]) -> str:
        """
        Call Mistral with up to 3 retries on transient errors.
        Uses temperature=0.7 for natural, varied educational responses.
        """
        last_error = None
        for attempt in range(3):
            try:
                response = await self.client.chat.complete_async(
                    model=self.model_id,
                    messages=messages,
                    max_tokens=2000,
                    temperature=0.7,
                    top_p=0.9,
                )
                return response.choices[0].message.content
            except Exception as e:
                last_error = e
                logger.warning(f"_generate_response attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2)

        logger.error(f"All retries exhausted: {last_error}", exc_info=True)
        raise last_error
