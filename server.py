"""
Fancy Control MCP Server
MCP-compliant HTTP Streamable server for controlling PowerExchange IoT devices
Based on decompiled Android app: FANCY_CONTROL_V7B
"""

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import StreamingResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("fancy-mcp-server")


class FancyControlConfig:
    """Configuration for PowerExchange device connection"""

    # Default tool descriptions
    DEFAULT_DESCRIPTIONS = {
        "freeze_lock": "FREEZE LOCK (BETA) - Activate Pet Training in freeze mode (mode 3/S2Z). When enabled, subject must stay completely still - any movement triggers a correction without warning.",
        "warning_buzzer": "Warning Buzzer - Enable or disable the warning buzzer on the device.",
        "pet_training": "Pet Training Mode - Enable or disable pet training mode with speed setting (normal, fast, or freeze).",
        "sleep_deprivation": "Sleep Deprivation Mode - Enable or disable sleep deprivation mode.",
        "random_mode": "Random Mode - Enable or disable random activation mode.",
        "timer": "Timer Mode - Enable or disable timer mode with optional duration in seconds.",
        "beep": "Beep - Send a beep signal to the device (equivalent to short button press).",
        "shock": "Shock - Send a shock signal with specified power level (equivalent to long button press).",
        "power_control": "Power Control - Adjust the device power level.",
        "send_raw_command": "Send a raw HTTP command to the device. For advanced users.",
    }

    def __init__(self):
        self.device_ip = os.getenv("DEVICE_IP")
        self.device_port = os.getenv("DEVICE_PORT", "80")
        self.auth_token = os.getenv("MCP_AUTH_TOKEN")
        self.context_description = os.getenv("MCP_CONTEXT_DESCRIPTION", "")

        # Safety: Maximum power limit (0-100)
        max_power_env = os.getenv("MCP_SAFETY_MAX_POWER_0_100")
        self.max_power = int(max_power_env) if max_power_env else None
        if self.max_power is not None:
            self.max_power = max(0, min(100, self.max_power))
            logger.info(f"Safety max power limit set to: {self.max_power}%")

        # Load tool descriptions from environment variables
        self.tool_descriptions = {}
        for tool_name, default_desc in self.DEFAULT_DESCRIPTIONS.items():
            env_var = f"TOOL_DESC_{tool_name.upper()}"
            self.tool_descriptions[tool_name] = os.getenv(env_var, default_desc)

        if not self.device_ip:
            logger.warning("DEVICE_IP not set - device commands will fail until configured")

        if not self.auth_token:
            raise ValueError("MCP_AUTH_TOKEN environment variable is required")

        self.base_url = f"http://{self.device_ip}:{self.device_port}" if self.device_ip else None

        if self.base_url:
            logger.info(f"Device API configured: {self.base_url}")
        logger.info("Authentication enabled")
        if self.context_description:
            logger.info(f"Context description: {self.context_description}")

    def get_tool_description(self, tool_name: str) -> str:
        """Get tool description with optional context prefix"""
        desc = self.tool_descriptions.get(tool_name, "")
        if self.context_description:
            return f"[{self.context_description}] {desc}"
        return desc


