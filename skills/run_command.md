---
title: Run Command
author: system
created: 2026-02-02
---

# Description
Execute shell or PowerShell commands on the system. Use this when the user asks to 
run a command, execute a script, check system status, list files, or perform any 
shell operation. Supports both Windows (PowerShell) and Linux (bash).

WARNING: This is a powerful skill. Use with caution.

# Dependencies

# Code
```python
import subprocess
import platform
import shlex

# Commands that are blocked for safety
BLOCKED_COMMANDS = [
    "rm -rf /",
    "del /f /s /q c:",
    "format c:",
    "mkfs",
    ":(){:|:&};:",  # Fork bomb
]

def execute(command: str, shell: str = "auto", timeout: int = 30):
    """
    Execute a shell command and return the output.
    
    Args:
        command: The command to execute
        shell: "powershell", "bash", "cmd", or "auto" (detect based on OS)
        timeout: Max seconds to wait for command (default 30)
    
    Returns:
        Command output or error message
    """
    # Safety check
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return f"⚠️ Blocked dangerous command: {command}"
    
    # Determine shell
    is_windows = platform.system() == "Windows"
    
    if shell == "auto":
        shell = "powershell" if is_windows else "bash"
    
    try:
        if shell == "powershell":
            # Run via PowerShell
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        elif shell == "cmd":
            # Run via CMD
            result = subprocess.run(
                ["cmd", "/c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        else:
            # Run via bash
            result = subprocess.run(
                ["bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if result.returncode != 0:
            if error:
                return f"❌ Error (exit {result.returncode}):\n{error}"
            return f"❌ Command failed with exit code {result.returncode}"
        
        if output:
            # Truncate very long output
            if len(output) > 3000:
                output = output[:3000] + "\n... (truncated)"
            return output
        
        return "✓ Command completed successfully (no output)"
        
    except subprocess.TimeoutExpired:
        return f"⏱️ Command timed out after {timeout} seconds"
    except FileNotFoundError:
        return f"❌ Shell '{shell}' not found on this system"
    except Exception as e:
        return f"❌ Error: {e}"
```
