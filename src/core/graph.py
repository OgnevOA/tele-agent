"""LangGraph state machine for conversation flow."""

import logging
from typing import TypedDict, Annotated, Literal
from operator import add

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.core.states import ConversationState, AgentState
from src.skills.parser import SkillParser
from src.skills.executor import SkillExecutor
from src.llm.manager import ProviderManager
from src.retrieval.vectorstore import VectorStore

logger = logging.getLogger(__name__)


class GraphState(TypedDict):
    """State passed through the graph."""
    user_id: int
    chat_id: int
    message: str
    conversation_state: str
    is_authorized: bool
    
    # Skill matching
    matched_skill: str | None
    match_confidence: float
    extracted_args: dict
    
    # Execution
    execution_result: str | None
    execution_error: str | None
    
    # Learning mode
    learning_context: Annotated[list[dict], add]
    pending_skill_code: str | None
    
    # Response
    response: str
    
    # Control flow
    next_action: str


class ConversationGraph:
    """LangGraph-based conversation flow manager."""
    
    # Confidence thresholds
    HIGH_CONFIDENCE = 0.8
    MEDIUM_CONFIDENCE = 0.6
    
    def __init__(
        self,
        provider_manager: ProviderManager,
        vector_store: VectorStore,
        skill_parser: SkillParser,
        admin_id: int,
    ):
        """Initialize conversation graph.
        
        Args:
            provider_manager: LLM provider manager.
            vector_store: Vector store for skill search.
            skill_parser: Skill file parser.
            admin_id: Admin Telegram user ID.
        """
        self.provider_manager = provider_manager
        self.vector_store = vector_store
        self.skill_parser = skill_parser
        self.admin_id = admin_id
        self.executor = SkillExecutor(timeout=30)
        
        # Build the graph
        self.graph = self._build_graph()
        self.memory = MemorySaver()
        self.app = self.graph.compile(checkpointer=self.memory)
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        graph = StateGraph(GraphState)
        
        # Add nodes
        graph.add_node("auth_check", self._auth_check)
        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("search_skills", self._search_skills)
        graph.add_node("execute_skill", self._execute_skill)
        graph.add_node("general_chat", self._general_chat)
        graph.add_node("initiate_learning", self._initiate_learning)
        graph.add_node("process_learning", self._process_learning)
        graph.add_node("generate_skill", self._generate_skill)
        graph.add_node("test_skill", self._test_skill)
        graph.add_node("save_skill", self._save_skill)
        
        # Set entry point
        graph.set_entry_point("auth_check")
        
        # Add edges
        graph.add_conditional_edges(
            "auth_check",
            self._route_after_auth,
            {
                "authorized": "classify_intent",
                "unauthorized": END,
            }
        )
        
        graph.add_conditional_edges(
            "classify_intent",
            self._route_after_classify,
            {
                "search": "search_skills",
                "learning": "process_learning",
                "chat": "general_chat",
            }
        )
        
        graph.add_conditional_edges(
            "search_skills",
            self._route_after_search,
            {
                "execute": "execute_skill",
                "learn": "initiate_learning",
                "chat": "general_chat",
            }
        )
        
        graph.add_edge("execute_skill", END)
        graph.add_edge("general_chat", END)
        graph.add_edge("initiate_learning", END)
        
        graph.add_conditional_edges(
            "process_learning",
            self._route_after_learning,
            {
                "generate": "generate_skill",
                "continue": END,
                "cancel": END,
            }
        )
        
        graph.add_edge("generate_skill", "test_skill")
        
        graph.add_conditional_edges(
            "test_skill",
            self._route_after_test,
            {
                "save": "save_skill",
                "retry": END,
            }
        )
        
        graph.add_edge("save_skill", END)
        
        return graph
    
    # Node implementations
    
    async def _auth_check(self, state: GraphState) -> GraphState:
        """Check if user is authorized."""
        state["is_authorized"] = state["user_id"] == self.admin_id
        return state
    
    async def _classify_intent(self, state: GraphState) -> GraphState:
        """Classify user intent as task, learning response, or chat."""
        message = state["message"]
        
        # Check if in learning mode (has context)
        if state.get("learning_context"):
            state["next_action"] = "learning"
            return state
        
        # Use LLM to classify
        provider = self.provider_manager.get_active()
        
        prompt = f"""Classify this message as either:
- "task": A request to do something specific (check weather, send email, etc.)
- "chat": General conversation, greeting, or question

Message: "{message}"

Reply with only "task" or "chat"."""

        try:
            response = await provider.generate([
                {"role": "system", "content": "You classify messages. Reply with only one word."},
                {"role": "user", "content": prompt},
            ])
            
            if "task" in response.lower():
                state["next_action"] = "search"
            else:
                state["next_action"] = "chat"
                
        except Exception as e:
            logger.error(f"Classification error: {e}")
            state["next_action"] = "chat"
        
        return state
    
    async def _search_skills(self, state: GraphState) -> GraphState:
        """Search for matching skills."""
        message = state["message"]
        
        try:
            matches = await self.vector_store.search(message, top_k=1)
            
            if matches:
                best_match = matches[0]
                state["matched_skill"] = best_match["name"]
                state["match_confidence"] = best_match["score"]
                
                if best_match["score"] >= self.HIGH_CONFIDENCE:
                    state["next_action"] = "execute"
                elif best_match["score"] >= self.MEDIUM_CONFIDENCE:
                    # For medium confidence, still try to execute
                    state["next_action"] = "execute"
                else:
                    state["next_action"] = "learn"
            else:
                state["next_action"] = "learn"
                
        except Exception as e:
            logger.error(f"Search error: {e}")
            state["next_action"] = "chat"
        
        return state
    
    async def _execute_skill(self, state: GraphState) -> GraphState:
        """Execute matched skill."""
        skill_name = state["matched_skill"]
        message = state["message"]
        
        skill = self.skill_parser.get_skill(skill_name)
        if not skill:
            state["response"] = f"Error: Skill '{skill_name}' not found."
            return state
        
        # Extract arguments using LLM
        args = await self._extract_arguments(message, skill.code)
        state["extracted_args"] = args
        
        # Execute
        result = self.executor.execute(skill, args)
        
        if result.success:
            state["execution_result"] = str(result.result)
            state["response"] = str(result.result)
        else:
            state["execution_error"] = result.error
            state["response"] = f"Error executing skill: {result.error}"
        
        return state
    
    async def _general_chat(self, state: GraphState) -> GraphState:
        """Handle general conversation."""
        message = state["message"]
        provider = self.provider_manager.get_active()
        
        try:
            response = await provider.generate([
                {"role": "system", "content": "You are a helpful personal assistant. Be concise and friendly."},
                {"role": "user", "content": message},
            ])
            state["response"] = response
        except Exception as e:
            state["response"] = f"I encountered an error: {e}"
        
        return state
    
    async def _initiate_learning(self, state: GraphState) -> GraphState:
        """Start learning mode for new skill."""
        state["response"] = (
            "I don't have a skill for that yet. "
            "Can you teach me how to do it?\n\n"
            "What API or method should I use?"
        )
        state["learning_context"] = [{"role": "user", "content": state["message"]}]
        return state
    
    async def _process_learning(self, state: GraphState) -> GraphState:
        """Process learning mode response."""
        message = state["message"].lower()
        
        # Check for cancel
        if message in ("cancel", "stop", "nevermind", "forget it"):
            state["response"] = "Learning cancelled."
            state["learning_context"] = []
            state["next_action"] = "cancel"
            return state
        
        # Add to context
        context = state.get("learning_context", [])
        context.append({"role": "user", "content": state["message"]})
        state["learning_context"] = context
        
        # Check if we have enough info to generate
        if len(context) >= 2:
            state["next_action"] = "generate"
        else:
            state["response"] = "I need more details. What library or API should I use?"
            state["next_action"] = "continue"
        
        return state
    
    async def _generate_skill(self, state: GraphState) -> GraphState:
        """Generate a new skill from learning context."""
        from src.skills.generator import SkillGenerator
        
        generator = SkillGenerator(self.provider_manager)
        
        # Get original request
        original = state["learning_context"][0]["content"] if state["learning_context"] else ""
        
        try:
            skill = await generator.generate_skill(
                original_request=original,
                teaching_context=state["learning_context"],
            )
            
            if skill:
                state["pending_skill_code"] = skill.code
                state["matched_skill"] = skill.name
            else:
                state["response"] = "I couldn't generate the skill. Can you provide more details?"
                
        except Exception as e:
            logger.error(f"Skill generation error: {e}")
            state["response"] = f"Error generating skill: {e}"
        
        return state
    
    async def _test_skill(self, state: GraphState) -> GraphState:
        """Test the generated skill."""
        from src.skills.parser import Skill
        from datetime import datetime
        
        code = state.get("pending_skill_code", "")
        if not code:
            state["next_action"] = "retry"
            state["response"] = "No skill code to test."
            return state
        
        # Create temporary skill for testing
        skill = Skill(
            title="Test Skill",
            description="Testing",
            dependencies=[],
            code=code,
            file_path=self.skill_parser.skills_dir / "temp_test.md",
            created=datetime.now().strftime("%Y-%m-%d"),
        )
        
        result = self.executor.test_skill(skill)
        
        if result.success:
            state["next_action"] = "save"
            state["execution_result"] = str(result.result)
        else:
            state["next_action"] = "retry"
            state["execution_error"] = result.error
            state["response"] = (
                f"I tried to create the skill but got an error:\n"
                f"```\n{result.error}\n```\n\n"
                f"Any suggestions?"
            )
        
        return state
    
    async def _save_skill(self, state: GraphState) -> GraphState:
        """Save the generated skill."""
        from src.skills.parser import Skill
        from datetime import datetime
        
        code = state.get("pending_skill_code", "")
        original = state["learning_context"][0]["content"] if state["learning_context"] else "New Skill"
        
        # Generate skill name from request
        skill_name = self._generate_skill_name(original)
        
        skill = Skill(
            title=skill_name.replace("_", " ").title(),
            description=original,
            dependencies=[],
            code=code,
            file_path=self.skill_parser.skills_dir / f"{skill_name}.md",
            author="user",
            created=datetime.now().strftime("%Y-%m-%d"),
        )
        
        # Save to disk
        self.skill_parser.save_skill(skill)
        
        # Index in vector store
        await self.vector_store.index_skill(skill)
        
        # Clear learning context
        state["learning_context"] = []
        state["pending_skill_code"] = None
        
        state["response"] = (
            f"Skill **{skill.title}** created and saved!\n\n"
            f"Test result: {state.get('execution_result', 'Success')}"
        )
        
        return state
    
    # Routing functions
    
    def _route_after_auth(self, state: GraphState) -> Literal["authorized", "unauthorized"]:
        return "authorized" if state["is_authorized"] else "unauthorized"
    
    def _route_after_classify(self, state: GraphState) -> Literal["search", "learning", "chat"]:
        return state.get("next_action", "chat")
    
    def _route_after_search(self, state: GraphState) -> Literal["execute", "learn", "chat"]:
        return state.get("next_action", "chat")
    
    def _route_after_learning(self, state: GraphState) -> Literal["generate", "continue", "cancel"]:
        return state.get("next_action", "continue")
    
    def _route_after_test(self, state: GraphState) -> Literal["save", "retry"]:
        return state.get("next_action", "retry")
    
    # Helper methods
    
    async def _extract_arguments(self, message: str, code: str) -> dict:
        """Extract function arguments from user message."""
        provider = self.provider_manager.get_active()
        
        prompt = f"""Given this user message and Python function, extract the arguments.

Message: "{message}"

Function code:
```python
{code}
```

Return a JSON object with argument names and values.
If an argument isn't mentioned, omit it.
Reply with only valid JSON."""

        try:
            response = await provider.generate([
                {"role": "system", "content": "Reply with only valid JSON."},
                {"role": "user", "content": prompt},
            ])
            
            import json
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response.rsplit("```", 1)[0]
            return json.loads(response.strip())
        except Exception:
            return {}
    
    def _generate_skill_name(self, request: str) -> str:
        """Generate a skill name from the request."""
        import re
        # Extract key words and create snake_case name
        words = re.findall(r'\b\w+\b', request.lower())
        # Take first 3-4 meaningful words
        stopwords = {"the", "a", "an", "to", "for", "in", "on", "at", "is", "it", "me", "my", "please", "can", "you", "i", "what"}
        meaningful = [w for w in words if w not in stopwords][:4]
        return "_".join(meaningful) if meaningful else "new_skill"
    
    async def run(self, state: GraphState) -> GraphState:
        """Run the conversation graph."""
        config = {"configurable": {"thread_id": str(state["user_id"])}}
        result = await self.app.ainvoke(state, config)
        return result