class FancyControlAPIClient:
    """Async client for PowerExchange device HTTP API"""

    def __init__(self, config: FancyControlConfig):
        self.config = config
        self.http_client: Optional[httpx.AsyncClient] = None
        self.current_power = 50  # Default power level (0-100)

    async def __aenter__(self):
        """Setup async HTTP client"""
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            follow_redirects=True
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup async HTTP client"""
        if self.http_client:
            await self.http_client.aclose()

    def _get_base_url(self) -> str:
        """Get base URL, raise error if not configured"""
        if not self.config.base_url:
            raise ValueError("Device IP not configured. Set DEVICE_IP environment variable.")
        return self.config.base_url

    async def send_get_command(self, endpoint: str) -> dict[str, Any]:
        """Send GET command to device"""
        try:
            base_url = self._get_base_url()
            url = f"{base_url}{endpoint}"
            logger.info(f"Sending GET request to: {url}")

            response = await self.http_client.get(url)
            response.raise_for_status()

            # Try to parse JSON, otherwise return text
            try:
                result = response.json()
            except:
                result = {"response": response.text}

            logger.info(f"Command successful: {endpoint}")
            return {"success": True, "data": result, "endpoint": endpoint}

        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {str(e)}")
            return {"success": False, "error": str(e), "endpoint": endpoint}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"success": False, "error": str(e), "endpoint": endpoint}

    # === FREEZE LOCK Control (Pet Training Mode 3) ===
    async def freeze_lock_on(self) -> dict[str, Any]:
        """Enable FREEZE LOCK - activates Pet Training in freeze mode (S2Z)"""
        return await self.send_get_command("/mode/S2Z")

    async def freeze_lock_off(self) -> dict[str, Any]:
        """Disable FREEZE LOCK - disables Pet Training mode"""
        return await self.send_get_command("/mode/0")

    # === Warning Buzzer Control ===
    async def warning_buzzer_on(self) -> dict[str, Any]:
        """Enable warning buzzer"""
        return await self.send_get_command("/S1/1")

    async def warning_buzzer_off(self) -> dict[str, Any]:
        """Disable warning buzzer"""
        return await self.send_get_command("/S1/0")

    # === Pet Training Mode ===
    async def pet_training_on(self, mode: str = "normal") -> dict[str, Any]:
        """Enable Pet Training mode"""
        if mode == "fast":
            return await self.send_get_command("/mode/S2F")
        elif mode == "freeze":
            return await self.send_get_command("/mode/S2Z")
        else:
            return await self.send_get_command("/mode/S2")

    async def pet_training_off(self) -> dict[str, Any]:
        """Disable Pet Training mode"""
        return await self.send_get_command("/mode/0")

    # === Sleep Deprivation Mode ===
    async def sleep_deprivation_on(self) -> dict[str, Any]:
        """Enable Sleep Deprivation mode"""
        return await self.send_get_command("/mode/S4")

    async def sleep_deprivation_off(self) -> dict[str, Any]:
        """Disable Sleep Deprivation mode"""
        return await self.send_get_command("/mode/0")

    # === Random Mode ===
    async def random_on(self) -> dict[str, Any]:
        """Enable Random mode"""
        return await self.send_get_command("/mode/RN")

    async def random_off(self) -> dict[str, Any]:
        """Disable Random mode"""
        return await self.send_get_command("/mode/0")

    # === Timer Mode ===
    async def timer_on(self) -> dict[str, Any]:
        """Enable Timer mode"""
        return await self.send_get_command("/mode/TM")

    async def timer_off(self) -> dict[str, Any]:
        """Disable Timer mode"""
        return await self.send_get_command("/mode/0")

    async def timer1_increase(self) -> dict[str, Any]:
        """Increase timer 1 value"""
        return await self.send_get_command("/T1/+")

    async def timer1_decrease(self) -> dict[str, Any]:
        """Decrease timer 1 value"""
        return await self.send_get_command("/T1/-")

    async def timer2_increase(self) -> dict[str, Any]:
        """Increase timer 2 value"""
        return await self.send_get_command("/T2/+")

    async def timer2_decrease(self) -> dict[str, Any]:
        """Decrease timer 2 value"""
        return await self.send_get_command("/T2/-")

    # === Beep Control (Short press) ===
    async def beep(self) -> dict[str, Any]:
        """Send a beep signal (equivalent to short button press)"""
        return await self.send_get_command("/B1/1")

    # === Shock Control (Long press) ===
    async def shock(self) -> dict[str, Any]:
        """Send a shock signal (equivalent to long button press)"""
        return await self.send_get_command("/Z1/1")

    # === Power Control ===
    async def power_increase(self) -> dict[str, Any]:
        """Increase power level"""
        result = await self.send_get_command("/PW/+")
        if result["success"] and self.current_power < 100:
            self.current_power = min(100, self.current_power + 5)
        return result

    async def power_decrease(self) -> dict[str, Any]:
        """Decrease power level"""
        result = await self.send_get_command("/PW/-")
        if result["success"] and self.current_power > 0:
            self.current_power = max(0, self.current_power - 5)
        return result

    async def set_power(self, target_power: int) -> dict[str, Any]:
        """Set power to a specific level (0-100), respecting safety max power limit"""
        original_target = target_power
        target_power = max(0, min(100, target_power))

        # Apply safety max power limit if configured
        if self.config.max_power is not None:
            target_power = min(target_power, self.config.max_power)

        results = []

        # Calculate steps needed (each step is ~5%)
        steps_needed = (target_power - self.current_power) // 5

        if steps_needed > 0:
            for _ in range(abs(steps_needed)):
                result = await self.power_increase()
                results.append(result)
                if not result["success"]:
                    break
                await asyncio.sleep(0.1)  # Small delay between commands
        elif steps_needed < 0:
            for _ in range(abs(steps_needed)):
                result = await self.power_decrease()
                results.append(result)
                if not result["success"]:
                    break
                await asyncio.sleep(0.1)

        self.current_power = target_power
        data = {"power_level": target_power, "steps": len(results)}

        # Add info if power was limited by safety setting
        if self.config.max_power is not None and original_target > target_power:
            data["power_limited_from"] = original_target
            data["safety_max_power"] = self.config.max_power

        return {
            "success": True,
            "data": data,
            "endpoint": f"power_set_{target_power}"
        }

    # === Combined Shock with Power ===
    async def shock_with_power(self, power: int) -> dict[str, Any]:
        """Send shock at specific power level, respecting safety max power limit"""
        # Apply safety max power limit if configured
        original_power = power
        if self.config.max_power is not None:
            power = min(power, self.config.max_power)

        # First set the power level
        power_result = await self.set_power(power)
        if not power_result["success"]:
            return power_result

        # Then send the shock
        shock_result = await self.shock()
        data = {
            "power_level": power,
            "shock_sent": shock_result["success"],
            "shock_response": shock_result.get("data", {})
        }
        # Add info if power was limited by safety setting
        if self.config.max_power is not None and original_power > power:
            data["power_limited_from"] = original_power
            data["safety_max_power"] = self.config.max_power

        return {
            "success": shock_result["success"],
            "data": data,
            "endpoint": f"shock_power_{power}"
        }

    # === Generic Command ===
    async def send_raw_command(self, command: str) -> dict[str, Any]:
        """Send raw command to device"""
        if not command.startswith("/"):
            command = "/" + command
        return await self.send_get_command(command)


# Global state
config: Optional[FancyControlConfig] = None
api_client: Optional[FancyControlAPIClient] = None
sessions: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources"""
    global config, api_client

    # Startup
    try:
        config = FancyControlConfig()
        api_client = FancyControlAPIClient(config)
        await api_client.__aenter__()
        logger.info("Server started successfully")
    except Exception as e:
        logger.error(f"Startup error: {str(e)}")
        raise

    yield

    # Shutdown
    if api_client:
        await api_client.__aexit__(None, None, None)
    logger.info("Server shutting down")


