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


def query_grbl_position(grbl_ser: serial.Serial) -> dict[str, float | str | None]:
    """
    Query GRBL for current machine position and status.
    Returns dict with 'x', 'y', 'z', 'status', 'raw', 'mode' keys.
    """
    grbl_ser.reset_input_buffer()
    grbl.send_raw_command(grbl_ser, b'?\n', wait_time=0.2)
    response = grbl.read_response(grbl_ser, timeout=0.2)

    result: dict[str, float | str | None] = {'x': None, 'y': None, 'z': None, 'status': 'Unknown', 'raw': response, 'mode': 'Unknown'}

    if '<' in response and '>' in response:
        status_part = response[response.find('<'):response.find('>')+1]
        result['status'] = status_part

        if 'G' in status_part:
            if 'G91' in status_part:
                result['mode'] = 'Relative (G91)'
            elif 'G90' in status_part:
                result['mode'] = 'Absolute (G90)'

        if 'MPos:' in response:
            parts = response[response.find('MPos:')+5:].split(',')
            if len(parts) >= 3:
                try:
                    result['x'] = float(parts[0].strip())
                    result['y'] = float(parts[1].strip())
                    result['z'] = float(parts[2].strip())
                except ValueError:
                    pass

    return result



def move_until_limit_fast(grbl_ser: serial.Serial, limit_ser: serial.Serial, direction: str, switch_id: int, max_distance: float = 1000.0, feed: int = 800) -> tuple[bool, serial.Serial, float]:
    """
    Start a long move and stop when limit switch is pressed.
    Returns (success, new_serial, distance_traveled).
    Distance is calculated from elapsed time and feed rate.
    Note: Returns new serial connection after hard reset.
    """
    logger.info(f"Moving {direction} until switch {switch_id} is pressed (max {max_distance}mm at F{feed})...")

    limit_ser.timeout = 0.01
    limit_ser.reset_input_buffer()

    grbl_ser.reset_input_buffer()
    if direction == "+":
        grbl.move_relative(grbl_ser, x=max_distance, feed=feed)
    else:
        grbl.move_relative(grbl_ser, x=-max_distance, feed=feed)
    start_time = time.time()

    while True:
        request = limits.LimitSwitchStateRequest(switch_id=switch_id, timeout=0.01)
        response = limits.get_switch_state(limit_ser, request)
        if response.state == 1:
            elapsed = time.time() - start_time
            distance = (elapsed * feed) / 60.0
            logger.info(f"Switch {switch_id} pressed after {elapsed:.2f}s (~{distance:.1f}mm), stopping...")
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
    logger.info(f"Moving Y+Z {direction} until switches {switch_ids} pressed (max {max_distance}mm at F{feed})...")

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
            logger.info(f"Switch {pressed_switch_id} pressed after {elapsed:.2f}s (~{distance:.1f}mm), stopping...")

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

