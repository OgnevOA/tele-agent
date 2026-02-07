"""Core scheduler using python-telegram-bot's JobQueue."""

import logging
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional, Callable, Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from telegram.ext import Application, ContextTypes

from .models import ScheduledJob, PendingJob, JobStore

logger = logging.getLogger(__name__)


def get_local_timezone() -> timezone:
    """Get the local system timezone."""
    # Get local UTC offset
    local_now = datetime.now()
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    offset = local_now - utc_now
    # Round to nearest minute to avoid floating point issues
    offset_seconds = round(offset.total_seconds() / 60) * 60
    return timezone(timedelta(seconds=offset_seconds))

# Storage for pending jobs awaiting confirmation
_pending_jobs: dict[str, PendingJob] = {}


def parse_cron(cron: str) -> dict:
    """Parse a cron expression into components.
    
    Format: minute hour day_of_month month day_of_week
    Example: "0 9 * * *" = every day at 9:00 AM
    
    Returns dict with parsed values or None for wildcards.
    """
    parts = cron.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron format: {cron}")
    
    minute, hour, day, month, dow = parts
    
    return {
        "minute": int(minute) if minute != "*" else None,
        "hour": int(hour) if hour != "*" else None,
        "day": day if day != "*" else None,
        "month": month if month != "*" else None,
        "day_of_week": dow if dow != "*" else None,
    }


def cron_to_time(cron: str, tz: timezone = None) -> Optional[time]:
    """Extract time from cron expression if it's a daily schedule.
    
    Args:
        cron: Cron expression string
        tz: Timezone to use (defaults to local timezone)
    """
    try:
        parsed = parse_cron(cron)
        if parsed["minute"] is not None and parsed["hour"] is not None:
            if tz is None:
                tz = get_local_timezone()
            return time(hour=parsed["hour"], minute=parsed["minute"], tzinfo=tz)
    except Exception:
        pass
    return None


def cron_to_interval_seconds(cron: str) -> Optional[int]:
    """Convert cron to interval in seconds for simple patterns."""
    parts = cron.strip().split()
    if len(parts) != 5:
        return None
    
    minute, hour, day, month, dow = parts
    
    # Every minute: * * * * *
    if all(p == "*" for p in parts):
        return 60
    
    # Every N minutes: */N * * * *
    if minute.startswith("*/") and hour == "*" and day == "*":
        try:
            return int(minute[2:]) * 60
        except ValueError:
            pass
    
    # Every hour: 0 * * * *
    if minute.isdigit() and hour == "*" and day == "*":
        return 3600
    
    # Every N hours: 0 */N * * *
    if minute.isdigit() and hour.startswith("*/") and day == "*":
        try:
            return int(hour[2:]) * 3600
        except ValueError:
            pass
    
    return None


