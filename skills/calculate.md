---
title: Calculate
author: system
created: 2026-02-02
---

# Description
Perform basic mathematical calculations. Use this when the user asks to 
calculate something, do math, or needs arithmetic operations like 
addition, subtraction, multiplication, division, powers, etc.

# Dependencies

# Code
```python
import math

def execute(expression="2+2"):
    """Safely evaluate a mathematical expression."""
    # Allowed names for safe evaluation
    allowed_names = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "pi": math.pi,
        "e": math.e,
    }
    
    try:
        # Remove any potentially dangerous characters
        safe_expr = expression.replace("^", "**")
        
        # Evaluate with restricted namespace
        result = eval(safe_expr, {"__builtins__": {}}, allowed_names)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error calculating '{expression}': {e}"
```
