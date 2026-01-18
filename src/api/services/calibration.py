"""
IMPORTANT: DUAL MOTOR Y AXIS CONFIGURATION

The Z axis in this system is NOT a separate vertical axis. Instead, the Z axis motor
is actually a second Y axis motor, creating a dual-motor Y axis configuration.

This means:
- Y and Z axes MUST always move together with the SAME values
- Any Y movement command must also include Z with the same value
- Example: G1 Y100 Z100 (both move 100mm, not independent)
- The "Z" axis is just GRBL's way of controlling the second Y motor

All movement commands in this codebase that move Y must also move Z by the same amount.
This includes homing, calibration, outlining, and any other Y-axis movements.

DO NOT treat Z as an independent axis - it is always coupled with Y.
"""

import json
import time

import serial
from loguru import logger

from api.modules import grbl
from api.modules import limits
from api.schemas import grbl as grbl_schemas
from api.schemas import limits as limits_schemas



def move_until_limit_fast(grbl_ser: serial.Serial, limit_ser: serial.Serial, direction: str, switch_id: int, max_distance: float = 1000.0, feed: int = 800) -> tuple[bool, serial.Serial, float]:
    """
    Start a long move and stop when limit switch is pressed.
    Returns (success, new_serial, distance_traveled).
    Distance is calculated from elapsed time and feed rate.
    Note: Returns new serial connection after hard reset.
    """
    limit_ser.timeout = 0.01
    limit_ser.reset_input_buffer()

    grbl_ser.reset_input_buffer()
    if direction == "+":
        grbl.move_relative(grbl_ser, x=max_distance, feed=feed)
    else:
        grbl.move_relative(grbl_ser, x=-max_distance, feed=feed)
    start_time = time.time()

    while True:
        request = limits_schemas.LimitSwitchStateRequest(switch_id=switch_id, timeout=0.01)
        response = limits.get_switch_state(limit_ser, request)
        if response.state == 1:
            elapsed = time.time() - start_time
            distance = (elapsed * feed) / 60.0
            grbl.feed_hold(grbl_ser)
            time.sleep(0.1)
            grbl.reset_grbl(grbl_ser)
            grbl_ser.reset_input_buffer()
            grbl.unlock_alarm(grbl_ser)
            time.sleep(0.1)
            grbl.set_setting(grbl_ser, "step_idle_delay", 255)
            time.sleep(0.1)
            grbl_ser.read_all()
            return True, grbl_ser, distance

def move_until_limit_fast_y(grbl_ser: serial.Serial, limit_ser: serial.Serial, direction: str, switch_ids: list[int], max_distance: float = 1000.0, feed: int = 800) -> tuple[bool, serial.Serial, float]:
    """
    Start a long Y+Z move and stop when any of the limit switches is pressed.
    Moves both Y and Z together (dual motor Y axis).
    Returns (success, serial, distance_traveled).
    """
    limit_ser.timeout = 0.01
    limit_ser.reset_input_buffer()

    grbl_ser.reset_input_buffer()
    if direction == "+":
        grbl.move_relative(grbl_ser, y=max_distance, feed=feed)
    else:
        grbl.move_relative(grbl_ser, y=-max_distance, feed=feed)
    start_time = time.time()

    while True:
        pressed_switch_id = limits.get_pressed_switch_id(limit_ser, switch_ids, timeout=0.01)
        if pressed_switch_id is not None:
            elapsed = time.time() - start_time
            distance = (elapsed * feed) / 60.0

            grbl.feed_hold(grbl_ser)
            time.sleep(0.1)
            grbl.reset_grbl(grbl_ser)
            grbl_ser.reset_input_buffer()
            grbl.unlock_alarm(grbl_ser)
            time.sleep(0.1)
            grbl.set_setting(grbl_ser, "step_idle_delay", 255)
            time.sleep(0.1)
            grbl_ser.read_all()

            return True, grbl_ser, distance

