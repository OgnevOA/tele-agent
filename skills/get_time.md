---
title: Get Time
author: system
created: 2026-02-02
---

# Description
Get the current time and date. Use this when the user asks what time it is, 
what the date is, or needs the current timestamp.

# Dependencies

# Code
```python
from datetime import datetime

def execute(timezone="local"):
    """Get the current time and date."""
    now = datetime.now()
    return f"Current time: {now.strftime('%I:%M %p')}\nDate: {now.strftime('%A, %B %d, %Y')}"
```
