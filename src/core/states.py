"""State definitions for the LangGraph state machine."""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Any


class ConversationState(Enum):
    """Possible states in the conversation flow."""
    IDLE = auto()           # Waiting for user input
    SEARCHING = auto()      # Querying vector DB for matching skills
    EXECUTING = auto()      # Running skill code
    LEARNING = auto()       # Interactive skill acquisition mode
    GENERATING = auto()     # LLM writing new skill
    RESPONDING = auto()     # Sending response to user


@dataclass
class AgentState:
    """Complete state of the agent during a conversation turn."""
    
    # User information
    user_id: int = 0
    chat_id: int = 0
    
    # Current message
    message: str = ""
    
    # Conversation state
    state: ConversationState = ConversationState.IDLE
    
    # Skill matching
    matched_skill: Optional[str] = None
    match_confidence: float = 0.0
    extracted_args: dict[str, Any] = field(default_factory=dict)
    
    # Execution results
    execution_result: Optional[str] = None
    execution_error: Optional[str] = None
    
    # Learning mode context
    learning_context: list[dict] = field(default_factory=list)
    pending_skill_code: Optional[str] = None
    
    # Response to send
    response: str = ""
    
    # Metadata
    is_authorized: bool = False
    
    def to_dict(self) -> dict:
        """Convert state to dictionary for LangGraph."""
        return {
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "message": self.message,
            "state": self.state.name,
            "matched_skill": self.matched_skill,
            "match_confidence": self.match_confidence,
            "extracted_args": self.extracted_args,
            "execution_result": self.execution_result,
            "execution_error": self.execution_error,
            "learning_context": self.learning_context,
            "pending_skill_code": self.pending_skill_code,
            "response": self.response,
            "is_authorized": self.is_authorized,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        """Create state from dictionary."""
        state = cls()
        for key, value in data.items():
            if key == "state":
                value = ConversationState[value]
            if hasattr(state, key):
                setattr(state, key, value)
        return state
