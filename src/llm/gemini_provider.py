"""Google Gemini LLM provider implementation."""

import logging
from typing import Optional, AsyncIterator

from .base import LLMProvider, ToolDefinition, ToolCall, GenerationResult

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini provider for cloud LLM inference with native function calling."""
    
    def __init__(self, api_key: str, model: str):
        """Initialize Gemini provider.
        
        Args:
            api_key: Google AI API key.
            model: Model name (e.g., gemini-1.5-flash).
        """
        self._api_key = api_key
        self._model = model
        self._client = None
        self._client_with_tools = None
        self._embed_model = None
    
    @property
    def name(self) -> str:
        return "gemini"
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def _get_client(self, tools=None):
        """Get or create Gemini client."""
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        
        if tools:
            # Create client with tools - needs fresh instance each time tools change
            return genai.GenerativeModel(self._model, tools=tools)
        
        if self._client is None:
            self._client = genai.GenerativeModel(self._model)
        return self._client
    
    def _get_embed_model(self):
        """Get embedding model."""
        if self._embed_model is None:
            # embedding-001 is the embedding model
            self._embed_model = "models/embedding-001"
        return self._embed_model
    
    def _prepare_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Prepare messages for Gemini API.
        
        Returns:
            Tuple of (system_prompt, conversation)
        """
        import google.generativeai as genai
        from PIL import Image
        from io import BytesIO
        
        system_prompt = ""
        conversation = []
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                system_prompt = content
            elif role == "user":
                # Check if content is multimodal (has image)
                if isinstance(content, dict) and content.get("_type") == "multimodal":
                    parts = []
                    # Add image
                    image_bytes = content.get("image_bytes")
                    if image_bytes:
                        try:
                            img = Image.open(BytesIO(image_bytes))
                            parts.append(img)
                        except Exception as e:
                            logger.warning(f"Failed to load image for Gemini: {e}")
                    # Add text
                    if content.get("text"):
                        parts.append(content["text"])
                    conversation.append({"role": "user", "parts": parts})
                else:
                    conversation.append({"role": "user", "parts": [content]})
            elif role == "assistant" or role == "model":
                conversation.append({"role": "model", "parts": [content]})
            elif role == "tool_result":
                # Format function response for Gemini
                conversation.append({
                    "role": "user",
                    "parts": [genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=msg.get("tool_name", ""),
                            response={"result": content}
                        )
                    )]
                })
        
        return system_prompt, conversation
    
    def _tools_to_gemini_format(self, tools: list[ToolDefinition]) -> list:
        """Convert tool definitions to Gemini function declarations."""
        import google.generativeai as genai
        
        function_declarations = []
        for tool in tools:
            function_declarations.append(
                genai.protos.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=genai.protos.Schema(
                        type=genai.protos.Type.OBJECT,
                        properties={
                            name: genai.protos.Schema(
                                type=self._json_type_to_gemini(prop.get("type", "string")),
                                description=prop.get("description", ""),
                            )
                            for name, prop in tool.parameters.get("properties", {}).items()
                        },
                        required=tool.parameters.get("required", []),
                    )
                )
            )
        
        return [genai.protos.Tool(function_declarations=function_declarations)]
    
    def _json_type_to_gemini(self, json_type: str):
        """Convert JSON Schema type to Gemini Type."""
        import google.generativeai as genai
        
        type_map = {
            "string": genai.protos.Type.STRING,
            "integer": genai.protos.Type.INTEGER,
            "number": genai.protos.Type.NUMBER,
            "boolean": genai.protos.Type.BOOLEAN,
            "array": genai.protos.Type.ARRAY,
            "object": genai.protos.Type.OBJECT,
        }
        return type_map.get(json_type, genai.protos.Type.STRING)
    
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate a response using Gemini."""
        import google.generativeai as genai
        
        client = self._get_client()
        system_prompt, conversation = self._prepare_messages(messages)
        
        # Prepend system prompt to first user message
        if system_prompt and conversation:
            first_content = conversation[0]["parts"][0]
            if isinstance(first_content, str):
                conversation[0]["parts"][0] = f"{system_prompt}\n\n{first_content}"
        
        try:
            generation_config = genai.GenerationConfig(temperature=temperature)
            if max_tokens:
                generation_config.max_output_tokens = max_tokens
            
            chat = client.start_chat(history=conversation[:-1] if len(conversation) > 1 else [])
            
            if conversation:
                last_message = conversation[-1]["parts"][0]
                response = await chat.send_message_async(
                    last_message,
                    generation_config=generation_config,
                )
                return response.text
            
            return ""
            
        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            raise
    
    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> GenerationResult:
        """Generate a response with native function calling support."""
        import google.generativeai as genai
        
        # Convert tools to Gemini format
        gemini_tools = self._tools_to_gemini_format(tools) if tools else None
        client = self._get_client(tools=gemini_tools)
        
        system_prompt, conversation = self._prepare_messages(messages)
        
        # Prepend system prompt
        if system_prompt and conversation:
            first_content = conversation[0]["parts"][0]
            if isinstance(first_content, str):
                conversation[0]["parts"][0] = f"{system_prompt}\n\n{first_content}"
        
        try:
            generation_config = genai.GenerationConfig(temperature=temperature)
            if max_tokens:
                generation_config.max_output_tokens = max_tokens
            
            chat = client.start_chat(history=conversation[:-1] if len(conversation) > 1 else [])
            
            if not conversation:
                return GenerationResult(text="")
            
            last_message = conversation[-1]["parts"][0]
            response = await chat.send_message_async(
                last_message,
                generation_config=generation_config,
            )
            
            # Parse response for function calls
            text = ""
            tool_calls = []
            
            for part in response.parts:
                if hasattr(part, 'text') and part.text:
                    text += part.text
                elif hasattr(part, 'function_call'):
                    fc = part.function_call
                    # Convert proto to dict
                    args = {}
                    if fc.args:
                        for key, value in fc.args.items():
                            args[key] = value
                    
                    tool_calls.append(ToolCall(
                        id=fc.name,  # Gemini doesn't have separate IDs
                        name=fc.name,
                        arguments=args,
                    ))
            
            # Determine finish reason
            finish_reason = "stop"
            if tool_calls:
                finish_reason = "tool_use"
            
            return GenerationResult(
                text=text,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
            
        except Exception as e:
            logger.error(f"Gemini tool calling error: {e}")
            raise
    
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response using Gemini."""
        import google.generativeai as genai
        
        client = self._get_client()
        system_prompt, conversation = self._prepare_messages(messages)
        
        if system_prompt and conversation:
            first_content = conversation[0]["parts"][0]
            if isinstance(first_content, str):
                conversation[0]["parts"][0] = f"{system_prompt}\n\n{first_content}"
        
        try:
            generation_config = genai.GenerationConfig(temperature=temperature)
            if max_tokens:
                generation_config.max_output_tokens = max_tokens
            
            chat = client.start_chat(history=conversation[:-1] if len(conversation) > 1 else [])
            
            if conversation:
                last_message = conversation[-1]["parts"][0]
                response = await chat.send_message_async(
                    last_message,
                    generation_config=generation_config,
                    stream=True,
                )
                
                async for chunk in response:
                    if chunk.text:
                        yield chunk.text
                        
        except Exception as e:
            logger.error(f"Gemini streaming error: {e}")
            raise
    
    async def embed(self, text: str) -> list[float]:
        """Generate embeddings using Gemini."""
        import google.generativeai as genai
        genai.configure(api_key=self._api_key)
        
        try:
            result = genai.embed_content(
                model=self._get_embed_model(),
                content=text,
                task_type="retrieval_document",
            )
            return result["embedding"]
        except Exception as e:
            logger.error(f"Gemini embedding error: {e}")
            raise
    
    def is_available(self) -> bool:
        """Check if Gemini is properly configured."""
        return bool(self._api_key)
    
    def supports_tools(self) -> bool:
        """Gemini supports native function calling."""
        return True
    
    def supports_embeddings(self) -> bool:
        return True
    
    def supports_vision(self) -> bool:
        """Gemini supports vision/image analysis."""
        return True