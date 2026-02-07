---
name: web_search
description: Search the web using Brave Search API. Use this to find current information, news, facts, documentation, or any real-time data. Returns relevant web results with titles, descriptions, and URLs.
# Dependencies: requests
---

# Web Search (Brave Search API)

Search the web for real-time information using the Brave Search API.

## Usage Examples

- "Search for the latest news about AI"
- "Find information about Python async programming"
- "What's the weather in New York?"
- "Search for TrueNAS Scale documentation"
- "Look up Home Assistant integrations"

```python
import os
import requests
from typing import Optional


def get_brave_api_key() -> str:
    """Get Brave Search API key from environment variable."""
    return os.environ.get("BRAVE_API_KEY", "")


def execute(
    query: str,
    count: int = 5,
    freshness: Optional[str] = None,
    country: str = "us",
) -> str:
    """
    Search the web using Brave Search API.
    
    Args:
        query: The search query string.
        count: Number of results to return (1-20, default 5).
        freshness: Filter by time - 'pd' (past day), 'pw' (past week), 'pm' (past month), 'py' (past year), or None for all.
        country: Country code for results (default 'us').
    
    Returns:
        Formatted search results with titles, descriptions, and URLs.
    """
    api_key = get_brave_api_key()
    
    if not api_key:
        return "Error: BRAVE_API_KEY environment variable not configured."
    
    # Validate count
    count = max(1, min(20, count))
    
    # Build request
    url = "https://api.search.brave.com/res/v1/web/search"
    
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    
    params = {
        "q": query,
        "count": count,
        "country": country,
        "search_lang": "en",
        "text_decorations": False,
    }
    
    # Add freshness filter if specified
    if freshness and freshness in ("pd", "pw", "pm", "py"):
        params["freshness"] = freshness
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Format results
        results = []
        
        # Web results
        web_results = data.get("web", {}).get("results", [])
        
        if not web_results:
            return f"No results found for: {query}"
        
        for i, result in enumerate(web_results[:count], 1):
            title = result.get("title", "No title")
            description = result.get("description", "No description")
            url = result.get("url", "")
            
            results.append(f"{i}. **{title}**\n   {description}\n   🔗 {url}")
        
        # Check for news results
        news_results = data.get("news", {}).get("results", [])
        if news_results:
            results.append("\n📰 **Related News:**")
            for news in news_results[:3]:
                title = news.get("title", "")
                source = news.get("meta_url", {}).get("hostname", "")
                age = news.get("age", "")
                results.append(f"   • {title} ({source}, {age})")
        
        return "\n\n".join(results)
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return "Error: Invalid Brave Search API key. Please check your BRAVE_API_KEY."
        elif e.response.status_code == 429:
            return "Error: Rate limit exceeded. Please wait and try again."
        else:
            return f"Error: HTTP {e.response.status_code} - {str(e)}"
    except requests.exceptions.RequestException as e:
        return f"Error searching: {str(e)}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
```
