import time

import serial
from loguru import logger
from pydantic import BaseModel

class GrblCommandRequest(BaseModel):
    command: str
    label: str
    retries: int = 3
    timeout: float = 2.0

class GrblCommandResponse(BaseModel):
    success: bool
    response: str
    attempts: int

class GrblConnection(BaseModel):
    port: str
    serial: serial.Serial

    model_config = {"arbitrary_types_allowed": True}

def create_grbl_connection(port: str = "/dev/ttyUSB1") -> GrblConnection:
    """
    Create and initialize a serial connection to GRBL controller.

    Args:
        port: Serial port path for GRBL controller (default: /dev/ttyUSB1)

    Returns:
        GrblConnection with port and initialized serial connection

    Raises:
        RuntimeError: If connection cannot be established or initialized
    """
    try:
        grbl_ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(2)
        grbl_ser.write(b'\r\n\r\n')
        time.sleep(1)
        grbl_ser.read_all()
        return GrblConnection(port=port, serial=grbl_ser)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to GRBL controller at {port}: {e}")

def send_command(ser: serial.Serial, request: GrblCommandRequest) -> GrblCommandResponse:
    """
    Send a GRBL command with retry logic and response handling.

    Args:
        ser: Serial connection to GRBL controller
        request: Command request containing command string, label, retries, and timeout

    Returns:
        GrblCommandResponse with success status, response text, and number of attempts

    Raises:
        None - always returns a response, even on failure
    """
    attempts = 0
    last_response = ""

    while attempts < request.retries:
        ser.reset_input_buffer()
        ser.write((request.command + "\n").encode())
        deadline = time.time() + request.timeout
        response_parts = []
        result = None

        while time.time() < deadline and result is None:
            line_bytes = ser.readline()
            if not line_bytes:
                continue
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            response_parts.append(line)
            lower = line.lower()
            if lower == "ok":
                result = "ok"
            if lower.startswith("error:") or lower.startswith("alarm:"):
                result = "error"

        last_response = "\n".join(response_parts)
        if last_response:
            logger.debug(f"{request.label}: {last_response}")

        if result == "ok":
            return GrblCommandResponse(
                success=True,
                response=last_response,
                attempts=attempts + 1
            )
        attempts += 1

    return GrblCommandResponse(
        success=False,
        response=last_response,
        attempts=attempts
    )

def send_raw_command(ser: serial.Serial, command: bytes, wait_time: float = 0.2) -> None:
    """
    Send a raw byte command to GRBL without waiting for response.

    Args:
        ser: Serial connection to GRBL controller
        command: Raw bytes command to send
        wait_time: Time to wait after sending command in seconds
    """
    ser.write(command)
    time.sleep(wait_time)

def read_response(ser: serial.Serial, timeout: float = 0.2) -> str:
    """
    Read response from GRBL serial connection.

    Args:
        ser: Serial connection to GRBL controller
        timeout: Time to wait for response in seconds

    Returns:
        Decoded response string, empty if no response
    """
    time.sleep(timeout)
    response = ser.read_all().decode('utf-8', errors='ignore').strip()
    return response
