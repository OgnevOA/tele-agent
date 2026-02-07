---
title: List Directory Files
author: user
created: 2026-02-02
---

# Description
list files in the current directory

# Dependencies
- subprocess

# Code
```python
import os
import subprocess

def execute(directory="."):
    try:
        # Get the absolute path
        target_dir = os.path.abspath(directory)
        
        # Check if directory exists
        if not os.path.isdir(target_dir):
            return f"Error: '{directory}' is not a valid directory"
        
        # List files in the directory
        items = os.listdir(target_dir)
        
        if not items:
            return f"No files or directories found in '{target_dir}'"
        
        # Sort items for better readability
        items.sort()
        
        # Format output
        result = f"Files in '{target_dir}':\n"
        for item in items:
            item_path = os.path.join(target_dir, item)
            if os.path.isdir(item_path):
                result += f"  [DIR]  {item}\n"
            else:
                result += f"  [FILE] {item}\n"
        
        return result
    
    except PermissionError:
        return f"Error: Permission denied accessing '{directory}'"
    except Exception as e:
        return f"Error listing files: {str(e)}"
```
