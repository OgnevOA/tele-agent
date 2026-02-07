"""Telegram command handlers."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from src.config import config

logger = logging.getLogger(__name__)


def admin_only(func):
    """Decorator to restrict commands to admin user only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id if update.effective_user else 0
        admin_id = context.bot_data.get("config", config).telegram.admin_id
        
        if user_id != admin_id:
            return None
        
        return await func(update, context)
    return wrapper


@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "Welcome to Tele-Agent!\n\n"
        "I'm your personal AI assistant. I can execute skills and learn new ones.\n\n"
        "Commands:\n"
        "/model - Switch LLM provider\n"
        "/skills - Manage skills\n"
        "/status - System status\n"
        "/help - Show this message"
    )


@admin_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    await update.message.reply_text(
        "Tele-Agent Help\n\n"
        "Just send me a message and I'll try to help!\n\n"
        "Commands:\n"
        "/model - Switch between Gemini and Anthropic\n"
        "/skills - View and manage available skills\n"
        "/status - Check system status\n"
        "/reload - Reload configuration and skills\n"
        "/clear - Clear conversation history\n"
        "/usage - View Anthropic token usage and costs\n"
        "/jobs - View and manage scheduled tasks\n\n"
        "If I don't know how to do something, I'll ask you to teach me!"
    )


