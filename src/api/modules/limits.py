import json
import time

import serial
from loguru import logger
from pydantic import BaseModel
from serial.tools import list_ports

class LimitSwitch(BaseModel):
    id: int
    state: int

class LimitControllerData(BaseModel):
    device: str
    switches: list[LimitSwitch]

class LimitSwitchStateRequest(BaseModel):
    switch_id: int
    timeout: float = 0.5

class LimitSwitchStateResponse(BaseModel):
    switch_id: int
    state: int
    found: bool

class LimitControllerConnection(BaseModel):
    port: str
    serial: serial.Serial

    model_config = {"arbitrary_types_allowed": True}

def find_limit_controller_port() -> str | None:
    """
    Scan all serial ports and find the one outputting limit controller JSON data.

    Returns:
        Port path string if limit controller found, None otherwise
    """
    ports = list_ports.comports()
    for port_info in ports:
        try:
            ser = serial.Serial(port_info.device, 115200, timeout=0.1)
            time.sleep(2.5)
            ser.reset_input_buffer()
            deadline = time.time() + 1.0
            while time.time() < deadline:
                line = ser.readline()
                if line:
                    data = line.decode('utf-8', errors='ignore').strip()
                    if data.startswith('{'):
                        try:
                            json_data = json.loads(data)
                            if json_data.get('device') == 'limit-controller':
                                ser.close()
                                return port_info.device
                        except json.JSONDecodeError:
                            continue
            ser.close()
        except Exception:
            continue
    return None

def create_limit_controller_connection(port: str) -> LimitControllerConnection:
    """
    Create a serial connection to the limit controller.

    Args:
        port: Serial port path for limit controller

    Returns:
        LimitControllerConnection with port and serial connection

    Raises:
        RuntimeError: If connection cannot be established
    """
    try:
        limit_ser = serial.Serial(port, 115200, timeout=0.1)
        return LimitControllerConnection(port=port, serial=limit_ser)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to limit controller at {port}: {e}")

def read_limit_controller_data(limit_ser: serial.Serial, timeout: float = 0.5) -> LimitControllerData | None:
    """
    Read and parse limit controller JSON data from serial connection.

    Args:
        limit_ser: Serial connection to limit controller
        timeout: Maximum time to wait for data in seconds

    Returns:
        LimitControllerData if valid data received, None otherwise
    """
    limit_ser.reset_input_buffer()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = limit_ser.readline()
            if line:
                data = line.decode('utf-8', errors='ignore').strip()
                if data.startswith('{'):
                    try:
                        json_data = json.loads(data)
                        if json_data.get('device') == 'limit-controller':
                            switches_data = json_data.get('switches', [])
                            switches = [LimitSwitch(id=s.get('id'), state=s.get('state', 0)) for s in switches_data]
                            return LimitControllerData(device=json_data.get('device', 'limit-controller'), switches=switches)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    return None

def get_switch_state(limit_ser: serial.Serial, request: LimitSwitchStateRequest) -> LimitSwitchStateResponse:
    """
    Read state of a specific limit switch from limit controller.

    Args:
        limit_ser: Serial connection to limit controller
        request: Request containing switch_id and timeout

    Returns:
        LimitSwitchStateResponse with switch state (1=pressed, 0=not pressed) and found status
    """
    limit_ser.reset_input_buffer()
    deadline = time.time() + request.timeout
    while time.time() < deadline:
        try:
            line = limit_ser.readline()
            if line:
                data = line.decode('utf-8', errors='ignore').strip()
                if data.startswith('{'):
                    try:
                        json_data = json.loads(data)
                        switches = json_data.get('switches', [])
                        for switch in switches:
                            if switch.get('id') == request.switch_id:
                                state = switch.get('state', 0)
                                return LimitSwitchStateResponse(
                                    switch_id=request.switch_id,
                                    state=state,
                                    found=True
                                )
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

    return LimitSwitchStateResponse(
        switch_id=request.switch_id,
        state=0,
        found=False
    )

def get_all_switches_state(limit_ser: serial.Serial, timeout: float = 0.5) -> dict[int, int] | None:
    """
    Read state of all limit switches from limit controller.

    Args:
        limit_ser: Serial connection to limit controller
        timeout: Maximum time to wait for data in seconds

    Returns:
        Dictionary mapping switch_id to state (1=pressed, 0=not pressed), or None if no data received
    """
    data = read_limit_controller_data(limit_ser, timeout)
    if data:
        return {switch.id: switch.state for switch in data.switches}
    return None

def check_switch_pressed(limit_ser: serial.Serial, switch_ids: list[int], timeout: float = 0.01) -> bool:
    """
    Check if any of the specified switches are pressed.
    Optimized for fast polling with short timeout.

    Args:
        limit_ser: Serial connection to limit controller
        switch_ids: List of switch IDs to check
        timeout: Maximum time to wait for data in seconds

    Returns:
        True if any specified switch is pressed, False otherwise
    """
    limit_ser.reset_input_buffer()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = limit_ser.readline()
            if not line:
                continue
            data = line.decode('utf-8', errors='ignore').strip()
            if not data.startswith('{'):
                continue
            json_data = json.loads(data)
            switches = json_data.get('switches', [])
            for switch in switches:
                if switch.get('id') in switch_ids and switch.get('state') == 1:
                    return True
        except json.JSONDecodeError:
            continue
        except Exception:
            continue
    return False

def get_pressed_switch_id(limit_ser: serial.Serial, switch_ids: list[int], timeout: float = 0.01) -> int | None:
    """
    Get the ID of the first pressed switch from the specified list.
    Optimized for fast polling with short timeout.

    Args:
        limit_ser: Serial connection to limit controller
        switch_ids: List of switch IDs to check
        timeout: Maximum time to wait for data in seconds

    Returns:
        Switch ID if any specified switch is pressed, None otherwise
    """
    limit_ser.reset_input_buffer()
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = limit_ser.readline()
            if not line:
                continue
            data = line.decode('utf-8', errors='ignore').strip()
            if not data.startswith('{'):
                continue
            json_data = json.loads(data)
            switches = json_data.get('switches', [])
            for switch in switches:
                if switch.get('id') in switch_ids and switch.get('state') == 1:
                    return switch.get('id')
        except json.JSONDecodeError:
            continue
        except Exception:
            continue
    return None