def move_until_limit_y(grbl_ser: serial.Serial, limit_ser: serial.Serial, direction: str, switch_ids: list[int], step_size: float = 0.5, feed: int = 100) -> tuple[bool, float]:
    """
    Step-by-step Y+Z movement until any of the limit switches is pressed.
    Moves both Y and Z together (dual motor Y axis).
    """
    logger.info(f"Moving Y+Z {direction} until switches {switch_ids} pressed...")
    distance_traveled = 0.0
    step_count = 0
    move_time = (step_size / feed) * 60.0 + 0.1

    while True:
        step_count += 1
        pressed_switch_id = limits.get_pressed_switch_id(limit_ser, switch_ids, timeout=0.5)
        if pressed_switch_id is not None:
            logger.info(f"Switch {pressed_switch_id} pressed, stopping")
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
    switch_1_id = 3
    switch_2_id = 2
    safety_margin = 5.0
    fine_step = 0.1
    fine_feed = 200
    known_axis_length = 291.0

    try:

        logger.info("Locking motors...")
        grbl.set_setting(grbl_ser, "step_idle_delay", 255)
        time.sleep(0.2)
        grbl_ser.read_all()

        logger.info("=== PASS 1: ROUGH SEEK (with resets) ===")

        grbl.set_mode_relative(grbl_ser)
        time.sleep(0.2)
        grbl_ser.read_all()

        logger.info("Fast seek to first limit (switch 3)...")
        success, grbl_ser, _ = move_until_limit_fast(grbl_ser, limit_ser, "+", switch_1_id)
        if not success:
            raise RuntimeError("Failed to reach first limit")

        grbl.set_mode_relative(grbl_ser)
        time.sleep(0.2)
        grbl_ser.read_all()

        logger.info("Fast seek to second limit (switch 2)...")
        success, grbl_ser, rough_distance = move_until_limit_fast(grbl_ser, limit_ser, "-", switch_2_id)
        if not success:
            raise RuntimeError("Failed to reach second limit")

        logger.info(f"Rough axis length: ~{rough_distance:.1f}mm")

        grbl.set_mode_relative(grbl_ser)
        time.sleep(0.2)
        grbl_ser.read_all()

        rough_center = rough_distance / 2.0
        logger.info(f"Moving to rough center ({rough_center:.1f}mm)...")
        grbl.move_relative(grbl_ser, x=rough_center, feed=20000)
        move_time = (rough_center / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        logger.info("=== PASS 2: FINE SEEK (no resets) ===")

        fast_approach = rough_center - safety_margin
        logger.info(f"Fast approach to first limit ({fast_approach:.1f}mm)...")
        grbl.move_relative(grbl_ser, x=fast_approach, feed=20000)
        move_time = (fast_approach / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        logger.info("Fine seek to first limit...")
        success, fine_dist_1 = move_until_limit(grbl_ser, limit_ser, "+", switch_1_id, step_size=fine_step, feed=fine_feed)
        if not success:
            raise RuntimeError("Failed to reach first limit (fine)")
        logger.info(f"First limit: fine travel = {fine_dist_1:.2f}mm")

        dist_to_limit_1 = fast_approach + fine_dist_1

        return_distance = dist_to_limit_1 + fast_approach
        logger.info(f"Moving toward second limit ({return_distance:.1f}mm)...")
        grbl.move_relative(grbl_ser, x=-return_distance, feed=20000)
        move_time = (return_distance / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        logger.info("Fine seek to second limit...")
        success, fine_dist_2 = move_until_limit(grbl_ser, limit_ser, "-", switch_2_id, step_size=fine_step, feed=fine_feed)
        if not success:
            raise RuntimeError("Failed to reach second limit (fine)")
        logger.info(f"Second limit: fine travel = {fine_dist_2:.2f}mm")

        total_distance = dist_to_limit_1 + fast_approach + fine_dist_2
        logger.info(f"Measured axis length: {total_distance:.2f}mm")
        logger.info(f"Known axis length: {known_axis_length:.2f}mm")

        logger.info("=== CALIBRATION ===")
        current_steps = grbl.get_setting(grbl_connection, "x_steps_per_mm") or 250.0

        logger.info(f"Current X steps/mm: {current_steps}")

        correction_factor = total_distance / known_axis_length
        new_steps = current_steps * correction_factor
        logger.info(f"Correction factor: {correction_factor:.4f}")
        logger.info(f"New X steps/mm: {new_steps:.3f}")

        grbl_connection.update_setting("x_steps_per_mm", new_steps)
        time.sleep(0.2)
        grbl_ser.read_all()
        logger.info("Calibration applied")

        center_distance = known_axis_length / 2.0
        logger.info(f"Moving to center ({center_distance:.2f}mm)...")

        grbl.move_relative(grbl_ser, x=center_distance, feed=20000)
        move_time = (center_distance / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        grbl_connection.update_setting("step_idle_delay", 25)
        time.sleep(0.2)
        grbl_ser.read_all()

        grbl.set_mode_absolute(grbl_ser)
        time.sleep(0.2)

        logger.info(f"X axis homing complete. Calibrated axis length: {known_axis_length:.2f}mm")

        return {
            "axis": "x",
            "measured_length": total_distance,
            "known_length": known_axis_length,
            "steps_per_mm": new_steps,
            "status": "complete"
        }

    except Exception as e:
        logger.error(f"X axis homing failed: {e}")
        raise

def move_until_limit(grbl_ser: serial.Serial, limit_ser: serial.Serial, direction: str, switch_id: int, step_size: float = 2.0, feed: int = 500) -> tuple[bool, float]:
    """
    Step-by-step movement until limit switch is pressed.
    Returns (success, distance_traveled).
    """
    logger.info(f"Moving {direction} until switch {switch_id} is pressed...")
    distance_traveled = 0.0
    step_count = 0
    move_time = (step_size / feed) * 60.0 + 0.1

    while True:
        step_count += 1
        request = limits.LimitSwitchStateRequest(switch_id=switch_id)
        response = limits.get_switch_state(limit_ser, request)
        if response.state == 1:
            logger.info(f"Switch {switch_id} already pressed, stopping")
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

        request = limits.LimitSwitchStateRequest(switch_id=switch_id)
        response = limits.get_switch_state(limit_ser, request)
        if response.state == 1:
            logger.info(f"Switch {switch_id} pressed, stopping")
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
    switch_1_ids = [0, 1]
    switch_2_ids = [4, 5]
    safety_margin = 5
    fine_step = 0.1
    fine_feed = 200
    known_axis_length = 899.0

    try:

        logger.info("Locking motors...")
        grbl.set_setting(grbl_ser, "step_idle_delay", 255)
        time.sleep(0.2)
        grbl_ser.read_all()

        logger.info("=== PASS 1: ROUGH SEEK (with resets) ===")

        pos_before = query_grbl_position(grbl_ser)
        logger.debug(f"Initial position: X={pos_before['x']}, Y={pos_before['y']}, Z={pos_before['z']}")

        grbl.set_mode_relative(grbl_ser)
        time.sleep(0.2)
        grbl_ser.read_all()

        logger.info(f"Fast seek to first limit (switches {switch_1_ids})...")
        success, grbl_ser, dist_to_limit_1 = move_until_limit_fast_y(grbl_ser, limit_ser, "+", switch_1_ids, feed=1200)
        if not success:
            raise RuntimeError("Failed to reach first limit")

        pos_after_limit_1 = query_grbl_position(grbl_ser)
        logger.debug(f"After limit 1: Y={pos_after_limit_1['y']}, Z={pos_after_limit_1['z']}")
        logger.debug(f"Distance traveled to limit 1: {dist_to_limit_1:.2f}mm")

        grbl.set_mode_relative(grbl_ser)
        time.sleep(0.2)
        grbl_ser.read_all()

        pos_before_limit_2 = query_grbl_position(grbl_ser)

        logger.info(f"Fast seek to second limit (switches {switch_2_ids})...")
        success, grbl_ser, dist_to_limit_2 = move_until_limit_fast_y(grbl_ser, limit_ser, "-", switch_2_ids, feed=1200)
        if not success:
            raise RuntimeError("Failed to reach second limit")

        pos_after_limit_2 = query_grbl_position(grbl_ser)
        logger.debug(f"After limit 2: Y={pos_after_limit_2['y']}, Z={pos_after_limit_2['z']}")
        logger.debug(f"Distance traveled to limit 2: {dist_to_limit_2:.2f}mm")

        if pos_after_limit_1['y'] is not None and pos_after_limit_2['y'] is not None:
            actual_axis_length = abs(pos_after_limit_1['y'] - pos_after_limit_2['y'])
            logger.debug(f"Actual axis length: {actual_axis_length:.2f}mm")
            rough_distance = actual_axis_length
        else:
            rough_distance = dist_to_limit_2

        logger.info(f"Rough axis length: ~{rough_distance:.1f}mm")

        grbl.set_mode_relative(grbl_ser)
        time.sleep(0.2)
        grbl_ser.read_all()

        pos_before_center = query_grbl_position(grbl_ser)

        if pos_after_limit_1['y'] is not None and pos_after_limit_2['y'] is not None and pos_before_center['y'] is not None:
            limit_1_pos = pos_after_limit_1['y']
            limit_2_pos = pos_after_limit_2['y']
            current_pos = pos_before_center['y']
            center_pos = (limit_1_pos + limit_2_pos) / 2.0
            center_move_distance = center_pos - current_pos
            rough_center = center_move_distance
        else:
            rough_center = rough_distance / 2.0

        logger.info(f"Moving to rough center ({rough_center:.1f}mm in + direction)...")
        grbl.move_relative(grbl_ser, y=rough_center, feed=20000)
        move_time = (rough_center / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        pos_after_center = query_grbl_position(grbl_ser)

        logger.info("Pausing at rough center for 3 seconds...")
        time.sleep(3.0)

        logger.info("=== PASS 2: FINE SEEK (no resets) ===")

        pos_after_rough_center = query_grbl_position(grbl_ser)

        if pos_after_rough_center['y'] is None:
            fast_approach = rough_center - safety_margin
        else:
            if pos_after_limit_1['y'] is not None:
                distance_to_limit_1_from_center = abs(pos_after_limit_1['y'] - pos_after_rough_center['y'])
                fast_approach = distance_to_limit_1_from_center - safety_margin
            else:
                fast_approach = rough_center - safety_margin

        logger.info(f"Fast approach to first limit ({fast_approach:.1f}mm)...")
        grbl.move_relative(grbl_ser, y=fast_approach, feed=20000)
        move_time = (abs(fast_approach) / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        pos_after_fast_approach = query_grbl_position(grbl_ser)

        logger.info("Fine seek to first limit...")
        success, fine_dist_1 = move_until_limit_y(grbl_ser, limit_ser, "+", switch_1_ids, step_size=fine_step, feed=fine_feed)
        if not success:
            raise RuntimeError("Failed to reach first limit (fine)")
        logger.info(f"First limit: fine travel = {fine_dist_1:.2f}mm")

        pos_after_limit_1_fine = query_grbl_position(grbl_ser)

        if pos_after_rough_center['y'] is not None and pos_after_limit_1_fine['y'] is not None:
            dist_to_limit_1_from_center = abs(pos_after_limit_1_fine['y'] - pos_after_rough_center['y'])
        else:
            dist_to_limit_1_from_center = fast_approach + fine_dist_1

        if pos_after_limit_1_fine['y'] is not None and pos_after_limit_2['y'] is not None:
            estimated_total_length = abs(pos_after_limit_1_fine['y'] - pos_after_limit_2['y'])
            return_distance = estimated_total_length - safety_margin
        else:
            return_distance = dist_to_limit_1_from_center + dist_to_limit_1_from_center

        logger.info(f"Moving toward second limit ({return_distance:.1f}mm)...")
        grbl.move_relative(grbl_ser, y=-return_distance, feed=20000)
        move_time = (return_distance / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        logger.info("Fine seek to second limit...")
        success, fine_dist_2 = move_until_limit_y(grbl_ser, limit_ser, "-", switch_2_ids, step_size=fine_step, feed=fine_feed)
        if not success:
            raise RuntimeError("Failed to reach second limit (fine)")
        logger.info(f"Second limit: fine travel = {fine_dist_2:.2f}mm")

        pos_after_limit_2_fine = query_grbl_position(grbl_ser)

        if pos_after_limit_1_fine['y'] is not None and pos_after_limit_2_fine['y'] is not None:
            total_distance = abs(pos_after_limit_1_fine['y'] - pos_after_limit_2_fine['y'])
        else:
            total_distance = dist_to_limit_1_from_center + dist_to_limit_1_from_center + fine_dist_2

        logger.info(f"Measured axis length: {total_distance:.2f}mm")
        logger.info(f"Known axis length: {known_axis_length:.2f}mm")

        logger.info("=== CALIBRATION ===")
        current_steps_y = grbl.get_setting(grbl_connection, "y_steps_per_mm") or 40.0
        current_steps_z = grbl.get_setting(grbl_connection, "z_steps_per_mm") or 40.0

        logger.info(f"Current Y steps/mm: {current_steps_y}")
        logger.info(f"Current Z steps/mm: {current_steps_z}")

        correction_factor = total_distance / known_axis_length
        new_steps_y = current_steps_y * correction_factor
        new_steps_z = current_steps_z * correction_factor
        logger.info(f"Correction factor: {correction_factor:.4f}")
        logger.info(f"New Y steps/mm: {new_steps_y:.3f}")
        logger.info(f"New Z steps/mm: {new_steps_z:.3f}")

        grbl_connection.update_setting("y_steps_per_mm", new_steps_y)
        time.sleep(0.2)
        grbl_connection.update_setting("z_steps_per_mm", new_steps_z)
        time.sleep(0.2)
        grbl_ser.read_all()
        logger.info("Calibration applied")

        pos_before_final_center = query_grbl_position(grbl_ser)

        if pos_after_limit_1_fine['y'] is not None and pos_after_limit_2_fine['y'] is not None and pos_before_final_center['y'] is not None:
            limit_1_pos = pos_after_limit_1_fine['y']
            limit_2_pos = pos_after_limit_2_fine['y']
            current_pos = pos_before_final_center['y']
            center_pos = (limit_1_pos + limit_2_pos) / 2.0
            center_move_distance = center_pos - current_pos
            center_distance = center_move_distance
        else:
            center_distance = known_axis_length / 2.0

        logger.info(f"Moving to center ({center_distance:.2f}mm)...")

        grbl.set_mode_relative(grbl_ser)
        time.sleep(0.2)
        grbl_ser.read_all()

        grbl.move_relative(grbl_ser, y=center_distance, feed=20000)
        move_time = (abs(center_distance) / 20000.0) * 60.0 + 0.5
        time.sleep(move_time)
        grbl_ser.read_all()

        pos_after_final_center = query_grbl_position(grbl_ser)

        grbl_connection.update_setting("step_idle_delay", 25)
        time.sleep(0.2)
        grbl_ser.read_all()

        grbl.set_mode_absolute(grbl_ser)
        time.sleep(0.2)

        logger.info(f"Y axis homing complete. Calibrated axis length: {known_axis_length:.2f}mm")

        return {
            "axis": "y",
            "measured_length": total_distance,
            "known_length": known_axis_length,
            "steps_per_mm": new_steps_y,
            "status": "complete"
        }

    except Exception as e:
        logger.error(f"Y axis homing failed: {e}")
        raise

def home_all(grbl_connection: grbl_schemas.GrblConnection, limit_ser: serial.Serial, outline: bool = True) -> dict[str, str | float | None]:
    """
    Run full calibration sequence: Y axis first, then X axis.
    Sets center as origin (0,0,0) after calibration.
    Optionally outlines the workspace border.

    Args:
        grbl_connection: GRBL connection with cached settings
        limit_ser: Limit controller serial connection
        outline: Whether to outline workspace after calibration

    Returns:
        Dict with calibration results
    """
    grbl_ser = grbl_connection.serial
    x_axis_length = 291.0
    y_axis_length = 899.0

    try:
        logger.info("=== Starting full calibration sequence ===")
        logger.info("Step 1/2: Calibrating Y axis...")
        y_result = home_y_axis_fast(grbl_connection, limit_ser)
        logger.info("\nStep 2/2: Calibrating X axis...")
        x_result = home_x_axis_fast(grbl_connection, limit_ser)

        logger.info("\n=== Setting center as origin (0,0,0) ===")

        grbl.initialize_connection(grbl_ser)

        grbl.set_mode_absolute(grbl_ser)
        time.sleep(0.2)
        grbl_ser.read_all()

        pos = query_grbl_position(grbl_ser)
        logger.info(f"Current position: X={pos['x']}, Y={pos['y']}, Z={pos['z']}")

        grbl.set_work_coordinate_offset(grbl_ser, x=0, y=0)
        time.sleep(0.2)
        grbl_ser.read_all()
        logger.info("Center set as origin (0,0,0)")

        if outline:
            logger.info("\n=== Outlining workspace ===")
            outline_workspace(grbl_ser, x_axis_length, y_axis_length, margin=10.0, feed=6000)

        logger.info("\n=== Full calibration complete ===")

        return {
            "status": "complete",
            "message": "Full calibration completed successfully",
            "x_axis_length": x_result.get("measured_length"),
            "y_axis_length": y_result.get("measured_length")
        }

    except Exception as e:
        logger.error(f"Full calibration failed: {e}")
        raise

def outline_workspace(grbl_ser: serial.Serial, x_length: float, y_length: float, margin: float = 10.0, feed: int = 20000) -> None:
    """
    Outline the workspace border with specified margin.
    Starts at bottom-left corner and moves clockwise around the border.
    """
    half_x = (x_length / 2.0) - margin
    half_y = (y_length / 2.0) - margin

    logger.info(f"Workspace outline: X={x_length:.1f}mm, Y={y_length:.1f}mm, Margin={margin:.1f}mm")
    logger.info(f"Outline bounds: X=±{half_x:.1f}mm, Y=±{half_y:.1f}mm")

    grbl.set_mode_absolute(grbl_ser)
    time.sleep(0.2)
    grbl_ser.read_all()

    logger.info("Moving to bottom-left corner...")
    grbl.move_absolute(grbl_ser, x=-half_x, y=-half_y, feed=feed)
    move_time = (max(half_x, half_y) / feed) * 60.0 + 1.0
    time.sleep(move_time)
    grbl_ser.read_all()

    logger.info("Outlining workspace border (clockwise)...")

    logger.info("  Bottom edge: left to right...")
    grbl.move_absolute(grbl_ser, x=half_x, y=-half_y, feed=feed)
    move_time = ((half_x * 2) / feed) * 60.0 + 0.5
    time.sleep(move_time)
    grbl_ser.read_all()

    logger.info("  Right edge: bottom to top...")
    grbl.move_absolute(grbl_ser, x=half_x, y=half_y, feed=feed)
    move_time = ((half_y * 2) / feed) * 60.0 + 0.5
    time.sleep(move_time)
    grbl_ser.read_all()

    logger.info("  Top edge: right to left...")
    grbl.move_absolute(grbl_ser, x=-half_x, y=half_y, feed=feed)
    move_time = ((half_x * 2) / feed) * 60.0 + 0.5
    time.sleep(move_time)
    grbl_ser.read_all()

    logger.info("  Left edge: top to bottom...")
    grbl.move_absolute(grbl_ser, x=-half_x, y=-half_y, feed=feed)
    move_time = ((half_y * 2) / feed) * 60.0 + 0.5
    time.sleep(move_time)
    grbl_ser.read_all()

    logger.info("Returning to center...")
    grbl.move_absolute(grbl_ser, x=0, y=0, feed=feed)
    move_time = (max(half_x, half_y) / feed) * 60.0 + 0.5
    time.sleep(move_time)
    grbl_ser.read_all()

    logger.info("Workspace outline complete")