def move_until_limit_y_independent(grbl_ser: serial.Serial, limit_ser: serial.Serial, direction: str, y_switch_id: int, z_switch_id: int, step_size: float = 0.1, feed: int = 200) -> tuple[bool, float]:
    """
    Step-by-step Y and Z independent movement until both switches are pressed.
    Moves Y and Z independently, stopping each motor when its switch is triggered.
    Used for auto-squaring on first fine approach.

    Args:
        grbl_ser: Serial connection to GRBL controller
        limit_ser: Serial connection to limit controller
        direction: Movement direction ("+" or "-")
        y_switch_id: Switch ID for Y axis motor
        z_switch_id: Switch ID for Z axis motor
        step_size: Step size in mm for each movement
        feed: Feed rate in mm/min

    Returns:
        Tuple of (success, distance_traveled) where distance is the maximum distance either motor traveled
    """
    y_distance = 0.0
    z_distance = 0.0
    y_switch_pressed = False
    z_switch_pressed = False
    move_time = (step_size / feed) * 60.0 + 0.1

    while not (y_switch_pressed and z_switch_pressed):
        switches_state = limits.get_all_switches_state(limit_ser, timeout=0.1)
        if switches_state:
            if switches_state.get(y_switch_id) == 1:
                y_switch_pressed = True
            if switches_state.get(z_switch_id) == 1:
                z_switch_pressed = True

        if y_switch_pressed and z_switch_pressed:
            break

        grbl_ser.reset_input_buffer()
        parts = ["G1"]
        if not y_switch_pressed:
            if direction == "+":
                parts.append(f"Y{step_size}")
            else:
                parts.append(f"Y-{step_size}")
        if not z_switch_pressed:
            if direction == "+":
                parts.append(f"Z{step_size}")
            else:
                parts.append(f"Z-{step_size}")

        if len(parts) == 1:
            break

        parts.append(f"F{feed}")
        command = " ".join(parts) + "\n"
        grbl_ser.write(command.encode())

        if not y_switch_pressed:
            y_distance += step_size
        if not z_switch_pressed:
            z_distance += step_size

        deadline = time.time() + 2.0
        while time.time() < deadline:
            if grbl_ser.in_waiting > 0:
                line_bytes = grbl_ser.readline()
                if line_bytes:
                    line = line_bytes.decode("utf-8", errors="ignore").strip().lower()
                    if line == "ok":
                        break
                    if line.startswith("error:") or line.startswith("alarm:"):
                        logger.error(f"GRBL error: {line}")
                        return False, max(y_distance, z_distance)
            time.sleep(0.05)

        time.sleep(move_time)

        switches_state = limits.get_all_switches_state(limit_ser, timeout=0.1)
        if switches_state:
            if switches_state.get(y_switch_id) == 1:
                y_switch_pressed = True
            if switches_state.get(z_switch_id) == 1:
                z_switch_pressed = True

    return True, max(y_distance, z_distance)

def move_until_limit_y(grbl_ser: serial.Serial, limit_ser: serial.Serial, direction: str, switch_ids: list[int], step_size: float = 0.5, feed: int = 100) -> tuple[bool, float]:
    """
    Step-by-step Y+Z movement until any of the limit switches is pressed.
    Moves both Y and Z together (dual motor Y axis).
    """
    distance_traveled = 0.0
    step_count = 0
    move_time = (step_size / feed) * 60.0 + 0.1

    while True:
        step_count += 1
        pressed_switch_id = limits.get_pressed_switch_id(limit_ser, switch_ids, timeout=0.5)
        if pressed_switch_id is not None:
            return True, distance_traveled

        grbl_ser.reset_input_buffer()
        if direction == "+":
            grbl.move_relative(grbl_ser, y=step_size, feed=feed)
        else:
            grbl.move_relative(grbl_ser, y=-step_size, feed=feed)
        distance_traveled += step_size

        deadline = time.time() + 2.0
        while time.time() < deadline:
            if grbl_ser.in_waiting > 0:
                line_bytes = grbl_ser.readline()
                if line_bytes:
                    line = line_bytes.decode("utf-8", errors="ignore").strip().lower()
                    if line == "ok":
                        break
                    if line.startswith("error:") or line.startswith("alarm:"):
                        logger.error(f"GRBL error: {line}")
                        return False, distance_traveled
            time.sleep(0.05)

        time.sleep(move_time)

