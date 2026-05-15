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
from fastapi.responses import StreamingResponse, JSONResponse, Response

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
        "device_config": "Device Config - Check or save device configuration (SSID, password, serial number, key).",
        "tilt": "Tilt - Check or save the device tilt position value.",
        "pet_training_freeze": "PET TRAINING FREEZE (BETA) - Activate Pet Training in freeze mode (mode 3/S2Z). When enabled, subject must stay completely still - any movement triggers a correction without warning.",
        "pet_training_fast": "PET TRAINING FAST - Activate Pet Training in fast mode (mode 2/S2F). Faster response time for training corrections.",
        "warning_buzzer": "Warning Buzzer - Enable or disable the warning buzzer on the device.",
        "pet_training": "Pet Training Mode - Enable or disable pet training mode (normal/S2). Use pet_training_fast or pet_training_freeze for other modes.",
        "sleep_deprivation": "Sleep Deprivation Mode - Enable or disable sleep deprivation mode.",
        "random_mode": "Random Mode - Enable or disable random activation mode.",
        "timer": "Timer Mode - Control timer mode: on/off, get values, increase/decrease timer1 or timer2.",
        "beep": "Beep - Send a beep signal to the device (equivalent to short button press).",
        "shock": "Shock - Send a shock signal with specified power level (equivalent to long button press).",
        "power_control": "Power Control - Increase or decrease the device power level. Device only supports increment/decrement, not absolute values.",
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

        except httpx.RemoteProtocolError as e:
            # Device disconnected without response - this is normal for some commands (like /mode/0)
            # Treat as success since the device received the command
            logger.info(f"Device disconnected after receiving command (normal behavior): {endpoint}")
            return {"success": True, "data": {"response": "Command sent, device disconnected (normal)"}, "endpoint": endpoint}
        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {str(e)}")
            return {"success": False, "error": str(e), "endpoint": endpoint}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"success": False, "error": str(e), "endpoint": endpoint}

    # === PET TRAINING FREEZE Control (Pet Training Mode 3) ===
    async def pet_training_freeze_on(self) -> dict[str, Any]:
        """Enable PET TRAINING FREEZE - activates Pet Training in freeze mode (S2Z)"""
        return await self.send_get_command("/mode/S2Z")

    async def pet_training_freeze_off(self) -> dict[str, Any]:
        """Disable PET TRAINING FREEZE - disables Pet Training mode"""
        return await self.send_get_command("/mode/0")

    # === PET TRAINING FAST Control (Pet Training Mode 2) ===
    async def pet_training_fast_on(self) -> dict[str, Any]:
        """Enable PET TRAINING FAST - activates Pet Training in fast mode (S2F)"""
        return await self.send_get_command("/mode/S2F")

    async def pet_training_fast_off(self) -> dict[str, Any]:
        """Disable PET TRAINING FAST - disables Pet Training mode"""
        return await self.send_get_command("/mode/0")

    # === Warning Buzzer Control ===
    async def warning_buzzer_on(self) -> dict[str, Any]:
        """Enable warning buzzer"""
        return await self.send_get_command("/S1/1")

    async def warning_buzzer_off(self) -> dict[str, Any]:
        """Disable warning buzzer"""
        return await self.send_get_command("/S1/0")

    # === Pet Training Mode (Normal/S2) ===
    async def pet_training_on(self) -> dict[str, Any]:
        """Enable Pet Training mode (normal/S2)"""
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

    async def timer_get(self) -> dict[str, Any]:
        """Get timer values from /DIS/TM endpoint"""
        result = await self.send_get_command("/DIS/TM")

        if result["success"]:
            response_text = result.get("data", {}).get("response", "")
            timer_data = self._parse_timer_response(response_text)
            result["data"] = {"timer": timer_data, "raw_response": response_text}

        return result

    def _parse_timer_response(self, response: str) -> dict[str, Any]:
        """Parse timer response (format: T1/<value> or T2/<value>)"""
        timer = {"timer1": None, "timer2": None}

        if not response:
            return timer

        parts = response.strip().split("/")
        if len(parts) >= 2:
            command = parts[0]
            try:
                value = int(parts[1])
                if command == "T1":
                    timer["timer1"] = value
                elif command == "T2":
                    timer["timer2"] = value
            except ValueError:
                pass

        return timer

    async def timer1_increase(self) -> dict[str, Any]:
        """Increase Timer 1 value"""
        return await self.send_get_command("/T1/+")

    async def timer1_decrease(self) -> dict[str, Any]:
        """Decrease Timer 1 value"""
        return await self.send_get_command("/T1/-")

    async def timer2_increase(self) -> dict[str, Any]:
        """Increase Timer 2 value"""
        return await self.send_get_command("/T2/+")

    async def timer2_decrease(self) -> dict[str, Any]:
        """Decrease Timer 2 value"""
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
    @staticmethod
    def _parse_pw_response(data: Any) -> Optional[int]:
        # Device returns "PW/<int>" as text/html
        text = data.get("response") if isinstance(data, dict) else None
        if not isinstance(text, str):
            return None
        parts = text.strip().split("/")
        if len(parts) == 2 and parts[0] == "PW":
            try:
                return int(parts[1])
            except ValueError:
                return None
        return None

    async def power_increase(self) -> dict[str, Any]:
        """Increase power level"""
        result = await self.send_get_command("/PW/+")
        if result["success"]:
            parsed = self._parse_pw_response(result.get("data"))
            if parsed is not None:
                self.current_power = parsed
        return result

    async def power_decrease(self) -> dict[str, Any]:
        """Decrease power level"""
        result = await self.send_get_command("/PW/-")
        if result["success"]:
            parsed = self._parse_pw_response(result.get("data"))
            if parsed is not None:
                self.current_power = parsed
        return result

    async def set_power(self, target_power: int, step: int = 5) -> dict[str, Any]:
        """Set power to a specific level (0-100), respecting safety max power limit"""
        target_power = max(0, min(100, target_power))
        step = max(1, min(50, step))  # Ensure step is between 1 and 50

        # Apply safety max power limit if configured (silent)
        if self.config.max_power is not None:
            target_power = min(target_power, self.config.max_power)

        results = []

        # Calculate steps needed based on the step size
        steps_needed = (target_power - self.current_power) // step

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

        return {
            "success": True,
            "data": {"power_level": target_power, "steps": len(results), "step_size": step},
            "endpoint": f"power_set_{target_power}"
        }

    # === Combined Shock with Power ===
    async def shock_with_power(self, power: int) -> dict[str, Any]:
        """Send shock at specific power level, respecting safety max power limit"""
        # Apply safety max power limit if configured (silent)
        if self.config.max_power is not None:
            power = min(power, self.config.max_power)

        # First set the power level
        power_result = await self.set_power(power)
        if not power_result["success"]:
            return power_result

        # Then send the shock
        shock_result = await self.shock()

        return {
            "success": shock_result["success"],
            "data": {
                "power_level": power,
                "shock_sent": shock_result["success"],
                "shock_response": shock_result.get("data", {})
            },
            "endpoint": f"shock_power_{power}"
        }

    # === Device Config ===
    async def device_config_check(self) -> dict[str, Any]:
        """Check device configuration (SSID, password, serial, key) from /TX? endpoint"""
        result = await self.send_get_command("/TX?")

        if result["success"]:
            response_text = result.get("data", {}).get("response", "")
            config_data = self._parse_device_config(response_text)
            result["data"] = {"config": config_data, "raw_response": response_text}

        return result

    def _parse_device_config(self, response: str) -> dict[str, Any]:
        """Parse device config response into structured data
        Response format: COMMAND/SSID:value:PASSWORD:value:SERIAL:value:KEY:value
        """
        config = {
            "ssid": None,
            "password": None,
            "serial": None,
            "key": None
        }

        if not response:
            return config

        # Split by ":" to extract values
        parts = response.split(":")

        # Extract values based on position (indices 1, 3, 5, 7 after first split)
        if len(parts) >= 2:
            config["ssid"] = parts[1] if len(parts) > 1 else None
        if len(parts) >= 4:
            config["password"] = parts[3] if len(parts) > 3 else None
        if len(parts) >= 6:
            config["serial"] = parts[5] if len(parts) > 5 else None
        if len(parts) >= 8:
            config["key"] = parts[7] if len(parts) > 7 else None

        return config

    async def device_config_save(self, ssid: str, password: str) -> dict[str, Any]:
        """Save device configuration (SSID and password)"""
        return await self.send_get_command(f"/TX?SSIDX={ssid}&PASSX={password}")

    # === Tilt ===
    async def tilt_check(self) -> dict[str, Any]:
        """Check device tilt position from /DIS/BOW endpoint"""
        result = await self.send_get_command("/DIS/BOW")

        if result["success"]:
            response_text = result.get("data", {}).get("response", "")
            tilt_value = self._parse_tilt(response_text)
            result["data"] = {"tilt": tilt_value, "raw_response": response_text}

        return result

    def _parse_tilt(self, response: str) -> int | None:
        """Parse tilt response (format: BOW/value)"""
        if not response:
            return None

        parts = response.strip().split("/")
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except ValueError:
                return None
        return None

    async def tilt_save(self, value: int) -> dict[str, Any]:
        """Save device tilt position value"""
        return await self.send_get_command(f"/TX?TILTVAL={value}")

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


