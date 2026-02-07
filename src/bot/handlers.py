"""Telegram message handlers with native tool calling support."""

import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager
from functools import wraps
from io import BytesIO
from pathlib import Path
from typing import Callable, Any, Optional

from telegram import Update
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode, ChatAction
import html as html_lib

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.config import config
from src.llm.base import ToolCall, GenerationResult
from src.core.tool_registry import ToolRegistry
from src.skills.executor import SkillExecutor

logger = logging.getLogger(__name__)

# Maximum tool call iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 10

# Processing timeout in seconds (2 minutes)
PROCESSING_TIMEOUT = 120

# Conversation history file
CONVERSATION_FILE = Path("data/conversation_history.json")

# Supported image types
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@asynccontextmanager
async def typing_indicator(chat):
    """Context manager that keeps typing indicator active until done.
    
    Sends typing action every 4 seconds (Telegram typing times out after ~5s).
    """
    stop_event = asyncio.Event()
    
    async def keep_typing():
        while not stop_event.is_set():
            try:
                await chat.send_action(ChatAction.TYPING)
            except Exception:
                pass  # Ignore errors, just keep trying
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                continue  # Timeout expected, keep looping
    
    task = asyncio.create_task(keep_typing())
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def admin_only(func: Callable) -> Callable:
    """Decorator to restrict handler to admin user only."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        user_id = update.effective_user.id if update.effective_user else 0
        admin_id = context.bot_data.get("config", config).telegram.admin_id
        
        if user_id != admin_id:
            logger.debug(f"Ignoring message from non-admin user: {user_id}")
            return None
        
        return await func(update, context)
    
    return wrapper


def load_conversation_history() -> list[dict]:
    """Load conversation history from disk."""
    try:
        if CONVERSATION_FILE.exists():
            data = json.loads(CONVERSATION_FILE.read_text(encoding="utf-8"))
            return data.get("messages", [])
    except Exception as e:
        logger.warning(f"Failed to load conversation history: {e}")
    return []


def save_conversation_history(messages: list[dict]) -> None:
    """Save conversation history to disk."""
    try:
        CONVERSATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"messages": messages[-20:]}  # Keep last 20 messages
        CONVERSATION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save conversation history: {e}")


async def send_formatted(update: Update, text: str, context: Optional[ContextTypes.DEFAULT_TYPE] = None) -> None:
    """Send message with formatting - tries HTML first, then plain text.
    
    Also handles special scheduler confirmation requests.
    """
    # Check for scheduler confirmation request
    if text.startswith("CONFIRM_SCHEDULE:") and context:
        await handle_scheduler_confirmation(update, context, text)
        return
    
    # Check for scheduler action responses
    if text.startswith("SCHEDULER_DELETE:") and context:
        job_id = text.split(":", 1)[1]
        scheduler = context.bot_data.get("scheduler")
        if scheduler:
            scheduler._unregister_job(job_id)
        await update.message.reply_text(f"🗑️ Deleted scheduled task {job_id}")
        return
    
    if text.startswith("SCHEDULER_TOGGLE:") and context:
        parts = text.split(":")
        job_id = parts[1]
        enabled = parts[2].lower() == "true"
        scheduler = context.bot_data.get("scheduler")
        if scheduler:
            job = scheduler.store.get(job_id)
            if job:
                if enabled:
                    scheduler._register_job(job)
                else:
                    scheduler._unregister_job(job_id)
        state = "resumed ▶️" if enabled else "paused ⏸️"
        await update.message.reply_text(f"Task {job_id} {state}")
        return
    
    # Strategy 1: Try HTML (most reliable for LLM markdown output)
    try:
        html_text = markdown_to_html(text)
        await update.message.reply_text(html_text, parse_mode=ParseMode.HTML)
        return
    except Exception as e:
        logger.debug(f"HTML formatting failed: {e}")
    
    # Strategy 2: Plain text (strip markdown for cleaner output)
    try:
        plain_text = strip_markdown(text)
        await update.message.reply_text(plain_text)
        return
    except Exception as e:
        logger.debug(f"Plain text failed: {e}")
    
    # Strategy 3: Last resort - raw text, truncate if needed
    try:
        await update.message.reply_text(text[:4000] if len(text) > 4000 else text)
    except Exception as e:
        logger.warning(f"All send attempts failed: {e}")


def strip_markdown_v2_escapes(text: str) -> str:
    """Remove MarkdownV2 escape sequences that the LLM might output."""
    import re
    
    # Remove backslash escapes before special chars: \. \! \- \( \) \[ \] etc.
    # MarkdownV2 escapes: _ * [ ] ( ) ~ ` > # + - = | { } . !
    text = re.sub(r'\\([_*\[\]()~`>#+=|{}.!\-])', r'\1', text)
    
    return text


def strip_markdown(text: str) -> str:
    """Remove markdown formatting for plain text output."""
    import re
    
    # First strip any MarkdownV2 escapes
    text = strip_markdown_v2_escapes(text)
    
    # Remove code block markers but keep content
    text = re.sub(r'```\w*\n?', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove formatting markers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    
    # Convert links to just the text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    return text


def markdown_to_html(text: str) -> str:
    """Convert markdown-style formatting to Telegram HTML."""
    import re
    
    # First, strip any MarkdownV2 escapes the LLM might have added
    text = strip_markdown_v2_escapes(text)
    
    # Process code blocks first (```code```)
    def replace_code_block(match):
        code = html_lib.escape(match.group(1))
        return f"<pre>{code}</pre>"
    
    text = re.sub(r'```(?:\w+)?\n?(.*?)```', replace_code_block, text, flags=re.DOTALL)
    
    # Process inline code (`code`)
    def replace_inline_code(match):
        code = html_lib.escape(match.group(1))
        return f"<code>{code}</code>"
    
    text = re.sub(r'`([^`]+)`', replace_inline_code, text)
    
    # Split by pre and code tags, escape the rest
    parts = re.split(r'(<pre>.*?</pre>|<code>.*?</code>)', text, flags=re.DOTALL)
    result_parts = []
    
    for part in parts:
        if part.startswith('<pre>') or part.startswith('<code>'):
            result_parts.append(part)
        else:
            escaped = html_lib.escape(part)
            
            # Bold: **text** or __text__
            escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
            escaped = re.sub(r'__(.+?)__', r'<b>\1</b>', escaped)
            
            # Italic: *text* or _text_
            escaped = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', escaped)
            escaped = re.sub(r'_([^_]+)_', r'<i>\1</i>', escaped)
            
            # Strikethrough: ~~text~~
            escaped = re.sub(r'~~(.+?)~~', r'<s>\1</s>', escaped)
            
            # Links: [text](url)
            escaped = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escaped)
            
            result_parts.append(escaped)
    
    return ''.join(result_parts)


async def download_telegram_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[tuple[bytes, str]]:
    """Download image from Telegram message.
    
    Returns:
        Tuple of (image_bytes, mime_type) or None if no image.
    """
    if not update.message:
        return None
    
    photo = None
    mime_type = "image/jpeg"
    
    # Check for photo (compressed image)
    if update.message.photo:
        # Get the largest photo (last in the list)
        photo = update.message.photo[-1]
        mime_type = "image/jpeg"
    
    # Check for document (uncompressed image)
    elif update.message.document:
        doc = update.message.document
        if doc.mime_type in SUPPORTED_IMAGE_TYPES:
            photo = doc
            mime_type = doc.mime_type
    
    if not photo:
        return None
    
    try:
        file = await context.bot.get_file(photo.file_id)
        
        # Download to BytesIO
        buffer = BytesIO()
        await file.download_to_memory(buffer)
        buffer.seek(0)
        
        return buffer.read(), mime_type
        
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        return None


@admin_only
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages with tool calling support."""
    if not update.message or not update.message.text:
        return
    
    message = update.message.text
    await process_message(update, context, message, image_data=None)


