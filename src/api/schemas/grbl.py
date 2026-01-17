import time

import serial

import pydantic

SETTING_NUM_TO_KEY: dict[int, str] = {
    0: "step_pulse_time",
    1: "step_idle_delay",
    2: "step_port_invert_mask",
    3: "direction_port_invert_mask",
    4: "step_enable_invert",
    5: "limit_pins_invert",
    6: "probe_pin_invert",
    10: "status_report_mask",
    11: "junction_deviation",
    12: "arc_tolerance",
    13: "arc_tolerance",
    20: "report_inches",
    21: "soft_limits",
    22: "hard_limits",
    23: "homing_cycle",
    24: "homing_dir_invert_mask",
    25: "homing_feed_rate",
    26: "homing_seek_rate",
    27: "homing_debounce_delay",
    28: "homing_pull_off",
    30: "max_spindle_speed",
    31: "min_spindle_speed",
    32: "laser_mode",
    100: "x_steps_per_mm",
    101: "y_steps_per_mm",
    102: "z_steps_per_mm",
    110: "x_max_rate",
    111: "y_max_rate",
    112: "z_max_rate",
    120: "x_acceleration",
    121: "y_acceleration",
    122: "z_acceleration",
    130: "x_max_travel",
    131: "y_max_travel",
    132: "z_max_travel",
}

KEY_TO_SETTING_NUM: dict[str, int] = {v: k for k, v in SETTING_NUM_TO_KEY.items()}

class GrblCommandRequest(pydantic.BaseModel):
    command: str
    label: str
    retries: int = 3
    timeout: float = 2.0

class GrblCommandResponse(pydantic.BaseModel):
    success: bool
    response: str
    attempts: int

class GrblSettings(pydantic.BaseModel):
    step_pulse_time: float | None = None
    step_idle_delay: float | None = None
    step_port_invert_mask: float | None = None
    direction_port_invert_mask: float | None = None
    step_enable_invert: float | None = None
    limit_pins_invert: float | None = None
    probe_pin_invert: float | None = None
    status_report_mask: float | None = None
    junction_deviation: float | None = None
    arc_tolerance: float | None = None
    report_inches: float | None = None
    soft_limits: float | None = None
    hard_limits: float | None = None
    homing_cycle: float | None = None
    homing_dir_invert_mask: float | None = None
    homing_feed_rate: float | None = None
    homing_seek_rate: float | None = None
    homing_debounce_delay: float | None = None
    homing_pull_off: float | None = None
    max_spindle_speed: float | None = None
    min_spindle_speed: float | None = None
    laser_mode: float | None = None
    x_steps_per_mm: float | None = None
    y_steps_per_mm: float | None = None
    z_steps_per_mm: float | None = None
    x_max_rate: float | None = None
    y_max_rate: float | None = None
    z_max_rate: float | None = None
    x_acceleration: float | None = None
    y_acceleration: float | None = None
    z_acceleration: float | None = None
    x_max_travel: float | None = None
    y_max_travel: float | None = None
    z_max_travel: float | None = None

    @classmethod
    def from_raw_settings(cls, raw_settings: dict[int, float]) -> "GrblSettings":
        """
        Create GrblSettings from raw settings dictionary mapping setting numbers to values.

        Args:
            raw_settings: Dictionary mapping setting numbers (e.g., 1, 100) to values

        Returns:
            GrblSettings instance with mapped properties
        """
        settings_dict: dict[str, float] = {}
        for setting_num, value in raw_settings.items():
            key = SETTING_NUM_TO_KEY.get(setting_num)
            if key is not None:
                settings_dict[key] = value
        return cls(**settings_dict)

    def get_setting_value(self, key: str) -> float | None:
        """
        Get setting value by key name.

        Args:
            key: Setting key name (e.g., "x_steps_per_mm", "step_idle_delay")

        Returns:
            Setting value if found, None otherwise
        """
        return getattr(self, key, None)

    def set_setting_value(self, key: str, value: float) -> None:
        """
        Set setting value by key name in cache only.

        Args:
            key: Setting key name (e.g., "x_steps_per_mm", "step_idle_delay")
            value: Setting value to set
        """
        if not hasattr(self, key):
            raise ValueError(f"Unknown setting key: {key}")
        setattr(self, key, value)

class GrblPosition(pydantic.BaseModel):
    x: float | None = None
    y: float | None = None
    z: float | None = None
    status: str = "Unknown"
    mode: str = "Unknown"
    raw: str = ""

class GrblConnection(pydantic.BaseModel):
    port: str
    serial: serial.Serial
    settings: GrblSettings

    model_config = {"arbitrary_types_allowed": True}

    def update_setting(self, key: str, value: float) -> None:
        """
        Update GRBL setting value and push to machine.

        Args:
            key: Setting key name (e.g., "x_steps_per_mm", "step_idle_delay")
            value: Setting value to set
        """
        setting_num = KEY_TO_SETTING_NUM.get(key)
        if setting_num is None:
            raise ValueError(f"Unknown setting key: {key}")
        command = f'${setting_num}={value}\n'
        self.serial.write(command.encode())
        time.sleep(0.2)
        self.settings.set_setting_value(key, value)