def home_x_axis_fast(grbl_connection: grbl_schemas.GrblConnection, limit_ser: serial.Serial) -> dict[str, float | str]:
    """
    Two-pass X axis homing with calibration.

    Args:
        grbl_connection: GRBL connection with cached settings
        limit_ser: Limit controller serial connection

    Returns:
        Dict with calibration results
    """
    grbl_ser = grbl_connection.serial
    switch_1_id = 3
    switch_2_id = 2
    safety_margin = 5.0
    fine_step = 0.1
    fine_feed = 200
    known_axis_length = 291.0

    try:
        grbl.set_setting(grbl_ser, "step_idle_delay", 255)
        time.sleep(0.2)
        grbl_ser.read_all()

        grbl.set_mode_relative(grbl_ser)
        success, grbl_ser, _ = move_until_limit_fast(grbl_ser, limit_ser, "+", switch_1_id)
        if not success:
            raise RuntimeError("Failed to reach first limit")

        grbl.set_mode_relative(grbl_ser)
        success, grbl_ser, rough_distance = move_until_limit_fast(grbl_ser, limit_ser, "-", switch_2_id)
        if not success:
            raise RuntimeError("Failed to reach second limit")

        grbl.set_mode_relative(grbl_ser)
        rough_center = rough_distance / 2.0
        grbl.move_relative(grbl_ser, x=rough_center, feed=20000)
        move_time = (rough_center / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        fast_approach = rough_center - safety_margin
        grbl.move_relative(grbl_ser, x=fast_approach, feed=20000)
        move_time = (fast_approach / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        success, fine_dist_1 = move_until_limit(grbl_ser, limit_ser, "+", switch_1_id, step_size=fine_step, feed=fine_feed)
        if not success:
            raise RuntimeError("Failed to reach first limit (fine)")

        dist_to_limit_1 = fast_approach + fine_dist_1
        return_distance = dist_to_limit_1 + fast_approach
        grbl.move_relative(grbl_ser, x=-return_distance, feed=20000)
        move_time = (return_distance / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        success, fine_dist_2 = move_until_limit(grbl_ser, limit_ser, "-", switch_2_id, step_size=fine_step, feed=fine_feed)
        if not success:
            raise RuntimeError("Failed to reach second limit (fine)")

        total_distance = dist_to_limit_1 + fast_approach + fine_dist_2
        current_steps = grbl.get_setting(grbl_connection, "x_steps_per_mm") or 250.0
        correction_factor = total_distance / known_axis_length
        new_steps = current_steps * correction_factor

        grbl_connection.update_setting("x_steps_per_mm", new_steps)
        grbl_ser.read_all()

        center_distance = known_axis_length / 2.0
        grbl.move_relative(grbl_ser, x=center_distance, feed=20000)
        move_time = (center_distance / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        grbl_connection.update_setting("step_idle_delay", 25)
        grbl_ser.read_all()
        grbl.set_mode_absolute(grbl_ser)

        logger.info(f"X axis calibration complete: {new_steps:.3f} steps/mm")

        pos_after_x_center = grbl.query_position(grbl_ser)
        min_x_limit = None
        max_x_limit = None
        if pos_after_x_center.x is not None:
            min_x_limit = pos_after_x_center.x - (known_axis_length / 2.0)
            max_x_limit = pos_after_x_center.x + (known_axis_length / 2.0)

        return {
            "axis": "x",
            "measured_length": total_distance,
            "known_length": known_axis_length,
            "steps_per_mm": new_steps,
            "status": "complete",
            "min_x_limit": min_x_limit,
            "max_x_limit": max_x_limit
        }

    except Exception as e:
        logger.error(f"X axis homing failed: {e}")
        raise

def move_until_limit(grbl_ser: serial.Serial, limit_ser: serial.Serial, direction: str, switch_id: int, step_size: float = 2.0, feed: int = 500) -> tuple[bool, float]:
    """
    Step-by-step movement until limit switch is pressed.
    Returns (success, distance_traveled).
    """
    distance_traveled = 0.0
    step_count = 0
    move_time = (step_size / feed) * 60.0 + 0.1

    while True:
        step_count += 1
        request = limits_schemas.LimitSwitchStateRequest(switch_id=switch_id)
        response = limits.get_switch_state(limit_ser, request)
        if response.state == 1:
            return True, distance_traveled

        grbl_ser.reset_input_buffer()
        if direction == "+":
            grbl.move_relative(grbl_ser, x=step_size, feed=feed)
        else:
            grbl.move_relative(grbl_ser, x=-step_size, feed=feed)
        distance_traveled += step_size

        deadline = time.time() + 2.0
        while time.time() < deadline:
            if grbl_ser.in_waiting > 0:
                line_bytes = grbl_ser.readline()
                if line_bytes:
                    line = line_bytes.decode("utf-8", errors="ignore").strip().lower()
                    if line == "ok":
                        break
                    if line.startswith("error:") or line.startswith("alarm:"):
                        logger.error(f"GRBL error: {line}")
                        return False, distance_traveled
            time.sleep(0.05)

        time.sleep(move_time)

        request = limits_schemas.LimitSwitchStateRequest(switch_id=switch_id)
        response = limits.get_switch_state(limit_ser, request)
        if response.state == 1:
            return True, distance_traveled

def home_y_axis_fast(grbl_connection: grbl_schemas.GrblConnection, limit_ser: serial.Serial) -> dict[str, float | str]:
    """
    Two-pass Y axis homing with calibration.
    Moves both Y and Z together (dual motor Y axis).

    Args:
        grbl_connection: GRBL connection with cached settings
        limit_ser: Limit controller serial connection

    Returns:
        Dict with calibration results
    """
    grbl_ser = grbl_connection.serial
    switch_1_ids = [0, 1]
    switch_2_ids = [4, 5]
    safety_margin = 5
    fine_step = 0.1
    fine_feed = 200
    known_axis_length = 899.0

    try:
        grbl.set_setting(grbl_ser, "step_idle_delay", 255)
        time.sleep(0.2)
        grbl_ser.read_all()

        pos_before = grbl.query_position(grbl_ser)
        grbl.set_mode_relative(grbl_ser)
        success, grbl_ser, dist_to_limit_1 = move_until_limit_fast_y(grbl_ser, limit_ser, "+", switch_1_ids, feed=1200)
        if not success:
            raise RuntimeError("Failed to reach first limit")

        pos_after_limit_1 = grbl.query_position(grbl_ser)
        grbl.set_mode_relative(grbl_ser)
        pos_before_limit_2 = grbl.query_position(grbl_ser)
        success, grbl_ser, dist_to_limit_2 = move_until_limit_fast_y(grbl_ser, limit_ser, "-", switch_2_ids, feed=1200)
        if not success:
            raise RuntimeError("Failed to reach second limit")

        pos_after_limit_2 = grbl.query_position(grbl_ser)
        if pos_after_limit_1.y is not None and pos_after_limit_2.y is not None:
            actual_axis_length = abs(pos_after_limit_1.y - pos_after_limit_2.y)
            rough_distance = actual_axis_length
        else:
            rough_distance = dist_to_limit_2

        grbl.set_mode_relative(grbl_ser)
        pos_before_center = grbl.query_position(grbl_ser)

        if pos_after_limit_1.y is not None and pos_after_limit_2.y is not None and pos_before_center.y is not None:
            limit_1_pos = pos_after_limit_1.y
            limit_2_pos = pos_after_limit_2.y
            current_pos = pos_before_center.y
            center_pos = (limit_1_pos + limit_2_pos) / 2.0
            center_move_distance = center_pos - current_pos
            rough_center = center_move_distance
        else:
            rough_center = rough_distance / 2.0

        grbl.move_relative(grbl_ser, y=rough_center, feed=20000)
        move_time = (rough_center / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        pos_after_center = grbl.query_position(grbl_ser)
        time.sleep(3.0)

        pos_after_rough_center = grbl.query_position(grbl_ser)

        if pos_after_rough_center.y is None:
            fast_approach = rough_center - safety_margin
        else:
            if pos_after_limit_1.y is not None:
                distance_to_limit_1_from_center = abs(pos_after_limit_1.y - pos_after_rough_center.y)
                fast_approach = distance_to_limit_1_from_center - safety_margin
            else:
                fast_approach = rough_center - safety_margin

        grbl.move_relative(grbl_ser, y=fast_approach, feed=20000)
        move_time = (abs(fast_approach) / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        pos_after_fast_approach = grbl.query_position(grbl_ser)
        switch_mapping = grbl_schemas.LimitSwitchMapping()
        success, fine_dist_1 = move_until_limit_y_independent(
            grbl_ser,
            limit_ser,
            "+",
            switch_mapping.y_axis_switches[0],
            switch_mapping.z_axis_switches[0],
            step_size=fine_step,
            feed=fine_feed
        )
        if not success:
            raise RuntimeError("Failed to reach first limit (fine)")

        pos_after_limit_1_fine = grbl.query_position(grbl_ser)

        if pos_after_rough_center.y is not None and pos_after_limit_1_fine.y is not None:
            dist_to_limit_1_from_center = abs(pos_after_limit_1_fine.y - pos_after_rough_center.y)
        else:
            dist_to_limit_1_from_center = fast_approach + fine_dist_1

        if pos_after_limit_1_fine.y is not None and pos_after_limit_2.y is not None:
            estimated_total_length = abs(pos_after_limit_1_fine.y - pos_after_limit_2.y)
            return_distance = estimated_total_length - safety_margin
        else:
            return_distance = dist_to_limit_1_from_center + dist_to_limit_1_from_center

        grbl.move_relative(grbl_ser, y=-return_distance, feed=20000)
        move_time = (return_distance / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        success, fine_dist_2 = move_until_limit_y(grbl_ser, limit_ser, "-", switch_2_ids, step_size=fine_step, feed=fine_feed)
        if not success:
            raise RuntimeError("Failed to reach second limit (fine)")

        pos_after_limit_2_fine = grbl.query_position(grbl_ser)

        if pos_after_limit_1_fine.y is not None and pos_after_limit_2_fine.y is not None:
            total_distance = abs(pos_after_limit_1_fine.y - pos_after_limit_2_fine.y)
        else:
            total_distance = dist_to_limit_1_from_center + dist_to_limit_1_from_center + fine_dist_2

        current_steps_y = grbl.get_setting(grbl_connection, "y_steps_per_mm") or 40.0
        current_steps_z = grbl.get_setting(grbl_connection, "z_steps_per_mm") or 40.0
        correction_factor = total_distance / known_axis_length
        new_steps_y = current_steps_y * correction_factor
        new_steps_z = current_steps_z * correction_factor

        grbl_connection.update_setting("y_steps_per_mm", new_steps_y)
        grbl_connection.update_setting("z_steps_per_mm", new_steps_z)
        grbl_ser.read_all()

        pos_before_final_center = grbl.query_position(grbl_ser)

        if pos_after_limit_1_fine.y is not None and pos_after_limit_2_fine.y is not None and pos_before_final_center.y is not None:
            limit_1_pos = pos_after_limit_1_fine.y
            limit_2_pos = pos_after_limit_2_fine.y
            current_pos = pos_before_final_center.y
            center_pos = (limit_1_pos + limit_2_pos) / 2.0
            center_move_distance = center_pos - current_pos
            center_distance = center_move_distance
        else:
            center_distance = known_axis_length / 2.0

        grbl.set_mode_relative(grbl_ser)
        grbl.move_relative(grbl_ser, y=center_distance, feed=20000)
        move_time = (abs(center_distance) / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        pos_after_final_center = grbl.query_position(grbl_ser)
        grbl_connection.update_setting("step_idle_delay", 25)
        grbl_ser.read_all()
        grbl.set_mode_absolute(grbl_ser)

        logger.info(f"Y axis calibration complete: {new_steps_y:.3f} steps/mm")

        min_y_limit = None
        max_y_limit = None
        if pos_after_limit_1_fine.y is not None and pos_after_limit_2_fine.y is not None:
            if pos_after_limit_1_fine.y < pos_after_limit_2_fine.y:
                min_y_limit = pos_after_limit_1_fine.y
                max_y_limit = pos_after_limit_2_fine.y
            else:
                min_y_limit = pos_after_limit_2_fine.y
                max_y_limit = pos_after_limit_1_fine.y

        logger.info(f"Y axis limits: min_y={min_y_limit}, max_y={max_y_limit}, limit_1_y={pos_after_limit_1_fine.y}, limit_2_y={pos_after_limit_2_fine.y}")

        return {
            "axis": "y",
            "measured_length": total_distance,
            "known_length": known_axis_length,
            "steps_per_mm": new_steps_y,
            "status": "complete",
            "min_y_limit": min_y_limit,
            "max_y_limit": max_y_limit
        }

    except Exception as e:
        logger.error(f"Y axis homing failed: {e}")
        raise

def home_all(grbl_connection: grbl_schemas.GrblConnection, limit_ser: serial.Serial) -> dict[str, str | float | None]:
    """
    Run full calibration sequence: Y axis first, then X axis.
    Sets origin (0,0,0) to be 10mm from the front-left corner and returns toolhead to origin.

    Args:
        grbl_connection: GRBL connection with cached settings
        limit_ser: Limit controller serial connection

    Returns:
        Dict with calibration results
    """
    grbl_ser = grbl_connection.serial
    x_axis_length = 291.0
    y_axis_length = 899.0

    try:
        y_result = home_y_axis_fast(grbl_connection, limit_ser)
        x_result = home_x_axis_fast(grbl_connection, limit_ser)

        grbl.initialize_connection(grbl_ser)
        grbl.set_mode_absolute(grbl_ser)

        pos_after_calibration = grbl.query_position(grbl_ser)

        min_x = x_result.get("min_x_limit")
        max_y = y_result.get("max_y_limit")

        return_to_origin_and_set_home(grbl_ser, min_x, max_y, corner_offset=10.0, feed=20000)

        logger.info("Calibration complete")

        return {
            "status": "complete",
            "message": "Full calibration completed successfully",
            "x_axis_length": x_result.get("measured_length"),
            "y_axis_length": y_result.get("measured_length")
        }

    except Exception as e:
        logger.error(f"Full calibration failed: {e}")
        raise

def return_to_origin_and_set_home(grbl_ser: serial.Serial, min_x: float | None, front_y: float | None, corner_offset: float = 10.0, feed: int = 20000) -> None:
    """
    Return toolhead to origin and set 0,0,0 to be corner_offset mm from the front-left corner.
    Front-left corner is defined as minimum X and front Y position (maximum Y limit).
    Uses combined Y+Z movement (not independent).

    Args:
        grbl_ser: Serial connection to GRBL controller
        min_x: Minimum X limit position from calibration (None if unavailable)
        front_y: Front Y limit position from calibration (maximum Y, None if unavailable)
        corner_offset: Distance in mm from corner to set as origin (default: 10.0)
        feed: Feed rate in mm/min for movement
    """
    pos_current = grbl.query_position(grbl_ser)

    if min_x is not None:
        front_left_corner_x = min_x
    elif pos_current.x is not None:
        front_left_corner_x = pos_current.x - 145.5
    else:
        front_left_corner_x = -145.5

    if front_y is not None:
        front_left_corner_y = front_y
    elif pos_current.y is not None:
        front_left_corner_y = pos_current.y + 449.5
    else:
        front_left_corner_y = 449.5

    home_x = front_left_corner_x + corner_offset
    home_y = front_left_corner_y - corner_offset

    grbl.set_mode_absolute(grbl_ser)
    grbl.move_absolute(grbl_ser, x=home_x, y=home_y, feed=feed)
    current_x = pos_current.x or 0.0
    current_y = pos_current.y or 0.0
    move_time = (max(abs(home_x - current_x), abs(home_y - current_y)) / feed) * 60.0 + 0.5
    time.sleep(move_time)
    grbl_ser.read_all()

    grbl.set_work_coordinate_offset(grbl_ser, x=0, y=0)
    logger.info(f"Origin set to 10mm from front-left corner at machine position ({home_x:.2f}, {home_y:.2f})")
