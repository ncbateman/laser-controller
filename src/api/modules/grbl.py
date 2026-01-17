import time

import serial
from loguru import logger

from api.schemas import grbl as grbl_schemas

def parse_settings(settings_text: str) -> dict[int, float]:
    """
    Parse GRBL settings from $$ command response.

    Args:
        settings_text: Raw settings response from GRBL

    Returns:
        Dictionary mapping setting numbers to their float values
    """
    settings: dict[int, float] = {}
    for line in settings_text.split('\n'):
        line = line.strip()
        if not line or not line.startswith('$'):
            continue
        if '=' not in line:
            continue
        try:
            setting_part = line.split('=')[0]
            value_part = line.split('=')[1].split('(')[0].strip()
            setting_num = int(setting_part[1:])
            value = float(value_part)
            settings[setting_num] = value
        except (ValueError, IndexError):
            continue
    return settings

def create_grbl_connection(port: str = "/dev/ttyUSB1") -> grbl_schemas.GrblConnection:
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
        logger.info(f"Loading Settings...")
        grbl_ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(2)
        grbl_ser.write(b'\r\n\r\n')
        time.sleep(1)
        grbl_ser.read_all()

        settings_text = query_settings(grbl_ser)
        raw_settings = parse_settings(settings_text)
        settings = grbl_schemas.GrblSettings.from_raw_settings(raw_settings)

        logger.info(f"Settings loaded successfully on GRBL controller at {port}")

        return grbl_schemas.GrblConnection(port=port, serial=grbl_ser, settings=settings)
    except Exception as e:
        logger.error(f"Failed to connect to GRBL controller at {port}: {e}")
        if 'grbl_ser' in locals():
            try:
                grbl_ser.close()
            except Exception:
                pass
        raise RuntimeError(f"Failed to load settings from GRBL controller at {port}: {e}")

