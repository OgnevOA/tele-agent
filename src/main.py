"""Main entry point for Tele-Agent."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from telegram.ext import Application

from src.config import config
from src.bot import setup_handlers, setup_commands
from src.core import PromptBuilder, ToolRegistry
from src.llm import ProviderManager
from src.skills import SkillParser
from src.scheduler import Scheduler, ScheduledJob

# Configure logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler(LOG_DIR / "tele-agent.log", encoding="utf-8"),  # File output
    ],
)

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class TeleAgent:
    """Main Tele-Agent application."""
    
    def __init__(self):
        self.config = config
        self.start_time = datetime.now()
        
        # Initialize components
        self.prompt_builder = PromptBuilder(config.paths)
        self.skill_parser = SkillParser(config.paths.skills_dir)
        self.tool_registry: ToolRegistry | None = None
        self.provider_manager: ProviderManager | None = None
        self.scheduler: Scheduler | None = None
        self.app: Application | None = None
    
    async def initialize(self):
        """Initialize all async components."""
        logger.info("Initializing Tele-Agent...")
        
        # Validate configuration
        errors = self.config.validate()
        if errors:
            for error in errors:
                logger.error(f"Config error: {error}")
            raise ValueError("Configuration validation failed")
        
        # Ensure directories exist
        self.config.paths.skills_dir.mkdir(parents=True, exist_ok=True)
        self.config.paths.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize provider manager
        self.provider_manager = ProviderManager(self.config)
        await self.provider_manager.initialize()
        
        # Load skills and create tool registry
        skills = self.skill_parser.load_all_skills()
        self.tool_registry = ToolRegistry(self.skill_parser)
        tools = self.tool_registry.get_all_tool_definitions()
        logger.info(f"Loaded {len(skills)} skills, {len(tools)} tools registered")
        
        # Load system prompt
        system_prompt = self.prompt_builder.build_system_prompt()
        logger.info(f"Loaded system prompt ({len(system_prompt)} chars)")
        
        # Build Telegram application
        self.app = Application.builder().token(self.config.telegram.bot_token).build()
        
        # Initialize scheduler
        self.scheduler = Scheduler(store_path=Path("data/scheduled_jobs.json"))
        self.scheduler.set_app(self.app)
        self.scheduler.set_job_callback(self._execute_scheduled_job)
        
        # Store references in bot_data for handlers
        self.app.bot_data["agent"] = self
        self.app.bot_data["config"] = self.config
        self.app.bot_data["provider_manager"] = self.provider_manager
        self.app.bot_data["skill_parser"] = self.skill_parser
        self.app.bot_data["tool_registry"] = self.tool_registry
        self.app.bot_data["prompt_builder"] = self.prompt_builder
        self.app.bot_data["scheduler"] = self.scheduler
        
        # Setup handlers and commands
        setup_commands(self.app)
        setup_handlers(self.app)
        
        logger.info("Tele-Agent initialized successfully")
    
    async def _execute_scheduled_job(self, job: ScheduledJob, context) -> None:
        """Execute a scheduled job by sending it to the AI."""
        logger.info(f"Executing scheduled job {job.id}: {job.task[:50]}...")
        
        try:
            # Get admin chat ID
            admin_id = self.config.telegram.admin_id
            
            # Send notification that scheduled task is running
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"⏰ Running scheduled task: {job.description}\n\nTask: {job.task}",
            )
            
            # Build system prompt
            system_prompt = self.prompt_builder.build_system_prompt()
            
            # Get provider
            provider = self.provider_manager.get_active()
            
            # Process the task with tool calling
            tools = self.tool_registry.get_all_tool_definitions()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"[SCHEDULED TASK] {job.task}"},
            ]
            
            from src.skills.executor import SkillExecutor
            executor = SkillExecutor(timeout=60)
            
            # Generate with tools
            result = await provider.generate_with_tools(
                messages=messages,
                tools=tools,
                temperature=0.7,
            )
            
            # Execute any tool calls
            if result.has_tool_calls:
                for tool_call in result.tool_calls:
                    skill = self.skill_parser.get_skill(tool_call.name)
                    if skill:
                        exec_result = executor.execute(skill, tool_call.arguments)
                        tool_output = str(exec_result.result) if exec_result.success else f"Error: {exec_result.error}"
                        messages.append({"role": "assistant", "content": f"[Executed {tool_call.name}]"})
                        messages.append({"role": "user", "content": f"Tool result: {tool_output}"})
                
                # Get final response
                result = await provider.generate_with_tools(
                    messages=messages,
                    tools=tools,
                    temperature=0.7,
                )
            
            response = result.text or "Task completed."
            
            # Send result to admin
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"✅ Task completed:\n\n{response[:3500]}",
            )
            
        except Exception as e:
            logger.error(f"Scheduled job {job.id} failed: {e}")
            try:
                await context.bot.send_message(
                    chat_id=self.config.telegram.admin_id,
                    text=f"❌ Scheduled task failed: {job.description}\n\nError: {e}",
                )
            except Exception:
                pass
    
    async def run(self):
        """Run the bot."""
        await self.initialize()
        
        logger.info("Starting Tele-Agent bot...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        
        # Start scheduler after bot is running
        await self.scheduler.start()
        logger.info(f"Scheduler started with {len(self.scheduler.list_jobs())} jobs")
        
        logger.info("Tele-Agent is running. Press Ctrl+C to stop.")
        
        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("Shutting down...")
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
    
    @property
    def uptime(self) -> str:
        """Get formatted uptime string."""
        delta = datetime.now() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m {seconds}s"


def main():
    """Entry point."""
    agent = TeleAgent()
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")


if __name__ == "__main__":
    main()
