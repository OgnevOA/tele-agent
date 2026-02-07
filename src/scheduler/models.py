"""Data models for scheduled jobs."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional
from pathlib import Path


@dataclass
class ScheduledJob:
    """A persisted scheduled job."""
    id: str
    task: str  # Text prompt for AI to execute
    cron: str  # Cron expression (e.g., "0 9 * * *")
    description: str  # Human-readable schedule description
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run: Optional[str] = None
    
    @classmethod
    def create(cls, task: str, cron: str, description: str) -> "ScheduledJob":
        """Create a new scheduled job with generated ID."""
        return cls(
            id=str(uuid.uuid4())[:8],
            task=task,
            cron=cron,
            description=description,
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledJob":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class PendingJob:
    """A job awaiting user confirmation before being saved."""
    id: str
    task: str
    cron: str
    description: str
    message_id: int  # Telegram message ID for the confirmation prompt
    
    @classmethod
    def create(cls, task: str, cron: str, description: str, message_id: int = 0) -> "PendingJob":
        """Create a new pending job."""
        return cls(
            id=str(uuid.uuid4())[:8],
            task=task,
            cron=cron,
            description=description,
            message_id=message_id,
        )
    
    def to_scheduled_job(self) -> ScheduledJob:
        """Convert to a scheduled job after confirmation."""
        return ScheduledJob(
            id=self.id,
            task=self.task,
            cron=self.cron,
            description=self.description,
        )


class JobStore:
    """Persistent storage for scheduled jobs."""
    
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._jobs: dict[str, ScheduledJob] = {}
        self._load()
    
    def _load(self) -> None:
        """Load jobs from disk."""
        if self.filepath.exists():
            try:
                data = json.loads(self.filepath.read_text(encoding="utf-8"))
                for job_data in data.get("jobs", []):
                    job = ScheduledJob.from_dict(job_data)
                    self._jobs[job.id] = job
            except Exception:
                pass
    
    def _save(self) -> None:
        """Save jobs to disk."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        data = {"jobs": [job.to_dict() for job in self._jobs.values()]}
        self.filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
    
    def add(self, job: ScheduledJob) -> None:
        """Add a new job."""
        self._jobs[job.id] = job
        self._save()
    
    def remove(self, job_id: str) -> Optional[ScheduledJob]:
        """Remove a job by ID."""
        job = self._jobs.pop(job_id, None)
        if job:
            self._save()
        return job
    
    def get(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a job by ID."""
        return self._jobs.get(job_id)
    
    def get_all(self) -> list[ScheduledJob]:
        """Get all jobs."""
        return list(self._jobs.values())
    
    def get_enabled(self) -> list[ScheduledJob]:
        """Get all enabled jobs."""
        return [job for job in self._jobs.values() if job.enabled]
    
    def update(self, job: ScheduledJob) -> None:
        """Update an existing job."""
        if job.id in self._jobs:
            self._jobs[job.id] = job
            self._save()
    
    def toggle_enabled(self, job_id: str) -> Optional[bool]:
        """Toggle job enabled state. Returns new state or None if not found."""
        job = self._jobs.get(job_id)
        if job:
            job.enabled = not job.enabled
            self._save()
            return job.enabled
        return None
    
    def mark_run(self, job_id: str) -> None:
        """Mark job as having just run."""
        job = self._jobs.get(job_id)
        if job:
            job.last_run = datetime.now().isoformat()
            self._save()
