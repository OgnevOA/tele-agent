---
title: Update Memory
author: system
created: 2026-02-02
---

# Description
Update the agent's memory and identity files. Use this when you need to save information 
about yourself, the user, your tools, or any persistent notes. This includes updating 
IDENTITY.md with your name/personality, USER.md with user info, TOOLS.md with environment 
details, or memory files for session notes.

Available files:
- IDENTITY.md: Your name, creature type, vibe, emoji, avatar
- USER.md: Information about your human (name, timezone, preferences)
- TOOLS.md: Environment-specific notes (camera names, SSH hosts, etc.)
- SOUL.md: Your core personality (be careful editing this!)
- memory/YYYY-MM-DD.md: Daily notes and logs

# Dependencies

# Code
```python
import os
from datetime import datetime
from pathlib import Path

# Allowed files that can be updated
ALLOWED_FILES = {
    "IDENTITY.md": "Your identity (name, vibe, emoji)",
    "USER.md": "Info about your human",
    "TOOLS.md": "Environment-specific notes",
    "SOUL.md": "Your core personality",
    "MEMORY.md": "Long-term curated memories",
}

def execute(
    action: str = "read",
    file: str = "IDENTITY.md",
    content: str = "",
    section: str = "",
):
    """
    Read or update agent memory/identity files.
    
    Args:
        action: "read", "write", "append", or "list"
        file: File to operate on (e.g., "IDENTITY.md", "USER.md", "memory/2026-02-02.md")
        content: Content to write or append
        section: Optional section name to update (for structured files)
    
    Returns:
        File content or confirmation message
    """
    # Handle daily memory files
    if file.startswith("memory/"):
        file_path = Path(file)
        file_path.parent.mkdir(exist_ok=True)
    elif file == "today":
        # Shortcut for today's memory file
        today = datetime.now().strftime("%Y-%m-%d")
        file_path = Path(f"memory/{today}.md")
        file_path.parent.mkdir(exist_ok=True)
    elif file in ALLOWED_FILES:
        file_path = Path(file)
    else:
        return f"❌ File '{file}' is not in the allowed list. Allowed: {', '.join(ALLOWED_FILES.keys())} or memory/YYYY-MM-DD.md"
    
    try:
        if action == "list":
            # List available files and their status
            result = "📁 **Available Memory Files:**\n\n"
            for name, desc in ALLOWED_FILES.items():
                exists = "✓" if Path(name).exists() else "✗"
                result += f"{exists} `{name}` - {desc}\n"
            
            # Check memory folder
            memory_dir = Path("memory")
            if memory_dir.exists():
                memory_files = sorted(memory_dir.glob("*.md"), reverse=True)[:5]
                if memory_files:
                    result += "\n📅 **Recent Memory Files:**\n"
                    for mf in memory_files:
                        result += f"  - `{mf}`\n"
            
            return result
        
        elif action == "read":
            if not file_path.exists():
                return f"📄 File `{file_path}` does not exist yet. Use action='write' to create it."
            return file_path.read_text(encoding="utf-8")
        
        elif action == "write":
            if not content:
                return "❌ No content provided. Use content='...' to specify what to write."
            
            # If section is provided, update just that section
            if section and file_path.exists():
                import re
                text = file_path.read_text(encoding="utf-8")
                
                # Try to match "## Section Name" header
                section_pattern = rf"(## {re.escape(section)}\n)(.+?)(?=\n## |\Z)"
                match = re.search(section_pattern, text, re.DOTALL)
                
                if match:
                    # Replace section content
                    new_text = text[:match.start(2)] + content + "\n" + text[match.end(2):]
                    file_path.write_text(new_text, encoding="utf-8")
                    return f"✓ Updated section '{section}' in `{file_path}`"
                
                # Try "**Section:**" format
                bold_pattern = rf"(\*\*{re.escape(section)}:\*\*\s*)(.+?)(?=\n\*\*|\n## |\Z)"
                match = re.search(bold_pattern, text, re.DOTALL)
                
                if match:
                    new_text = text[:match.start(2)] + content + text[match.end(2):]
                    file_path.write_text(new_text, encoding="utf-8")
                    return f"✓ Updated section '{section}' in `{file_path}`"
                
                # Section not found - append as new section
                new_text = text.rstrip() + f"\n\n## {section}\n{content}\n"
                file_path.write_text(new_text, encoding="utf-8")
                return f"✓ Added new section '{section}' to `{file_path}`"
            
            # No section - full file write
            file_path.write_text(content, encoding="utf-8")
            return f"✓ Written to `{file_path}` ({len(content)} chars)"
        
        elif action == "append":
            if not content:
                return "❌ No content provided. Use content='...' to specify what to append."
            
            existing = ""
            if file_path.exists():
                existing = file_path.read_text(encoding="utf-8")
            
            # Add timestamp for memory files
            if "memory/" in str(file_path):
                timestamp = datetime.now().strftime("%H:%M")
                content = f"\n\n## {timestamp}\n{content}"
            
            new_content = existing + content
            file_path.write_text(new_content, encoding="utf-8")
            return f"✓ Appended to `{file_path}` (+{len(content)} chars)"
        
        elif action == "update_section":
            if not section or not content:
                return "❌ Both 'section' and 'content' required for update_section"
            
            if not file_path.exists():
                return f"❌ File `{file_path}` does not exist"
            
            text = file_path.read_text(encoding="utf-8")
            
            # Find and replace section (markdown format)
            import re
            pattern = rf"(\*\*{re.escape(section)}:\*\*\s*)(.+?)(?=\n|$)"
            
            if re.search(pattern, text):
                new_text = re.sub(pattern, rf"\1{content}", text)
                file_path.write_text(new_text, encoding="utf-8")
                return f"✓ Updated section '{section}' in `{file_path}`"
            else:
                return f"❌ Section '{section}' not found in `{file_path}`"
        
        else:
            return f"❌ Unknown action '{action}'. Use: read, write, append, list, or update_section"
    
    except Exception as e:
        return f"❌ Error: {e}"
```