# Create FastAPI app
app = FastAPI(title="Fancy Control MCP Server", lifespan=lifespan)


async def verify_token(authorization: Optional[str] = Header(None)) -> bool:
    """Verify Bearer token - accepts both 'Bearer <token>' and '<token>' formats"""
    if not authorization:
        logger.warning("Missing Authorization header")
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Extract token - handle both "Bearer token" and "token" formats
    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token[7:]  # Remove "Bearer " prefix

    if token != config.auth_token:
        logger.warning("Invalid authentication token provided")
        raise HTTPException(status_code=403, detail="Invalid authentication token")

    return True


def handle_initialize(request_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Handle MCP initialize request"""
    session_id = str(uuid.uuid4())
    sessions[session_id] = {"initialized": True}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
                "prompts": {}
            },
            "serverInfo": {
                "name": "fancy-control-mcp-server",
                "version": "2.0.0"
            }
        },
        "_session_id": session_id
    }


def handle_tools_list(request_id: str) -> dict[str, Any]:
    """Handle MCP tools/list request"""

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "freeze_lock",
                    "description": config.get_tool_description("freeze_lock"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to lock/freeze, 'off' to unlock",
                                "enum": ["on", "off"]
                            }
                        },
                        "required": ["action"]
                    }
                },
                {
                    "name": "warning_buzzer",
                    "description": config.get_tool_description("warning_buzzer"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable buzzer, 'off' to disable",
                                "enum": ["on", "off"]
                            }
                        },
                        "required": ["action"]
                    }
                },
                {
                    "name": "pet_training",
                    "description": config.get_tool_description("pet_training"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable, 'off' to disable",
                                "enum": ["on", "off"]
                            },
                            "mode": {
                                "type": "string",
                                "description": "Training mode: 'normal' (S2), 'fast' (S2F), or 'freeze' (S2Z - stay still, no warning). Only used when action is 'on'.",
                                "enum": ["normal", "fast", "freeze"],
                                "default": "normal"
                            }
                        },
                        "required": ["action"]
                    }
                },
                {
                    "name": "sleep_deprivation",
                    "description": config.get_tool_description("sleep_deprivation"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable, 'off' to disable",
                                "enum": ["on", "off"]
                            }
                        },
                        "required": ["action"]
                    }
                },
                {
                    "name": "random_mode",
                    "description": config.get_tool_description("random_mode"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable random mode, 'off' to disable",
                                "enum": ["on", "off"]
                            }
                        },
                        "required": ["action"]
                    }
                },
                {
                    "name": "timer",
                    "description": config.get_tool_description("timer"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable timer mode, 'off' to disable, 't1_up'/'t1_down' to adjust timer 1, 't2_up'/'t2_down' to adjust timer 2",
                                "enum": ["on", "off", "t1_up", "t1_down", "t2_up", "t2_down"]
                            }
                        },
                        "required": ["action"]
                    }
                },
                {
                    "name": "beep",
                    "description": config.get_tool_description("beep"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                },
                {
                    "name": "shock",
                    "description": config.get_tool_description("shock"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "power": {
                                "type": "integer",
                                "description": "Power level from 1 to 100 percent",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 50
                            }
                        }
                    }
                },
                {
                    "name": "power_control",
                    "description": config.get_tool_description("power_control"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'increase' to raise power, 'decrease' to lower power, 'set' to set specific level",
                                "enum": ["increase", "decrease", "set"]
                            },
                            "level": {
                                "type": "integer",
                                "description": "Power level (0-100), only used when action is 'set'",
                                "minimum": 0,
                                "maximum": 100
                            }
                        },
                        "required": ["action"]
                    }
                },
                {
                    "name": "send_raw_command",
                    "description": config.get_tool_description("send_raw_command"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Raw command path (e.g., '/REL/1', '/mode/S2', '/TX?param=value')"
                            }
                        },
                        "required": ["command"]
                    }
                }
            ]
        }
    }


async def handle_tools_call(request_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Handle MCP tools/call request"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    try:
        result = None

        if tool_name == "freeze_lock":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.freeze_lock_on()
            else:
                result = await api_client.freeze_lock_off()

        elif tool_name == "warning_buzzer":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.warning_buzzer_on()
            else:
                result = await api_client.warning_buzzer_off()

        elif tool_name == "pet_training":
            action = arguments.get("action", "off")
            if action == "on":
                mode = arguments.get("mode", "normal")
                result = await api_client.pet_training_on(mode)
            else:
                result = await api_client.pet_training_off()

        elif tool_name == "sleep_deprivation":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.sleep_deprivation_on()
            else:
                result = await api_client.sleep_deprivation_off()

        elif tool_name == "random_mode":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.random_on()
            else:
                result = await api_client.random_off()

        elif tool_name == "timer":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.timer_on()
            elif action == "off":
                result = await api_client.timer_off()
            elif action == "t1_up":
                result = await api_client.timer1_increase()
            elif action == "t1_down":
                result = await api_client.timer1_decrease()
            elif action == "t2_up":
                result = await api_client.timer2_increase()
            elif action == "t2_down":
                result = await api_client.timer2_decrease()
            else:
                result = await api_client.timer_off()

        elif tool_name == "beep":
            result = await api_client.beep()

        elif tool_name == "shock":
            power = arguments.get("power", 50)
            result = await api_client.shock_with_power(power)

        elif tool_name == "power_control":
            action = arguments.get("action", "increase")
            if action == "increase":
                result = await api_client.power_increase()
            elif action == "decrease":
                result = await api_client.power_decrease()
            elif action == "set":
                level = arguments.get("level", 50)
                result = await api_client.set_power(level)

        elif tool_name == "send_raw_command":
            command = arguments.get("command", "")
            if not command:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Command parameter is required"
                    }
                }
            result = await api_client.send_raw_command(command)

        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}"
                }
            }

        if result and result.get("success"):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Success: Command '{tool_name}' executed.\nEndpoint: {result.get('endpoint', 'N/A')}\nResponse: {json.dumps(result.get('data', {}), indent=2)}"
                        }
                    ]
                }
            }
        else:
            error_msg = result.get("error", "Unknown error") if result else "No response"
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32000,
                    "message": f"Failed to execute '{tool_name}': {error_msg}"
                }
            }

    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": f"Execution error: {str(e)}"
            }
        }


def handle_resources_list(request_id: str) -> dict[str, Any]:
    """Handle MCP resources/list request"""
    prefix = get_context_prefix()

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "resources": [
                {
                    "uri": "fancy://config/device",
                    "name": "Device Configuration",
                    "description": f"{prefix}Current device connection configuration and status",
                    "mimeType": "application/json"
                },
                {
                    "uri": "fancy://info/endpoints",
                    "name": "Available Endpoints",
                    "description": f"{prefix}List of all available device control endpoints",
                    "mimeType": "application/json"
                }
            ]
        }
    }


async def handle_resources_read(request_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Handle MCP resources/read request"""
    uri = params.get("uri")

    try:
        if uri == "fancy://config/device":
            config_info = {
                "device_ip": config.device_ip or "Not configured",
                "device_port": config.device_port,
                "base_url": config.base_url or "Not configured",
                "context_description": config.context_description or "None",
                "current_power_level": api_client.current_power if api_client else 0,
                "status": "connected" if config.base_url else "not_configured"
            }
            content = json.dumps(config_info, indent=2)

        elif uri == "fancy://info/endpoints":
            endpoints_info = {
                "freeze_lock": {
                    "on": "/mode/S2Z",
                    "off": "/mode/0",
                    "note": "Freeze Lock activates Pet Training mode 3 (S2Z) - stay still, no warning"
                },
                "warning_buzzer": {
                    "on": "/S1/1",
                    "off": "/S1/0"
                },
                "pet_training": {
                    "normal": "/mode/S2",
                    "fast": "/mode/S2F",
                    "freeze": "/mode/S2Z",
                    "off": "/mode/0"
                },
                "sleep_deprivation": {
                    "on": "/mode/S4",
                    "off": "/mode/0"
                },
                "random": {
                    "on": "/mode/RN",
                    "off": "/mode/0"
                },
                "timer": {
                    "on": "/mode/TM",
                    "off": "/mode/0",
                    "set_seconds": "/T1/{seconds}"
                },
                "beep": "/B1/1",
                "shock": "/Z1/1",
                "power": {
                    "increase": "/PW/+",
                    "decrease": "/PW/-"
                }
            }
            content = json.dumps(endpoints_info, indent=2)

        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message": f"Unknown resource URI: {uri}"
                }
            }

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": content
                    }
                ]
            }
        }

    except Exception as e:
        logger.error(f"Resource read error: {str(e)}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": f"Failed to read resource: {str(e)}"
            }
        }


