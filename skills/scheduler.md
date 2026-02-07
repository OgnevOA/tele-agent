---
name: scheduler
description: Schedule tasks to run automatically at specified times. Use this to set reminders, schedule recurring checks, automate daily routines, or plan future actions. Supports natural language time conversion to cron format. IMPORTANT - When scheduling a new task, you MUST show the exact task text word-for-word and ask for confirmation before saving.
# Dependencies: none
---

# Task Scheduler

Schedule tasks to run automatically at specified times. Tasks are executed by the AI with full tool access.

## Usage Examples

- "Remind me to check emails every day at 9am"
- "Schedule a weather check every morning at 7:30"
- "Every Monday at 8am, summarize my calendar"
- "List my scheduled tasks"
- "Delete task abc123"
- "Pause task xyz789"

## Cron Format Reference

Format: `minute hour day_of_month month day_of_week`

Examples:
- `0 9 * * *` = Every day at 9:00 AM
- `30 8 * * 1` = Every Monday at 8:30 AM
- `0 18 * * 1-5` = Weekdays at 6:00 PM
- `0 * * * *` = Every hour
- `*/15 * * * *` = Every 15 minutes

```python
import json
from typing import Optional


def execute(
    action: str,
    task: Optional[str] = None,
    schedule: Optional[str] = None,
    cron: Optional[str] = None,
    job_id: Optional[str] = None,
) -> str:
    """
    Manage scheduled tasks.
    
    Args:
        action: One of 'schedule', 'list', 'delete', 'pause', 'resume', 'get'.
        task: For 'schedule' - The task text for AI to execute when triggered.
        schedule: For 'schedule' - Human-readable description (e.g., "every day at 9am").
        cron: For 'schedule' - Cron expression (e.g., "0 9 * * *").
        job_id: For 'delete', 'pause', 'resume', 'get' - The job ID.
    
    Returns:
        Result message or confirmation request.
    """
    action = action.lower().strip()
    
    if action == "schedule":
        return handle_schedule(task, schedule, cron)
    elif action == "list":
        return handle_list()
    elif action == "delete":
        return handle_delete(job_id)
    elif action == "pause":
        return handle_toggle(job_id, enable=False)
    elif action == "resume":
        return handle_toggle(job_id, enable=True)
    elif action == "get":
        return handle_get(job_id)
    else:
        return f"Unknown action: {action}. Use: schedule, list, delete, pause, resume, get"


def handle_schedule(task: Optional[str], schedule: Optional[str], cron: Optional[str]) -> str:
    """Request to schedule a new task - returns confirmation request."""
    if not task:
        return "Error: task text is required for scheduling."
    
    if not cron:
        return "Error: cron expression is required. Convert the time to cron format first."
    
    if not schedule:
        schedule = f"cron: {cron}"
    
    # Validate cron format
    parts = cron.strip().split()
    if len(parts) != 5:
        return f"Error: Invalid cron format '{cron}'. Expected 5 parts: minute hour day month day_of_week"
    
    # Return special format that triggers confirmation flow
    # The handler will parse this and show confirmation buttons
    confirmation = {
        "_type": "scheduler_confirmation",
        "task": task,
        "cron": cron,
        "description": schedule,
    }
    
    return f"CONFIRM_SCHEDULE:{json.dumps(confirmation)}"


def handle_list() -> str:
    """List all scheduled jobs."""
    from pathlib import Path
    
    jobs_file = Path("data/scheduled_jobs.json")
    if not jobs_file.exists():
        return "No scheduled tasks found."
    
    try:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
        jobs = data.get("jobs", [])
        
        if not jobs:
            return "No scheduled tasks found."
        
        lines = ["📅 Scheduled Tasks:\n"]
        for job in jobs:
            status = "✅" if job.get("enabled", True) else "⏸️"
            job_id = job.get("id", "?")
            desc = job.get("description", "No description")
            task = job.get("task", "")
            cron = job.get("cron", "")
            last_run = job.get("last_run")
            
            lines.append(f"{status} **{job_id}**: {desc}")
            lines.append(f"   Task: {task[:50]}{'...' if len(task) > 50 else ''}")
            lines.append(f"   Cron: `{cron}`")
            if last_run:
                lines.append(f"   Last run: {last_run[:19]}")
            lines.append("")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error reading jobs: {e}"


def handle_delete(job_id: Optional[str]) -> str:
    """Delete a scheduled job."""
    if not job_id:
        return "Error: job_id is required to delete a task."
    
    from pathlib import Path
    
    jobs_file = Path("data/scheduled_jobs.json")
    if not jobs_file.exists():
        return f"Job '{job_id}' not found."
    
    try:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
        jobs = data.get("jobs", [])
        
        # Find and remove job
        new_jobs = [j for j in jobs if j.get("id") != job_id]
        
        if len(new_jobs) == len(jobs):
            return f"Job '{job_id}' not found."
        
        # Save
        data["jobs"] = new_jobs
        jobs_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        
        # Return special format to trigger unregister in scheduler
        return f"SCHEDULER_DELETE:{job_id}"
        
    except Exception as e:
        return f"Error deleting job: {e}"


def handle_toggle(job_id: Optional[str], enable: bool) -> str:
    """Pause or resume a scheduled job."""
    if not job_id:
        return "Error: job_id is required."
    
    from pathlib import Path
    
    jobs_file = Path("data/scheduled_jobs.json")
    if not jobs_file.exists():
        return f"Job '{job_id}' not found."
    
    try:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
        jobs = data.get("jobs", [])
        
        found = False
        for job in jobs:
            if job.get("id") == job_id:
                job["enabled"] = enable
                found = True
                break
        
        if not found:
            return f"Job '{job_id}' not found."
        
        # Save
        data["jobs"] = jobs
        jobs_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        
        action = "resumed" if enable else "paused"
        return f"SCHEDULER_TOGGLE:{job_id}:{enable}"
        
    except Exception as e:
        return f"Error updating job: {e}"


def handle_get(job_id: Optional[str]) -> str:
    """Get details of a specific job."""
    if not job_id:
        return "Error: job_id is required."
    
    from pathlib import Path
    
    jobs_file = Path("data/scheduled_jobs.json")
    if not jobs_file.exists():
        return f"Job '{job_id}' not found."
    
    try:
        data = json.loads(jobs_file.read_text(encoding="utf-8"))
        jobs = data.get("jobs", [])
        
        for job in jobs:
            if job.get("id") == job_id:
                status = "Active" if job.get("enabled", True) else "Paused"
                return (
                    f"📅 Job: {job_id}\n"
                    f"Status: {status}\n"
                    f"Schedule: {job.get('description', 'N/A')}\n"
                    f"Cron: {job.get('cron', 'N/A')}\n"
                    f"Task: {job.get('task', 'N/A')}\n"
                    f"Created: {job.get('created_at', 'N/A')[:19]}\n"
                    f"Last run: {job.get('last_run', 'Never')[:19] if job.get('last_run') else 'Never'}"
                )
        
        return f"Job '{job_id}' not found."
        
    except Exception as e:
        return f"Error reading job: {e}"
```