@admin_only
async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /model command - show model selection."""
    provider_manager = context.bot_data.get("provider_manager")
    
    if not provider_manager:
        await update.message.reply_text("Provider manager not initialized.")
        return
    
    current = provider_manager.active_provider
    current_model = provider_manager.get_active().model_name
    
    # Build inline keyboard
    keyboard = []
    for name, provider in provider_manager.providers.items():
        # Mark current provider with checkmark
        label = f"✓ {name.title()}" if name == current else name.title()
        if provider.is_available():
            keyboard.append([InlineKeyboardButton(label, callback_data=f"model:{name}")])
        else:
            keyboard.append([InlineKeyboardButton(f"{name.title()} (unavailable)", callback_data=f"model:{name}:unavailable")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Current provider: **{current.title()}** ({current_model})\n\n"
        "Select a provider:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


@admin_only
async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /skills command - show skills management."""
    skill_parser = context.bot_data.get("skill_parser")
    
    if not skill_parser:
        await update.message.reply_text("Skill parser not initialized.")
        return
    
    skills = skill_parser.skills
    
    if not skills:
        await update.message.reply_text(
            "No skills found.\n\n"
            "Teach me something new by asking me to do a task I don't know!"
        )
        return
    
    # Build skill list with toggle buttons
    keyboard = []
    enabled_count = 0
    disabled_count = 0
    
    for name, skill in sorted(skills.items()):
        status = "✅" if skill.enabled else "❌"
        if skill.enabled:
            enabled_count += 1
        else:
            disabled_count += 1
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {skill.title}",
                callback_data=f"skill:toggle:{name}",
            )
        ])
    
    # Add bulk actions
    keyboard.append([
        InlineKeyboardButton("Disable All", callback_data="skill:disable_all"),
        InlineKeyboardButton("Enable All", callback_data="skill:enable_all"),
    ])
    keyboard.append([
        InlineKeyboardButton("🔄 Refresh Index", callback_data="skill:refresh"),
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Skills ({enabled_count} active, {disabled_count} disabled):\n\n"
        "Tap a skill to toggle it:",
        reply_markup=reply_markup,
    )


@admin_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - show system status."""
    agent = context.bot_data.get("agent")
    provider_manager = context.bot_data.get("provider_manager")
    skill_parser = context.bot_data.get("skill_parser")
    tool_registry = context.bot_data.get("tool_registry")
    prompt_builder = context.bot_data.get("prompt_builder")
    
    # Gather status info
    provider_name = "N/A"
    model_name = "N/A"
    if provider_manager:
        provider_name = provider_manager.active_provider.title()
        provider = provider_manager.get_active()
        model_name = provider.model_name
    
    skills_count = len(skill_parser.skills) if skill_parser else 0
    enabled_skills = sum(1 for s in skill_parser.skills.values() if s.enabled) if skill_parser else 0
    disabled_skills = skills_count - enabled_skills
    
    tools_count = len(tool_registry.get_all_tool_definitions()) if tool_registry else 0
    
    # Get identity if available
    identity = "Unknown"
    if prompt_builder:
        identity_info = prompt_builder.get_identity()
        if identity_info:
            identity = f"{identity_info.get('name', 'Unknown')} {identity_info.get('emoji', '')}"
    
    uptime = agent.uptime if agent else "N/A"
    
    status_text = (
        "🤖 **Tele-Agent Status**\n\n"
        f"Provider: {provider_name} ({model_name})\n"
        f"Skills: {enabled_skills} active, {disabled_skills} disabled\n"
        f"Tools: {tools_count} registered\n"
        f"Identity: {identity}\n"
        f"Uptime: {uptime}"
    )
    
    await update.message.reply_text(status_text, parse_mode="Markdown")


@admin_only
async def reload_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reload command - reload skills and config."""
    skill_parser = context.bot_data.get("skill_parser")
    tool_registry = context.bot_data.get("tool_registry")
    prompt_builder = context.bot_data.get("prompt_builder")
    
    try:
        # Reload skills
        if skill_parser:
            skills = skill_parser.load_all_skills()
            
            # Refresh tool registry
            if tool_registry:
                tool_registry.refresh()
        
        # Reload prompt
        if prompt_builder:
            prompt_builder.reload()
        
        skills_count = len(skill_parser.skills) if skill_parser else 0
        tools_count = len(tool_registry.get_all_tool_definitions()) if tool_registry else 0
        
        await update.message.reply_text(
            f"Reloaded!\n\n"
            f"Skills: {skills_count}\n"
            f"Tools: {tools_count}\n"
            f"System prompt updated"
        )
        
    except Exception as e:
        await update.message.reply_text(f"Error reloading: {e}")


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()
    
    # Check admin
    user_id = update.effective_user.id if update.effective_user else 0
    admin_id = context.bot_data.get("config", config).telegram.admin_id
    if user_id != admin_id:
        return
    
    data = query.data
    
    if data.startswith("model:"):
        await handle_model_callback(update, context, data)
    elif data.startswith("skill:"):
        await handle_skill_callback(update, context, data)
    elif data.startswith("usage:"):
        await handle_usage_callback(update, context, data)
    elif data.startswith("scheduler:"):
        await handle_scheduler_callback(update, context, data)


async def handle_model_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle model selection callback."""
    query = update.callback_query
    provider_manager = context.bot_data.get("provider_manager")
    
    parts = data.split(":")
    provider_name = parts[1]
    
    if len(parts) > 2 and parts[2] == "unavailable":
        await query.edit_message_text(
            f"Provider '{provider_name}' is not available. "
            "Check your API key configuration."
        )
        return
    
    if provider_manager:
        try:
            provider_manager.switch(provider_name)
            model_name = provider_manager.get_active().model_name
            
            await query.edit_message_text(
                f"Switched to **{provider_name.title()}** ({model_name})",
                parse_mode="Markdown",
            )
        except Exception as e:
            await query.edit_message_text(f"Error switching provider: {e}")


async def handle_skill_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle skill management callback."""
    query = update.callback_query
    skill_parser = context.bot_data.get("skill_parser")
    vector_store = context.bot_data.get("vector_store")
    
    parts = data.split(":")
    action = parts[1]
    
    if action == "toggle" and len(parts) > 2:
        skill_name = parts[2]
        skill = skill_parser.get_skill(skill_name)
        
        if skill:
            skill.enabled = not skill.enabled
            status = "enabled" if skill.enabled else "disabled"
            await query.edit_message_text(f"Skill '{skill.title}' {status}.")
    
    elif action == "enable_all":
        for skill in skill_parser.skills.values():
            skill.enabled = True
        await query.edit_message_text("All skills enabled.")
    
    elif action == "disable_all":
        for skill in skill_parser.skills.values():
            skill.enabled = False
        await query.edit_message_text("All skills disabled.")
    
    elif action == "refresh":
        skills = skill_parser.load_all_skills()
        if vector_store:
            await vector_store.clear()
            await vector_store.index_skills(skills)
        await query.edit_message_text(f"Refreshed {len(skills)} skills.")


async def handle_usage_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle usage stats callback."""
    query = update.callback_query
    provider_manager = context.bot_data.get("provider_manager")
    
    parts = data.split(":")
    action = parts[1]
    
    anthropic_provider = provider_manager.providers.get("anthropic")
    if not anthropic_provider:
        await query.edit_message_text("Anthropic provider not found.")
        return
    
    if action == "reset":
        anthropic_provider.usage.reset()
        await query.edit_message_text("✅ Session stats reset to zero.")
    
    elif action == "report":
        days = int(parts[2]) if len(parts) > 2 else 7
        
        await query.edit_message_text(f"⏳ Fetching {days}-day report from Anthropic...")
        
        # Fetch both reports
        usage_report = await anthropic_provider.get_usage_report(days=days)
        cost_report = await anthropic_provider.get_cost_report(days=days)
        
        if not usage_report and not cost_report:
            await query.edit_message_text(
                "❌ Could not fetch reports.\n\n"
                "The Admin API may require an admin-level API key. "
                "Check your Anthropic Console for usage details."
            )
            return
        
        # Build report text (no Markdown to avoid parsing issues with model names)
        lines = [f"📊 Anthropic {days}-Day Report\n"]
        
        if usage_report:
            lines.append(f"📅 {usage_report.period_start} → {usage_report.period_end}\n")
            lines.append("Token Usage:")
            lines.append(f"• Input (uncached): {usage_report.uncached_input_tokens:,}")
            lines.append(f"• Output: {usage_report.output_tokens:,}")
            if usage_report.cache_read_input_tokens:
                lines.append(f"• Cache reads: {usage_report.cache_read_input_tokens:,}")
            if usage_report.cache_creation_tokens:
                lines.append(f"• Cache creation: {usage_report.cache_creation_tokens:,}")
            lines.append(f"• Total: {usage_report.total_tokens:,}\n")
        
        if cost_report:
            lines.append("Cost:")
            lines.append(f"• Total: ${cost_report.total_cost_usd:.4f} {cost_report.currency}")
            
            # Show breakdown if available
            if cost_report.breakdown:
                lines.append("\nBreakdown:")
                for key, amount in sorted(cost_report.breakdown.items()):
                    if amount > 0:
                        model, token_type = key.split(":", 1) if ":" in key else (key, "")
                        cost_usd = amount / 100.0
                        # Clean up token type for display
                        token_display = token_type.replace("_", " ").title()
                        lines.append(f"  • {token_display}: ${cost_usd:.4f}")
        
        await query.edit_message_text("\n".join(lines))


@admin_only
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /clear command - clear conversation history."""
    from pathlib import Path
    
    # Clear in-memory history
    context.user_data["conversation"] = []
    
    # Clear persisted history
    history_file = Path("data/conversation_history.json")
    try:
        if history_file.exists():
            history_file.unlink()
    except Exception:
        pass
    
    await update.message.reply_text("Conversation history cleared. Starting fresh!")


@admin_only
async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /usage command - show token usage and costs."""
    provider_manager = context.bot_data.get("provider_manager")
    
    if not provider_manager:
        await update.message.reply_text("Provider manager not initialized.")
        return
    
    # Get Anthropic provider
    anthropic_provider = provider_manager.providers.get("anthropic")
    
    if not anthropic_provider:
        await update.message.reply_text("Anthropic provider not configured.")
        return
    
    # Session stats
    session = anthropic_provider.usage
    
    # Build inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("📈 7 Days", callback_data="usage:report:7"),
            InlineKeyboardButton("📈 30 Days", callback_data="usage:report:30"),
        ],
        [InlineKeyboardButton("🔄 Reset Session", callback_data="usage:reset")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Session stats text
    text = (
        "📊 **Anthropic Usage**\n\n"
        f"Model: `{anthropic_provider.model_name}`\n\n"
        "**This Session:**\n"
        f"• Requests: {session.requests}\n"
        f"• Input: {session.input_tokens:,} tokens\n"
        f"• Output: {session.output_tokens:,} tokens\n"
        f"• Cache reads: {session.cache_read_tokens:,} tokens\n\n"
        "_Tap a button to fetch usage from Anthropic Admin API_"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


@admin_only
async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /jobs command - list scheduled jobs."""
    scheduler = context.bot_data.get("scheduler")
    
    if not scheduler:
        await update.message.reply_text("Scheduler not initialized.")
        return
    
    jobs = scheduler.list_jobs()
    
    if not jobs:
        await update.message.reply_text(
            "📅 No scheduled tasks.\n\n"
            "Tell me to schedule something, like:\n"
            "\"Remind me to check emails every day at 9am\""
        )
        return
    
    lines = ["📅 Scheduled Tasks:\n"]
    for job in jobs:
        status = "✅" if job.enabled else "⏸️"
        lines.append(f"{status} {job.id}: {job.description}")
        lines.append(f"   Task: {job.task[:40]}{'...' if len(job.task) > 40 else ''}")
        if job.last_run:
            lines.append(f"   Last: {job.last_run[:16]}")
        lines.append("")
    
    # Add management buttons
    keyboard = []
    for job in jobs[:5]:  # Limit to 5 buttons
        status_emoji = "⏸️" if job.enabled else "▶️"
        keyboard.append([
            InlineKeyboardButton(f"{status_emoji} {job.id}", callback_data=f"scheduler:toggle:{job.id}"),
            InlineKeyboardButton("🗑️", callback_data=f"scheduler:delete:{job.id}"),
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await update.message.reply_text("\n".join(lines), reply_markup=reply_markup)


async def handle_scheduler_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle scheduler-related callbacks."""
    query = update.callback_query
    scheduler = context.bot_data.get("scheduler")
    
    if not scheduler:
        await query.edit_message_text("Scheduler not available.")
        return
    
    parts = data.split(":")
    action = parts[1]
    
    if action == "confirm" and len(parts) > 2:
        job_id = parts[2]
        job = scheduler.confirm_job(job_id)
        
        if job:
            await query.edit_message_text(
                f"✅ Scheduled!\n\n"
                f"ID: {job.id}\n"
                f"Schedule: {job.description}\n"
                f"Task: {job.task}"
            )
        else:
            await query.edit_message_text("Job not found or already confirmed.")
    
    elif action == "cancel" and len(parts) > 2:
        job_id = parts[2]
        if scheduler.cancel_pending(job_id):
            await query.edit_message_text("❌ Scheduling cancelled.")
        else:
            await query.edit_message_text("Job not found.")
    
    elif action == "toggle" and len(parts) > 2:
        job_id = parts[2]
        new_state = scheduler.toggle_job(job_id)
        
        if new_state is not None:
            state_text = "resumed ▶️" if new_state else "paused ⏸️"
            await query.edit_message_text(f"Job {job_id} {state_text}")
        else:
            await query.edit_message_text(f"Job {job_id} not found.")
    
    elif action == "delete" and len(parts) > 2:
        job_id = parts[2]
        job = scheduler.delete_job(job_id)
        
        if job:
            await query.edit_message_text(f"🗑️ Deleted job {job_id}: {job.description}")
        else:
            await query.edit_message_text(f"Job {job_id} not found.")


def setup_commands(app: Application) -> None:
    """Register command handlers with the application."""
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("model", model_command))
    app.add_handler(CommandHandler("skills", skills_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("reload", reload_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("usage", usage_command))
    app.add_handler(CommandHandler("jobs", jobs_command))
    
    # Handle inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    logger.info("Command handlers registered")
