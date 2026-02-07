---
name: home_assistant
description: Control Home Assistant smart home devices. Use this to turn lights on/off, adjust brightness, control switches, set thermostat temperature, activate scenes, run scripts, and get device states. Supports lights, switches, climate, covers, media players, scenes, scripts, and automations.
# Dependencies: requests
---

# Home Assistant Control

Control your smart home via Home Assistant's REST API.

## Usage Examples

- "Turn on the living room lights"
- "Set bedroom brightness to 50%"
- "What's the temperature in the house?"
- "Turn off all lights"
- "Activate movie night scene"
- "Set thermostat to 22 degrees"
- "List all my lights"

```python
import os
import requests
from typing import Optional, Any


def get_ha_config() -> tuple[str, str]:
    """Get Home Assistant URL and token from environment variables."""
    url = os.environ.get("HA_URL", "")
    token = os.environ.get("HA_TOKEN", "")
    
    if not url or not token:
        raise ValueError(
            "Home Assistant not configured. Set HA_URL and HA_TOKEN environment variables."
        )
    
    return url.rstrip('/'), token


def ha_request(
    method: str,
    endpoint: str,
    data: Optional[dict] = None
) -> dict[str, Any]:
    """Make authenticated request to Home Assistant API."""
    url, token = get_ha_config()
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    full_url = f"{url}/api/{endpoint.lstrip('/')}"
    
    response = requests.request(
        method=method,
        url=full_url,
        headers=headers,
        json=data,
        timeout=30
    )
    
    if response.status_code == 401:
        raise ValueError("Invalid Home Assistant token. Check your HA_TOKEN environment variable.")
    elif response.status_code == 404:
        raise ValueError(f"Endpoint not found: {endpoint}")
    
    response.raise_for_status()
    
    if response.text:
        return response.json()
    return {"status": "ok"}


def execute(
    action: str,
    entity_id: Optional[str] = None,
    domain: Optional[str] = None,
    brightness: Optional[int] = None,
    temperature: Optional[float] = None,
    hvac_mode: Optional[str] = None,
    color_temp: Optional[int] = None,
    rgb_color: Optional[list[int]] = None,
    position: Optional[int] = None,
    volume: Optional[float] = None,
) -> str:
    """
    Control Home Assistant devices.
    
    Args:
        action: Action to perform. Options:
            - "list" - List entities (use domain to filter: lights, switches, climate, etc.)
            - "state" - Get state of an entity
            - "on" - Turn on entity
            - "off" - Turn off entity
            - "toggle" - Toggle entity
            - "scene" - Activate a scene
            - "script" - Run a script
            - "set_temp" - Set thermostat temperature
            - "info" - Get HA system info
        entity_id: The entity ID (e.g., "light.living_room", "switch.fan")
        domain: Entity domain for listing (e.g., "light", "switch", "climate")
        brightness: Brightness 0-255 for lights
        temperature: Temperature for climate devices
        hvac_mode: HVAC mode (heat, cool, auto, off)
        color_temp: Color temperature in mireds (153-500)
        rgb_color: RGB color as [R, G, B] (0-255 each)
        position: Position 0-100 for covers
        volume: Volume 0.0-1.0 for media players
    
    Returns:
        Result message or entity state
    """
    action = action.lower().strip()
    
    # === INFO ===
    if action == "info":
        result = ha_request("GET", "")
        return f"Home Assistant {result.get('version', 'unknown')} - {result.get('location_name', 'Home')}"
    
    # === LIST ENTITIES ===
    if action == "list":
        states = ha_request("GET", "states")
        
        if domain:
            domain = domain.lower().rstrip('s')  # "lights" -> "light"
            states = [s for s in states if s['entity_id'].startswith(f"{domain}.")]
        
        if not states:
            return f"No {domain or 'entities'} found."
        
        # Group by domain
        by_domain: dict[str, list] = {}
        for state in states:
            d = state['entity_id'].split('.')[0]
            if d not in by_domain:
                by_domain[d] = []
            
            name = state.get('attributes', {}).get('friendly_name', state['entity_id'])
            status = state['state']
            by_domain[d].append(f"• {name} ({state['entity_id']}): {status}")
        
        result_lines = []
        for d, entities in sorted(by_domain.items()):
            result_lines.append(f"\n**{d.title()}s** ({len(entities)})")
            result_lines.extend(entities[:10])  # Limit per domain
            if len(entities) > 10:
                result_lines.append(f"  ... and {len(entities) - 10} more")
        
        return '\n'.join(result_lines)
    
    # === GET STATE ===
    if action == "state":
        if not entity_id:
            return "Please specify an entity_id"
        
        result = ha_request("GET", f"states/{entity_id}")
        
        attrs = result.get('attributes', {})
        name = attrs.get('friendly_name', entity_id)
        state = result['state']
        
        info = [f"**{name}**: {state}"]
        
        # Add relevant attributes
        if 'brightness' in attrs:
            pct = round(attrs['brightness'] / 255 * 100)
            info.append(f"Brightness: {pct}%")
        if 'current_temperature' in attrs:
            info.append(f"Current: {attrs['current_temperature']}°")
        if 'temperature' in attrs:
            info.append(f"Target: {attrs['temperature']}°")
        if 'hvac_mode' in attrs:
            info.append(f"Mode: {attrs['hvac_mode']}")
        
        return '\n'.join(info)
    
    # === CONTROL ACTIONS ===
    if action in ("on", "off", "toggle", "turn_on", "turn_off"):
        if not entity_id:
            return "Please specify an entity_id"
        
        # Normalize action
        if action == "on":
            action = "turn_on"
        elif action == "off":
            action = "turn_off"
        
        # Determine domain from entity_id
        entity_domain = entity_id.split('.')[0]
        entity_name = entity_id.split('.')[1]
        
        # Build service data
        service_data = {"entity_id": entity_id}
        
        if brightness is not None and entity_domain == "light":
            service_data["brightness"] = max(0, min(255, brightness))
        if color_temp is not None and entity_domain == "light":
            service_data["color_temp"] = color_temp
        if rgb_color is not None and entity_domain == "light":
            service_data["rgb_color"] = rgb_color
        if position is not None and entity_domain == "cover":
            action = "set_cover_position"
            service_data["position"] = max(0, min(100, position))
        if volume is not None and entity_domain == "media_player":
            action = "volume_set"
            service_data["volume_level"] = max(0.0, min(1.0, volume))
        
        # Special handling for media_player turn_on (Apple TV, etc.)
        # Many media players need remote.turn_on to wake up
        if entity_domain == "media_player" and action == "turn_on":
            remote_entity = f"remote.{entity_name}"
            try:
                # Check if remote entity exists
                ha_request("GET", f"states/{remote_entity}")
                # If it exists, use remote.turn_on (more reliable for Apple TV, Fire TV, etc.)
                ha_request("POST", "services/remote/turn_on", {"entity_id": remote_entity})
                return f"✅ {entity_id} woken up via remote"
            except:
                # Fall back to media_player.turn_on
                pass
        
        ha_request("POST", f"services/{entity_domain}/{action}", service_data)
        
        action_word = action.replace('_', ' ').replace('turn ', '')
        return f"✅ {entity_id} turned {action_word}"
    
    # === SCENE ===
    if action == "scene":
        if not entity_id:
            return "Please specify a scene (e.g., 'movie_night' or 'scene.movie_night')"
        
        if not entity_id.startswith("scene."):
            entity_id = f"scene.{entity_id}"
        
        ha_request("POST", "services/scene/turn_on", {"entity_id": entity_id})
        return f"✅ Activated scene: {entity_id}"
    
    # === SCRIPT ===
    if action == "script":
        if not entity_id:
            return "Please specify a script (e.g., 'goodnight' or 'script.goodnight')"
        
        if not entity_id.startswith("script."):
            entity_id = f"script.{entity_id}"
        
        ha_request("POST", "services/script/turn_on", {"entity_id": entity_id})
        return f"✅ Ran script: {entity_id}"
    
    # === CLIMATE / SET TEMPERATURE ===
    if action in ("set_temp", "temperature", "climate"):
        if not entity_id:
            # Try to find a climate entity
            states = ha_request("GET", "states")
            climate_entities = [s for s in states if s['entity_id'].startswith("climate.")]
            if climate_entities:
                entity_id = climate_entities[0]['entity_id']
            else:
                return "No climate entities found. Please specify entity_id."
        
        if not entity_id.startswith("climate."):
            entity_id = f"climate.{entity_id}"
        
        service_data = {"entity_id": entity_id}
        
        if temperature is not None:
            service_data["temperature"] = temperature
        if hvac_mode is not None:
            service_data["hvac_mode"] = hvac_mode
        
        if temperature is not None:
            ha_request("POST", "services/climate/set_temperature", service_data)
            return f"✅ Set {entity_id} to {temperature}°"
        elif hvac_mode is not None:
            ha_request("POST", "services/climate/set_hvac_mode", service_data)
            return f"✅ Set {entity_id} mode to {hvac_mode}"
        else:
            return "Please specify temperature or hvac_mode"
    
    return f"Unknown action: {action}. Use: list, state, on, off, toggle, scene, script, set_temp, info"
```