@admin_only
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photos with optional captions."""
    if not update.message:
        return
    
    # Get caption text (can be empty)
    caption = update.message.caption or "What's in this image?"
    
    # Download the image
    image_data = await download_telegram_image(update, context)
    
    if not image_data:
        await update.message.reply_text("Sorry, I couldn't download that image.")
        return
    
    await process_message(update, context, caption, image_data=image_data)


async def process_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message: str,
    image_data: Optional[tuple[bytes, str]] = None,
) -> None:
    """Process a message with optional image."""
    user_id = update.effective_user.id if update.effective_user else 0
    
    if image_data:
        logger.info(f"Received image from {user_id} with caption: {message[:50]}...")
    else:
        logger.info(f"Received message from {user_id}: {message[:50]}...")
    
    # Get components from bot_data
    provider_manager = context.bot_data.get("provider_manager")
    tool_registry: ToolRegistry = context.bot_data.get("tool_registry")
    skill_parser = context.bot_data.get("skill_parser")
    prompt_builder = context.bot_data.get("prompt_builder")
    
    if not provider_manager:
        await update.message.reply_text("I'm still initializing. Please try again in a moment.")
        return
    
    # Load conversation history (from memory or disk)
    if "conversation" not in context.user_data:
        context.user_data["conversation"] = load_conversation_history()
    
    # Get active provider
    provider = provider_manager.get_active()
    
    # Check if provider supports vision for images
    if image_data and not provider.supports_vision():
        await update.message.reply_text(
            f"The current model ({provider.model_name}) doesn't support images. "
            f"Switch to Anthropic or Gemini with /model"
        )
        return
    
    # Build system prompt
    system_prompt = prompt_builder.build_system_prompt() if prompt_builder else ""
    
    # Process with typing indicator and timeout
    try:
        async with typing_indicator(update.message.chat):
            await asyncio.wait_for(
                handle_with_tool_calling(
                    update, context, message, system_prompt,
                    provider, tool_registry, skill_parser,
                    image_data=image_data,
                ),
                timeout=PROCESSING_TIMEOUT,
            )
    except asyncio.TimeoutError:
        logger.warning(f"Processing timed out after {PROCESSING_TIMEOUT}s for user {user_id}")
        await update.message.reply_text(
            f"⏱️ Request timed out after {PROCESSING_TIMEOUT // 60} minutes. "
            "Please try a simpler request."
        )


def build_user_message_content(
    text: str,
    image_data: Optional[tuple[bytes, str]] = None,
    provider_name: str = "",
) -> Any:
    """Build user message content with optional image for different providers."""
    if not image_data:
        return text
    
    image_bytes, mime_type = image_data
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    if provider_name == "anthropic":
        # Anthropic format: content blocks
        return [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": image_b64,
                }
            },
            {
                "type": "text",
                "text": text,
            }
        ]
    elif provider_name == "gemini":
        # Gemini handles images differently - we'll pass raw bytes
        # Return a special format that Gemini provider will handle
        return {
            "_type": "multimodal",
            "text": text,
            "image_bytes": image_bytes,
            "mime_type": mime_type,
        }
    else:
        # Fallback for providers without vision support
        return text


async def handle_with_tool_calling(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message: str,
    system_prompt: str,
    provider,
    tool_registry: ToolRegistry,
    skill_parser,
    image_data: Optional[tuple[bytes, str]] = None,
) -> None:
    """Handle message using native LLM tool calling."""
    # Get all available tools
    tools = tool_registry.get_all_tool_definitions() if tool_registry else []
    
    # Get conversation history
    conversation = context.user_data.get("conversation", [])
    
    # Build messages
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add recent conversation history (last 20 messages)
    messages.extend(conversation[-20:])
    
    # Add current message (with image if present)
    user_content = build_user_message_content(message, image_data, provider.name)
    messages.append({"role": "user", "content": user_content})
    
    # Tool execution loop
    executor = SkillExecutor(timeout=30)
    iterations = 0
    
    while iterations < MAX_TOOL_ITERATIONS:
        iterations += 1
        
        # Generate with tools
        result: GenerationResult = await provider.generate_with_tools(
            messages=messages,
            tools=tools,
            temperature=0.7,
        )
        
        if not result.has_tool_calls:
            # No tool calls - send final response
            response = result.text or "I processed your request."
            
            # Update conversation history
            conversation.append({"role": "user", "content": message})
            conversation.append({"role": "assistant", "content": response})
            context.user_data["conversation"] = conversation[-20:]  # Keep last 20
            
            # Save to disk for persistence
            save_conversation_history(conversation[-20:])
            
            # Send with HTML formatting
            await send_formatted(update, response, context)
            return
        
        # Execute tool calls
        logger.info(f"Executing {len(result.tool_calls)} tool calls")
        
        for tool_call in result.tool_calls:
            await execute_tool_call(
                update, context, messages, tool_call,
                skill_parser, executor, provider.name
            )
    
    # Max iterations reached
    await update.message.reply_text(
        "I've reached the maximum number of tool calls. "
        "Please try a simpler request."
    )


async def execute_tool_call(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    messages: list[dict],
    tool_call: ToolCall,
    skill_parser,
    executor: SkillExecutor,
    provider_name: str,
) -> None:
    """Execute a single tool call and add result to messages."""
    skill = skill_parser.get_skill(tool_call.name)
    
    if not skill:
        error_msg = f"Skill '{tool_call.name}' not found"
        logger.warning(error_msg)
        add_tool_result(messages, tool_call, error_msg, provider_name)
        return
    
    logger.info(f"Executing skill: {tool_call.name} with args: {tool_call.arguments}")
    
    # Execute the skill
    result = executor.execute(skill, tool_call.arguments)
    
    if result.success:
        result_text = str(result.result)
        logger.info(f"Skill {tool_call.name} succeeded: {result_text[:200]}{'...' if len(result_text) > 200 else ''}")
    else:
        result_text = f"Error: {result.error}"
        logger.error(f"Skill {tool_call.name} failed: {result.error}")
        if result.stderr:
            logger.error(f"Skill {tool_call.name} stderr: {result.stderr[:500]}")
    
    # Check for special scheduler confirmation - needs direct handling
    if result_text.startswith("CONFIRM_SCHEDULE:"):
        await handle_scheduler_confirmation(update, context, result_text)
        # Add a note to the LLM that confirmation was requested
        add_tool_result(messages, tool_call, "Confirmation dialog shown to user. Waiting for their response.", provider_name)
        return
    
    # Check for other scheduler actions that need immediate handling
    if result_text.startswith("SCHEDULER_DELETE:"):
        job_id = result_text.split(":", 1)[1]
        scheduler = context.bot_data.get("scheduler")
        if scheduler:
            scheduler._unregister_job(job_id)
        add_tool_result(messages, tool_call, f"Deleted scheduled task {job_id}", provider_name)
        return
    
    if result_text.startswith("SCHEDULER_TOGGLE:"):
        parts = result_text.split(":")
        job_id = parts[1]
        enabled = parts[2].lower() == "true"
        scheduler = context.bot_data.get("scheduler")
        if scheduler:
            job = scheduler.store.get(job_id)
            if job:
                if enabled:
                    scheduler._register_job(job)
                else:
                    scheduler._unregister_job(job_id)
        state = "resumed" if enabled else "paused"
        add_tool_result(messages, tool_call, f"Task {job_id} {state}", provider_name)
        return
    
    # Add result to messages in provider-specific format
    add_tool_result(messages, tool_call, result_text, provider_name)


def add_tool_result(
    messages: list[dict],
    tool_call: ToolCall,
    result: str,
    provider_name: str,
) -> None:
    """Add tool result to messages in provider-specific format."""
    if provider_name == "anthropic":
        # Anthropic format: assistant message with tool_use, then user with tool_result
        messages.append({
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": tool_call.id,
                "name": tool_call.name,
                "input": tool_call.arguments,
            }],
        })
        messages.append({
            "role": "tool_result",
            "tool_use_id": tool_call.id,
            "content": result,
        })
    elif provider_name == "gemini":
        # Gemini format
        messages.append({
            "role": "assistant",
            "content": f"[Called {tool_call.name}]",
        })
        messages.append({
            "role": "tool_result",
            "tool_name": tool_call.name,
            "content": result,
        })
    else:
        # Generic format
        messages.append({
            "role": "assistant",
            "content": f"[Executed {tool_call.name}]",
        })
        messages.append({
            "role": "user",
            "content": f"Tool result for {tool_call.name}: {result}",
        })


async def handle_scheduler_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    """Handle scheduler confirmation request from skill."""
    import json as json_module
    
    try:
        # Parse the confirmation payload
        json_str = text.split(":", 1)[1]
        data = json_module.loads(json_str)
        
        task = data.get("task", "")
        cron = data.get("cron", "")
        description = data.get("description", "")
        
        scheduler = context.bot_data.get("scheduler")
        if not scheduler:
            await update.message.reply_text("Scheduler not available.")
            return
        
        # Create pending job
        from src.scheduler import PendingJob
        pending = PendingJob.create(
            task=task,
            cron=cron,
            description=description,
        )
        scheduler.add_pending(pending)
        
        # Show confirmation with inline buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"scheduler:confirm:{pending.id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"scheduler:cancel:{pending.id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        confirmation_text = (
            f"📅 **Schedule this task?**\n\n"
            f"**When:** {description}\n"
            f"**Cron:** `{cron}`\n\n"
            f"**Task (word-for-word):**\n{task}"
        )
        
        await update.message.reply_text(
            confirmation_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
        )
        
    except Exception as e:
        logger.error(f"Failed to parse scheduler confirmation: {e}")
        await update.message.reply_text(f"Error scheduling task: {e}")


def setup_handlers(app: Application) -> None:
    """Register message handlers with the application."""
    # Text messages
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message,
    ))
    
    # Photos (with or without captions)
    app.add_handler(MessageHandler(
        filters.PHOTO | (filters.Document.IMAGE),
        handle_photo,
    ))
    
    logger.info("Message handlers registered (text + images)")