def get_context_prefix() -> str:
    """Return context description prefix for tool/resource/prompt descriptions"""
    if config and config.context_description:
        return f"[{config.context_description}] "
    return ""


SUPPORTED_PROTOCOL_VERSIONS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"]


def handle_initialize(request_id: str, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Handle MCP initialize request. Returns (response, session_id, negotiated_version) tuple."""
    session_id = str(uuid.uuid4())

    # Protocol version negotiation: use client's version if supported, otherwise our latest
    client_version = params.get("protocolVersion", SUPPORTED_PROTOCOL_VERSIONS[-1])
    if client_version in SUPPORTED_PROTOCOL_VERSIONS:
        negotiated_version = client_version
    else:
        negotiated_version = SUPPORTED_PROTOCOL_VERSIONS[-1]

    sessions[session_id] = {"initialized": True, "protocol_version": negotiated_version}

    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": negotiated_version,
            "capabilities": {
                "tools": {
                    "listChanged": False
                },
                "resources": {
                    "subscribe": False,
                    "listChanged": False
                },
                "prompts": {
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": "fancy-control-mcp-server",
                "title": "Fancy Control MCP Server",
                "version": "2.0.0",
                "description": "MCP server for controlling PowerExchange IoT devices"
            },
            "instructions": "This server controls PowerExchange IoT devices. Use the available tools to manage device modes, power levels, and settings."
        }
    }
    return response, session_id


def handle_tools_list(request_id: str) -> dict[str, Any]:
    """Handle MCP tools/list request"""

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {
                    "name": "device_config",
                    "title": "Device Configuration",
                    "description": config.get_tool_description("device_config"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'check' to retrieve config, 'save' to update SSID/password",
                                "enum": ["check", "save"]
                            },
                            "ssid": {
                                "type": "string",
                                "description": "New SSID (only used with 'save' action)"
                            },
                            "password": {
                                "type": "string",
                                "description": "New password (only used with 'save' action)"
                            }
                        },
                        "required": ["action"]
                    },
                    "annotations": {
                        "title": "Device Configuration",
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "tilt",
                    "title": "Tilt Control",
                    "description": config.get_tool_description("tilt"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'check' to retrieve tilt value, 'save' to set new value",
                                "enum": ["check", "save"]
                            },
                            "value": {
                                "type": "integer",
                                "description": "Tilt position value (only used with 'save' action)"
                            }
                        },
                        "required": ["action"]
                    },
                    "annotations": {
                        "title": "Tilt Control",
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "pet_training_freeze",
                    "title": "Pet Training Freeze",
                    "description": config.get_tool_description("pet_training_freeze"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable freeze training mode, 'off' to disable",
                                "enum": ["on", "off"]
                            }
                        },
                        "required": ["action"]
                    },
                    "annotations": {
                        "title": "Pet Training Freeze",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "pet_training_fast",
                    "title": "Pet Training Fast",
                    "description": config.get_tool_description("pet_training_fast"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable fast training mode, 'off' to disable",
                                "enum": ["on", "off"]
                            }
                        },
                        "required": ["action"]
                    },
                    "annotations": {
                        "title": "Pet Training Fast",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "warning_buzzer",
                    "title": "Warning Buzzer",
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
                    },
                    "annotations": {
                        "title": "Warning Buzzer",
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "pet_training",
                    "title": "Pet Training",
                    "description": config.get_tool_description("pet_training"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable normal pet training (S2), 'off' to disable",
                                "enum": ["on", "off"]
                            }
                        },
                        "required": ["action"]
                    },
                    "annotations": {
                        "title": "Pet Training",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "sleep_deprivation",
                    "title": "Sleep Deprivation",
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
                    },
                    "annotations": {
                        "title": "Sleep Deprivation",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "random_mode",
                    "title": "Random Mode",
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
                    },
                    "annotations": {
                        "title": "Random Mode",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "timer",
                    "title": "Timer Control",
                    "description": config.get_tool_description("timer"),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "Action: 'on' to enable, 'off' to disable, 'get' to read values, 't1_up'/'t1_down' for timer1, 't2_up'/'t2_down' for timer2",
                                "enum": ["on", "off", "get", "t1_up", "t1_down", "t2_up", "t2_down"]
                            }
                        },
                        "required": ["action"]
                    },
                    "annotations": {
                        "title": "Timer Control",
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "beep",
                    "title": "Beep",
                    "description": config.get_tool_description("beep"),
                    "inputSchema": {
                        "type": "object",
                        "additionalProperties": False
                    },
                    "annotations": {
                        "title": "Beep",
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "idempotentHint": True,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "shock",
                    "title": "Shock",
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
                    },
                    "annotations": {
                        "title": "Shock",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": False,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "power_control",
                    "title": "Power Control",
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
                            },
                            "step": {
                                "type": "integer",
                                "description": "Step size for power adjustment (default: 5), only used when action is 'set'",
                                "minimum": 1,
                                "maximum": 50,
                                "default": 5
                            }
                        },
                        "required": ["action"]
                    },
                    "annotations": {
                        "title": "Power Control",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": False,
                        "openWorldHint": True
                    }
                },
                {
                    "name": "send_raw_command",
                    "title": "Send Raw Command",
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
                    },
                    "annotations": {
                        "title": "Send Raw Command",
                        "readOnlyHint": False,
                        "destructiveHint": True,
                        "idempotentHint": False,
                        "openWorldHint": True
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

        if tool_name == "device_config":
            action = arguments.get("action", "check")
            if action == "check":
                result = await api_client.device_config_check()
            elif action == "save":
                ssid = arguments.get("ssid", "")
                password = arguments.get("password", "")
                if not ssid or not password:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": "Both 'ssid' and 'password' are required for save action"
                        }
                    }
                result = await api_client.device_config_save(ssid, password)

        elif tool_name == "tilt":
            action = arguments.get("action", "check")
            if action == "check":
                result = await api_client.tilt_check()
            elif action == "save":
                value = arguments.get("value", 0)
                result = await api_client.tilt_save(value)

        elif tool_name == "pet_training_freeze":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.pet_training_freeze_on()
            else:
                result = await api_client.pet_training_freeze_off()

        elif tool_name == "pet_training_fast":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.pet_training_fast_on()
            else:
                result = await api_client.pet_training_fast_off()

        elif tool_name == "warning_buzzer":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.warning_buzzer_on()
            else:
                result = await api_client.warning_buzzer_off()

        elif tool_name == "pet_training":
            action = arguments.get("action", "off")
            if action == "on":
                result = await api_client.pet_training_on()
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
            elif action == "get":
                result = await api_client.timer_get()
            elif action == "t1_up":
                result = await api_client.timer1_increase()
            elif action == "t1_down":
                result = await api_client.timer1_decrease()
            elif action == "t2_up":
                result = await api_client.timer2_increase()
            elif action == "t2_down":
                result = await api_client.timer2_decrease()

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
                step = arguments.get("step", 5)
                result = await api_client.set_power(level, step)

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
                    "code": -32602,
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
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error: Failed to execute '{tool_name}': {error_msg}"
                        }
                    ],
                    "isError": True
                }
            }

    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: Execution error: {str(e)}"
                    }
                ],
                "isError": True
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
                "device_config": {
                    "check": "/TX?",
                    "save": "/TX?SSIDX=<ssid>&PASSX=<password>",
                    "note": "Returns/saves device config: SSID, password, serial, key"
                },
                "tilt": {
                    "check": "/DIS/BOW",
                    "save": "/TX?TILTVAL=<value>",
                    "note": "Returns/saves device tilt position value"
                },
                "pet_training_freeze": {
                    "on": "/mode/S2Z",
                    "off": "/mode/0",
                    "note": "Pet Training Freeze activates mode 3 (S2Z) - stay still, no warning"
                },
                "pet_training_fast": {
                    "on": "/mode/S2F",
                    "off": "/mode/0",
                    "note": "Pet Training Fast activates Pet Training mode 2 (S2F) - faster response"
                },
                "warning_buzzer": {
                    "on": "/S1/1",
                    "off": "/S1/0"
                },
                "pet_training": {
                    "on": "/mode/S2",
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
                    "get": "/DIS/TM",
                    "t1_up": "/T1/+",
                    "t1_down": "/T1/-",
                    "t2_up": "/T2/+",
                    "t2_down": "/T2/-",
                    "note": "get returns T1/<value> or T2/<value>"
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
                    "code": -32002,
                    "message": f"Resource not found: {uri}"
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


def validate_origin(request: Request) -> None:
    """Validate Origin header to prevent DNS rebinding attacks (MUST per MCP 2025-11-25 spec)"""
    origin = request.headers.get("origin")
    if origin is not None:
        # Allow localhost origins and absent Origin headers
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        hostname = parsed.hostname or ""
        if hostname not in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            # Check allowed origins from environment
            allowed_origins = os.getenv("MCP_ALLOWED_ORIGINS", "").split(",")
            allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
            if allowed_origins and origin not in allowed_origins:
                logger.warning(f"Rejected request with invalid Origin: {origin}")
                raise HTTPException(status_code=403, detail="Forbidden: invalid Origin header")


def validate_protocol_version_header(request: Request) -> None:
    """Validate MCP-Protocol-Version header on non-initialize requests (MUST per MCP 2025-11-25 spec)"""
    version = request.headers.get("mcp-protocol-version")
    if version and version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported MCP-Protocol-Version: {version}")


def validate_session(request: Request, require: bool = True) -> Optional[str]:
    """Validate MCP-Session-Id header on subsequent requests (SHOULD per MCP 2025-11-25 spec)"""
    session_id = request.headers.get("mcp-session-id")
    if session_id:
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found or expired")
        return session_id
    elif require:
        raise HTTPException(status_code=400, detail="Missing MCP-Session-Id header")
    return None


@app.post("/mcp")
async def mcp_endpoint(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """Main MCP endpoint - POST handler for JSON-RPC messages"""
    await verify_token(authorization)
    validate_origin(request)

    # Validate Accept header (client MUST include application/json and text/event-stream)
    accept = request.headers.get("accept", "")
    if "application/json" not in accept and "text/event-stream" not in accept and "*/*" not in accept:
        raise HTTPException(status_code=406, detail="Accept header must include application/json and text/event-stream")

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    # Validate JSON-RPC 2.0 envelope
    if body.get("jsonrpc") != "2.0":
        return JSONResponse(content={
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "error": {"code": -32600, "message": "Invalid Request: missing or incorrect jsonrpc version, expected '2.0'"}
        })

    method = body.get("method")
    request_id = body.get("id")
    params = body.get("params", {})

    logger.info(f"Received MCP request: method={method}, id={request_id}")

    # JSON-RPC notifications have no "id" field and expect no response
    is_notification = request_id is None

    # Validate MCP-Protocol-Version header on non-initialize requests
    if method != "initialize":
        validate_protocol_version_header(request)

    # Validate session on non-initialize requests (SHOULD per spec)
    if method != "initialize":
        validate_session(request, require=False)

    # Handle notifications (no response expected per JSON-RPC spec)
    if method == "notifications/initialized":
        logger.info("Client initialized notification received")
        if is_notification:
            return Response(status_code=202)
        return JSONResponse(content={"jsonrpc": "2.0", "id": request_id, "result": {}})

    if is_notification and method.startswith("notifications/"):
        logger.info(f"Received notification: {method}")
        return Response(status_code=202)

    # Handle JSON-RPC responses from client (for server-initiated requests)
    if "result" in body or "error" in body:
        return Response(status_code=202)

    session_id = None
    response = None

    try:
        if method == "initialize":
            response, session_id = handle_initialize(request_id, params)
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
    except Exception as e:
        logger.error(f"Error handling MCP request: {str(e)}")
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }

    # Ensure response is never None
    if response is None:
        logger.error(f"Response is None for method {method}")
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32603, "message": "Internal error: No response generated"}
        }

    headers = {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    return JSONResponse(content=response, headers=headers)


@app.get("/mcp")
async def mcp_get_endpoint(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """MCP GET endpoint - for opening SSE streams (per MCP 2025-11-25 Streamable HTTP spec).
    This server does not support server-initiated requests, so returns 405."""
    await verify_token(authorization)
    validate_origin(request)

    # Accept header must include text/event-stream
    accept = request.headers.get("accept", "")
    if "text/event-stream" not in accept and "*/*" not in accept:
        raise HTTPException(status_code=406, detail="Accept header must include text/event-stream")

    # This server does not support server-to-client SSE streams
    return Response(status_code=405, headers={"Allow": "POST, DELETE"})


@app.delete("/mcp")
async def mcp_delete_endpoint(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization")
):
    """MCP DELETE endpoint - for client-initiated session termination (per MCP 2025-11-25 spec)"""
    await verify_token(authorization)
    validate_origin(request)

    session_id = request.headers.get("mcp-session-id")
    if session_id and session_id in sessions:
        del sessions[session_id]
        logger.info(f"Session terminated by client: {session_id}")
        return Response(status_code=200)
    elif session_id:
        raise HTTPException(status_code=404, detail="Session not found")
    else:
        raise HTTPException(status_code=400, detail="Missing MCP-Session-Id header")


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
            "device_config", "tilt", "pet_training_freeze", "pet_training_fast",
            "warning_buzzer", "pet_training", "sleep_deprivation", "random_mode", "timer",
            "beep", "shock", "power_control", "send_raw_command"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