def send_command(ser: serial.Serial, request: grbl_schemas.GrblCommandRequest) -> grbl_schemas.GrblCommandResponse:
    """
    Send a GRBL command with retry logic and response handling.

    Args:
        ser: Serial connection to GRBL controller
        request: Command request containing command string, label, retries, and timeout

    Returns:
        grbl_schemas.GrblCommandResponse with success status, response text, and number of attempts

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
            return grbl_schemas.GrblCommandResponse(
                success=True,
                response=last_response,
                attempts=attempts + 1
            )
        attempts += 1

    return grbl_schemas.GrblCommandResponse(
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

def move_relative(ser: serial.Serial, x: float | None = None, y: float | None = None, z: float | None = None, feed: int | None = None) -> None:
    """
    Send relative movement command (G1 in relative mode).
    Automatically duplicates Y value to Z for dual motor Y axis configuration.

    Args:
        ser: Serial connection to GRBL controller
        x: X axis movement distance in mm
        y: Y axis movement distance in mm (will also move Z by same amount)
        z: Z axis movement distance in mm (ignored if y is provided, uses y value instead)
        feed: Feed rate in mm/min
    """
    parts = ["G1"]
    if x is not None:
        parts.append(f"X{x}")
    if y is not None:
        parts.append(f"Y{y}")
        parts.append(f"Z{y}")
    elif z is not None:
        parts.append(f"Z{z}")
    if feed is not None:
        parts.append(f"F{feed}")
    command = " ".join(parts) + "\n"
    ser.write(command.encode())

def move_absolute(ser: serial.Serial, x: float | None = None, y: float | None = None, z: float | None = None, feed: int | None = None) -> None:
    """
    Send absolute movement command (G1 in absolute mode).
    Automatically duplicates Y value to Z for dual motor Y axis configuration.

    Args:
        ser: Serial connection to GRBL controller
        x: X axis target position in mm
        y: Y axis target position in mm (will also set Z to same value)
        z: Z axis target position in mm (ignored if y is provided, uses y value instead)
        feed: Feed rate in mm/min
    """
    parts = ["G1"]
    if x is not None:
        parts.append(f"X{x}")
    if y is not None:
        parts.append(f"Y{y}")
        parts.append(f"Z{y}")
    elif z is not None:
        parts.append(f"Z{z}")
    if feed is not None:
        parts.append(f"F{feed}")
    command = " ".join(parts) + "\n"
    ser.write(command.encode())

def set_mode_relative(ser: serial.Serial) -> None:
    """
    Set GRBL to relative positioning mode (G91).

    Args:
        ser: Serial connection to GRBL controller
    """
    ser.write(b'G91\n')

def set_mode_absolute(ser: serial.Serial) -> None:
    """
    Set GRBL to absolute positioning mode (G90).

    Args:
        ser: Serial connection to GRBL controller
    """
    ser.write(b'G90\n')

def set_work_coordinate_offset(ser: serial.Serial, x: float | None = None, y: float | None = None, z: float | None = None) -> None:
    """
    Set work coordinate offset (G92).
    Automatically duplicates Y value to Z for dual motor Y axis configuration.

    Args:
        ser: Serial connection to GRBL controller
        x: X axis offset in mm
        y: Y axis offset in mm (will also set Z to same value)
        z: Z axis offset in mm (ignored if y is provided, uses y value instead)
    """
    parts = ["G92"]
    if x is not None:
        parts.append(f"X{x}")
    if y is not None:
        parts.append(f"Y{y}")
        parts.append(f"Z{y}")
    elif z is not None:
        parts.append(f"Z{z}")
    command = " ".join(parts) + "\n"
    ser.write(command.encode())

def set_setting(ser: serial.Serial, key: str, value: float, connection: grbl_schemas.GrblConnection | None = None) -> None:
    """
    Set GRBL setting parameter.

    Args:
        ser: Serial connection to GRBL controller
        key: Setting key name (e.g., "x_steps_per_mm", "step_idle_delay")
        value: Setting value
        connection: Optional GrblConnection to update cached settings and push to machine
    """
    if connection is not None:
        connection.update_setting(key, value)
    else:
        setting_num = grbl_schemas.KEY_TO_SETTING_NUM.get(key)
        if setting_num is None:
            raise ValueError(f"Unknown setting key: {key}")
        command = f'${setting_num}={value}\n'
        ser.write(command.encode())

def get_setting(connection: grbl_schemas.GrblConnection, key: str) -> float | None:
    """
    Get cached GRBL setting value.

    Args:
        connection: GrblConnection with cached settings
        key: Setting key name (e.g., "x_steps_per_mm", "step_idle_delay")

    Returns:
        Setting value if found, None otherwise
    """
    return connection.settings.get_setting_value(key)

def query_settings(ser: serial.Serial) -> str:
    """
    Query GRBL settings ($$ command).

    Args:
        ser: Serial connection to GRBL controller

    Returns:
        Settings response string
    """
    ser.write(b'$$\n')
    time.sleep(0.3)
    return ser.read_all().decode("utf-8", errors="ignore")

def unlock_alarm(ser: serial.Serial) -> None:
    """
    Unlock GRBL after alarm condition ($X command).

    Args:
        ser: Serial connection to GRBL controller
    """
    ser.write(b'$X\n')

def reset_grbl(ser: serial.Serial) -> None:
    """
    Reset GRBL controller (Ctrl-X, 0x18).

    Args:
        ser: Serial connection to GRBL controller
    """
    ser.write(b"\x18")
    time.sleep(1)

def feed_hold(ser: serial.Serial) -> None:
    """
    Send feed hold command (!).

    Args:
        ser: Serial connection to GRBL controller
    """
    ser.write(b"!")

def initialize_connection(ser: serial.Serial) -> None:
    """
    Initialize GRBL connection by sending wake-up sequence.

    Args:
        ser: Serial connection to GRBL controller
    """
    ser.write(b'\r\n\r\n')
    time.sleep(1)
    ser.read_all()