class Scheduler:
    """Manages scheduled jobs with persistence and telegram-bot JobQueue integration."""
    
    def __init__(self, store_path: Path):
        """Initialize scheduler.
        
        Args:
            store_path: Path to the JSON file for persisting jobs.
        """
        self.store = JobStore(store_path)
        self.app: Optional[Application] = None
        self._job_callback: Optional[Callable] = None
    
    def set_app(self, app: Application) -> None:
        """Set the telegram application for JobQueue access."""
        self.app = app
    
    def set_job_callback(self, callback: Callable) -> None:
        """Set the callback to execute when a job triggers.
        
        Callback signature: async def callback(job: ScheduledJob, context: ContextTypes.DEFAULT_TYPE)
        """
        self._job_callback = callback
    
    async def start(self) -> None:
        """Start the scheduler and register all enabled jobs."""
        if not self.app:
            logger.warning("Scheduler started without app - jobs won't run")
            return
        
        jobs = self.store.get_enabled()
        logger.info(f"Loading {len(jobs)} scheduled jobs")
        
        for job in jobs:
            self._register_job(job)
    
    def _register_job(self, job: ScheduledJob) -> None:
        """Register a job with the telegram JobQueue."""
        if not self.app or not self.app.job_queue:
            logger.warning(f"Cannot register job {job.id} - no job queue")
            return
        
        # Remove existing job with same ID if any
        self._unregister_job(job.id)
        
        # Try to parse as interval first
        interval = cron_to_interval_seconds(job.cron)
        if interval:
            self.app.job_queue.run_repeating(
                self._job_trigger,
                interval=interval,
                first=10,  # Start 10 seconds after registration
                name=job.id,
                data=job,
            )
            logger.info(f"Registered repeating job {job.id}: every {interval}s")
            return
        
        # Try to parse as daily time with local timezone
        local_tz = get_local_timezone()
        run_time = cron_to_time(job.cron, local_tz)
        
        if run_time:
            # Log timezone info for debugging
            now = datetime.now()
            logger.info(f"Scheduling job {job.id} for {run_time} (TZ offset: {local_tz})")
            logger.info(f"Current local time: {now.strftime('%H:%M:%S')}")
            
            # Check day_of_week
            parsed = parse_cron(job.cron)
            days = None
            
            if parsed["day_of_week"] and parsed["day_of_week"] != "*":
                dow = parsed["day_of_week"]
                # Convert cron days to python-telegram-bot days
                # Cron: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
                # PTB:  0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
                def cron_to_ptb_day(cron_day: int) -> int:
                    return (cron_day - 1) % 7
                
                if "-" in dow:
                    start, end = dow.split("-")
                    cron_days = range(int(start), int(end) + 1)
                    days = tuple(cron_to_ptb_day(d) for d in cron_days)
                elif "," in dow:
                    cron_days = [int(d) for d in dow.split(",")]
                    days = tuple(cron_to_ptb_day(d) for d in cron_days)
                else:
                    days = (cron_to_ptb_day(int(dow)),)
            
            self.app.job_queue.run_daily(
                self._job_trigger,
                time=run_time,
                days=days,
                name=job.id,
                data=job,
            )
            # Log with day names for clarity
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            if days:
                day_str = ", ".join(day_names[d] for d in days)
                logger.info(f"Registered daily job {job.id}: at {run_time} on {day_str}")
            else:
                logger.info(f"Registered daily job {job.id}: at {run_time} every day")
            
            # Check if we missed this job and need to catch up
            self._check_missed_job(job, run_time, days)
            return
        
        logger.warning(f"Could not parse cron for job {job.id}: {job.cron}")
    
    def _check_missed_job(self, job: ScheduledJob, run_time: time, days: tuple = None) -> None:
        """Check if we missed this job today and run it immediately if so."""
        now = datetime.now()
        today_weekday = now.weekday()  # 0=Monday, 6=Sunday (same as PTB)
        
        # Check if today is a valid day for this job
        if days is not None and today_weekday not in days:
            logger.debug(f"Job {job.id}: today ({today_weekday}) not in scheduled days {days}")
            return
        
        # Check if the scheduled time has passed today
        current_time = now.time()
        scheduled_time_naive = time(run_time.hour, run_time.minute)
        
        if current_time <= scheduled_time_naive:
            logger.debug(f"Job {job.id}: scheduled time {run_time} hasn't passed yet")
            return
        
        # Check if the job already ran today
        if job.last_run:
            last_run_date = datetime.fromisoformat(job.last_run).date()
            if last_run_date == now.date():
                logger.debug(f"Job {job.id}: already ran today at {job.last_run}")
                return
        
        # We missed this job! Run it immediately
        logger.info(f"⚡ Job {job.id} missed its scheduled time today - running now!")
        self.app.job_queue.run_once(
            self._job_trigger,
            when=5,  # Run in 5 seconds
            name=f"{job.id}_catchup",
            data=job,
        )
    
    def _unregister_job(self, job_id: str) -> None:
        """Remove a job from the JobQueue."""
        if not self.app or not self.app.job_queue:
            return
        
        jobs = self.app.job_queue.get_jobs_by_name(job_id)
        for job in jobs:
            job.schedule_removal()
    
    async def _job_trigger(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Called when a scheduled job triggers."""
        job: ScheduledJob = context.job.data
        
        logger.info(f"🔔 JOB TRIGGERED: {job.id} - {job.description}")
        logger.info(f"   Task: {job.task[:100]}...")
        
        # Mark as run
        self.store.mark_run(job.id)
        
        # Execute callback
        if self._job_callback:
            try:
                logger.info(f"   Executing callback for job {job.id}")
                await self._job_callback(job, context)
                logger.info(f"   ✅ Job {job.id} completed successfully")
            except Exception as e:
                logger.error(f"   ❌ Job {job.id} execution error: {e}", exc_info=True)
        else:
            logger.warning(f"   No callback set for job {job.id}")
    
    # --- Pending Job Management ---
    
    def add_pending(self, pending: PendingJob) -> None:
        """Add a job to pending confirmation."""
        _pending_jobs[pending.id] = pending
    
    def get_pending(self, job_id: str) -> Optional[PendingJob]:
        """Get a pending job by ID."""
        return _pending_jobs.get(job_id)
    
    def remove_pending(self, job_id: str) -> Optional[PendingJob]:
        """Remove a pending job."""
        return _pending_jobs.pop(job_id, None)
    
    def confirm_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Confirm a pending job, save it, and register with scheduler."""
        pending = self.remove_pending(job_id)
        if not pending:
            return None
        
        job = pending.to_scheduled_job()
        self.store.add(job)
        self._register_job(job)
        
        logger.info(f"Confirmed and scheduled job {job.id}: {job.description}")
        return job
    
    def cancel_pending(self, job_id: str) -> bool:
        """Cancel a pending job confirmation."""
        return self.remove_pending(job_id) is not None
    
    # --- Job Management ---
    
    def list_jobs(self) -> list[ScheduledJob]:
        """List all scheduled jobs."""
        return self.store.get_all()
    
    def delete_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Delete a job by ID."""
        self._unregister_job(job_id)
        return self.store.remove(job_id)
    
    def toggle_job(self, job_id: str) -> Optional[bool]:
        """Toggle job enabled state. Returns new state."""
        new_state = self.store.toggle_enabled(job_id)
        
        if new_state is not None:
            job = self.store.get(job_id)
            if job:
                if new_state:
                    self._register_job(job)
                else:
                    self._unregister_job(job_id)
        
        return new_state
    
    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a job by ID."""
        return self.store.get(job_id)