def handle_prompts_list(request_id: str) -> dict[str, Any]:
    """Handle MCP prompts/list request"""
    prefix = get_context_prefix()

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "prompts": [
                {
                    "name": "quick_shock",
                    "description": f"{prefix}Quick shock with specified power level",
                    "arguments": [
                        {
                            "name": "power",
                            "description": "Power level (1-100)",
                            "required": True
                        }
                    ]
                },
                {
                    "name": "enable_mode",
                    "description": f"{prefix}Enable a specific device mode",
                    "arguments": [
                        {
                            "name": "mode",
                            "description": "Mode: pet_training, sleep_deprivation, random, timer",
                            "required": True
                        }
                    ]
                }
            ]
        }
    }


def handle_prompts_get(request_id: str, params: dict[str, Any]) -> dict[str, Any]:
    """Handle MCP prompts/get request"""
    prompt_name = params.get("name")
    arguments = params.get("arguments", {})

    if prompt_name == "quick_shock":
        power = arguments.get("power", 50)
        message = f"Send a shock at {power}% power using the shock tool."
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "description": f"Quick shock at {power}%",
                "messages": [{"role": "user", "content": {"type": "text", "text": message}}]
            }
        }

    elif prompt_name == "enable_mode":
        mode = arguments.get("mode", "pet_training")
        message = f"Enable {mode} mode on the device."
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "description": f"Enable {mode}",
                "messages": [{"role": "user", "content": {"type": "text", "text": message}}]
            }
        }

    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": f"Unknown prompt: {prompt_name}"}
        }


@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """Main MCP endpoint with streaming support"""
    await verify_token(authorization)

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    method = body.get("method")
    request_id = body.get("id")
    params = body.get("params", {})

    logger.info(f"Received MCP request: method={method}, id={request_id}")

    session_id = None

    if method == "initialize":
        response = handle_initialize(request_id, params)
        session_id = response.pop("_session_id", None)
    elif method == "initialized":
        response = {"jsonrpc": "2.0", "id": request_id, "result": {}}
    elif method == "tools/list":
        response = handle_tools_list(request_id)
    elif method == "tools/call":
        response = await handle_tools_call(request_id, params)
    elif method == "resources/list":
        response = handle_resources_list(request_id)
    elif method == "resources/read":
        response = await handle_resources_read(request_id, params)
    elif method == "prompts/list":
        response = handle_prompts_list(request_id)
    elif method == "prompts/get":
        response = handle_prompts_get(request_id, params)
    elif method == "ping":
        response = {"jsonrpc": "2.0", "id": request_id, "result": {}}
    else:
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }

    async def generate():
        yield json.dumps(response).encode('utf-8')

    headers = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    return StreamingResponse(generate(), media_type="application/json", headers=headers)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    response = {
        "status": "healthy",
        "server": "fancy-control-mcp-server",
        "version": "2.0.0",
        "device_configured": bool(config and config.base_url),
        "device_ip": config.device_ip if config else None,
        "current_power": api_client.current_power if api_client else 0
    }
    # Add safety max power if configured
    if config and config.max_power is not None:
        response["safety_max_power"] = config.max_power
    return response


@app.get("/")
async def root():
    """Root endpoint with server info"""
    return {
        "name": "Fancy Control MCP Server",
        "version": "2.0.0",
        "description": "MCP server for controlling PowerExchange IoT devices",
        "mcp_endpoint": "/mcp",
        "health_endpoint": "/health",
        "tools": [
            "freeze_lock", "warning_buzzer", "pet_training",
            "sleep_deprivation", "random_mode", "timer",
            "beep", "shock", "power_control", "send_raw_command"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
