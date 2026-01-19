import os
import re
import tempfile
import time

import fastapi
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Form
from fastapi import HTTPException
from fastapi import UploadFile
from loguru import logger

from api import utils
from api.modules import grbl
from api.schemas import grbl as grbl_schemas
from api.schemas.operations import SvgToGcodeResponse

async def svg_to_gcode_endpoint(
    svg_file: UploadFile,
    feed: int = Form(5000),
    movement_feed: int = Form(10000),
    origin_x: float = Form(0.0),
    origin_y: float = Form(0.0),
    laser_power: int = Form(1000, description="Laser power level (0-1000, default: 1000)"),
    grbl_connection: grbl_schemas.GrblConnection = Depends(utils.get_grbl_connection)
) -> SvgToGcodeResponse:
    """
    Convert SVG file to G-code and execute on the machine.
    The SVG is converted to G-code commands which are then sent to GRBL.
    Coordinates are transformed to account for machine coordinate system (Y inversion, dual motor Y/Z).

    Args:
        svg_file: Uploaded SVG file to convert and execute
        feed: Feed rate in mm/min for cutting movements (default: 5000)
        movement_feed: Feed rate in mm/min for rapid movements (default: 10000)
        origin_x: X coordinate offset in mm from home position to apply to toolpath center (default: 0.0)
        origin_y: Y coordinate offset in mm from home position to apply to toolpath center (default: 0.0)
        laser_power: Laser power level from 0-1000 (default: 1000, maximum power)
        grbl_connection: GRBL connection with cached settings

    Returns:
        SvgToGcodeResponse with status, number of commands sent, and final position

    Raises:
        HTTPException: 400 if SVG is invalid or conversion fails, 500 if execution fails
    """
    if not svg_file.filename or not svg_file.filename.endswith('.svg'):
        raise HTTPException(status_code=400, detail="File must be an SVG file")

    grbl_ser = grbl_connection.serial

    try:
        svg_content = await svg_file.read()

        with tempfile.NamedTemporaryFile(mode='wb', suffix='.svg', delete=False) as svg_temp:
            svg_temp.write(svg_content)
            svg_temp_path = svg_temp.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.gcode', delete=False) as gcode_temp:
            gcode_temp_path = gcode_temp.name

        from svg_to_gcode.svg_parser import parse_file
        from svg_to_gcode.compiler import Compiler
        from svg_to_gcode.compiler import interfaces

        curves = parse_file(svg_temp_path)
        compiler = Compiler(
            interfaces.Gcode,
            movement_speed=movement_feed,
            cutting_speed=feed,
            pass_depth=0
        )
        compiler.append_curves(curves)
        compiler.compile_to_file(gcode_temp_path, passes=1)

        with open(gcode_temp_path, 'r') as f:
            gcode_lines = f.readlines()

        logger.info(f"[SVG_TO_GCODE] Generated {len(gcode_lines)} lines of G-code")
        logger.debug(f"[SVG_TO_GCODE] First 10 G-code lines: {gcode_lines[:10]}")

        if laser_power < 0 or laser_power > 1000:
            raise HTTPException(status_code=400, detail="laser_power must be between 0 and 1000")

        processed_lines = []
        for line in gcode_lines:
            if 'M3' in line.upper():
                line_upper = line.upper()
                if 'S' in line_upper:
                    line = re.sub(r'M3\s+S\d+', f'M3 S{laser_power}', line, flags=re.IGNORECASE)
                else:
                    line = re.sub(r'M3', f'M3 S{laser_power}', line, flags=re.IGNORECASE)
            processed_lines.append(line)
        gcode_lines = processed_lines
        logger.info(f"[SVG_TO_GCODE] Laser power configured to {laser_power} (0-1000 scale)")

        os.unlink(svg_temp_path)
        os.unlink(gcode_temp_path)

        current_pos = grbl.query_position(grbl_ser)
        if current_pos.x is None or current_pos.y is None:
            raise HTTPException(status_code=500, detail="Unable to query current work position")

        grbl.set_mode_absolute(grbl_ser)

        min_x = float('inf')
        max_x = float('-inf')
        min_y = float('inf')
        max_y = float('-inf')

        for line in gcode_lines:
            line = line.strip()
            if not line or line.startswith(';') or line.startswith('('):
                continue

            parts = line.split()
            if not parts:
                continue

            command_type = parts[0].upper()
            if command_type == 'G0' or command_type == 'G1':
                for part in parts[1:]:
                    if part.startswith('X'):
                        x_coord = float(part[1:].rstrip(';'))
                        min_x = min(min_x, x_coord)
                        max_x = max(max_x, x_coord)
                    elif part.startswith('Y'):
                        y_coord = float(part[1:].rstrip(';'))
                        min_y = min(min_y, y_coord)
                        max_y = max(max_y, y_coord)

        if min_x == float('inf') or min_y == float('inf'):
            raise HTTPException(status_code=400, detail="SVG contains no valid toolpath coordinates")

        raw_center_x = (min_x + max_x) / 2.0
        raw_center_y = (min_y + max_y) / 2.0
        target_center_x = raw_center_x + origin_x
        target_center_y = raw_center_y + origin_y

        grbl.move_absolute(grbl_ser, x=target_center_x, y=target_center_y, feed=movement_feed, invert_y=True)
        distance_to_center = ((target_center_x - current_pos.x) ** 2 + (target_center_y - current_pos.y) ** 2) ** 0.5
        if distance_to_center > 0:
            move_time = (distance_to_center / movement_feed) * 60.0 + 0.5
            time.sleep(move_time)
            grbl_ser.read_all()

        commands_sent = 0
        current_x = target_center_x
        current_y = target_center_y
        current_z = current_pos.z if current_pos.z is not None else 0.0

        laser_commands_found = []
        g_commands_found = set()
        m_commands_found = set()

        for line in gcode_lines:
            line = line.strip()
            if not line or line.startswith(';') or line.startswith('('):
                continue

            parts = line.split()
            if not parts:
                continue

            command_type = parts[0].upper()

            if command_type.startswith('M'):
                m_commands_found.add(command_type)
                if command_type in ['M3', 'M4', 'M5']:
                    laser_commands_found.append(line)
                    logger.info(f"[SVG_TO_GCODE] Laser command found: {line}")
                else:
                    logger.debug(f"[SVG_TO_GCODE] M-command found: {line}")
            elif command_type.startswith('G'):
                g_commands_found.add(command_type)

            if command_type in ['G90']:
                grbl.set_mode_absolute(grbl_ser)
                commands_sent += 1
                continue
            elif command_type in ['G91']:
                logger.warning("Relative mode (G91) detected in G-code, but absolute mode is required. Skipping.")
                continue
            elif command_type.startswith('M'):
                logger.info(f"[SVG_TO_GCODE] Executing M-command: {line}")
                grbl_command = grbl_schemas.GrblCommandRequest(
                    command=line,
                    label="G-code M-command",
                    retries=3,
                    timeout=1.0
                )
                response = grbl.send_command(grbl_ser, grbl_command)
                if not response.success:
                    logger.warning(f"[SVG_TO_GCODE] M-command {line} failed: {response.response}")
                else:
                    logger.info(f"[SVG_TO_GCODE] M-command {line} executed successfully")
                commands_sent += 1
                continue
            elif command_type in ['G92', 'G28', 'G30']:
                logger.debug(f"[SVG_TO_GCODE] Executing G-command: {line}")
                grbl_command = grbl_schemas.GrblCommandRequest(
                    command=line,
                    label="G-code command",
                    retries=3,
                    timeout=1.0
                )
                response = grbl.send_command(grbl_ser, grbl_command)
                if not response.success:
                    logger.warning(f"[SVG_TO_GCODE] Command {line} failed: {response.response}")
                commands_sent += 1
                continue
            elif command_type == 'G0' or command_type == 'G1':
                x_val = None
                y_val = None
                z_val = None
                feed_val = None

                for part in parts[1:]:
                    if part.startswith('X'):
                        raw_x = float(part[1:].rstrip(';'))
                        x_val = (raw_x - raw_center_x) + target_center_x
                    elif part.startswith('Y'):
                        raw_y = float(part[1:].rstrip(';'))
                        y_val = (raw_y - raw_center_y) + target_center_y
                    elif part.startswith('Z'):
                        z_val = float(part[1:].rstrip(';'))
                    elif part.startswith('F'):
                        feed_val = int(float(part[1:].rstrip(';')))

                if x_val is None and y_val is None and z_val is None:
                    continue

                if x_val is None:
                    x_val = current_x
                if y_val is None:
                    y_val = current_y
                if z_val is None:
                    z_val = current_z

                if command_type == 'G0':
                    feed_to_use = movement_feed
                else:
                    feed_to_use = feed_val if feed_val is not None else feed

                distance = ((x_val - current_x) ** 2 + (y_val - current_y) ** 2 + (z_val - current_z) ** 2) ** 0.5

                grbl.move_absolute(
                    grbl_ser,
                    x=x_val,
                    y=y_val,
                    z=z_val,
                    feed=feed_to_use,
                    invert_y=True
                )

                if distance > 0:
                    move_time = (distance / feed_to_use) * 60.0 + 0.1
                    time.sleep(move_time)
                    grbl_ser.read_all()

                current_x = x_val
                current_y = y_val
                current_z = z_val
                commands_sent += 1

        logger.info(f"[SVG_TO_GCODE] Summary - G-commands found: {sorted(g_commands_found)}")
        logger.info(f"[SVG_TO_GCODE] Summary - M-commands found: {sorted(m_commands_found)}")
        if laser_commands_found:
            logger.info(f"[SVG_TO_GCODE] Summary - Laser commands found: {laser_commands_found}")
        else:
            logger.warning(f"[SVG_TO_GCODE] Summary - No laser on/off commands (M3/M4/M5) found in G-code")

        grbl.move_absolute(grbl_ser, x=0.0, y=0.0, feed=movement_feed, invert_y=True)
        distance_to_home = ((current_x) ** 2 + (current_y) ** 2) ** 0.5
        if distance_to_home > 0:
            move_time = (distance_to_home / movement_feed) * 60.0 + 0.5
            time.sleep(move_time)
            grbl_ser.read_all()

        final_pos = grbl.query_position(grbl_ser)

        return SvgToGcodeResponse(
            status="success",
            message=f"SVG converted and executed successfully. {commands_sent} commands sent.",
            commands_sent=commands_sent,
            final_position_x=final_pos.x,
            final_position_y=final_pos.y,
            final_position_z=final_pos.z
        )

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"svg-to-gcode library not available: {str(e)}")
    except Exception as e:
        logger.error(f"SVG to G-code conversion failed: {e}")
        raise HTTPException(status_code=500, detail=f"SVG to G-code conversion failed: {str(e)}")

def factory(app: fastapi.FastAPI) -> APIRouter:
    """
    Create and configure the operations API router with SVG to G-code endpoints.

    Args:
        app: FastAPI application instance

    Returns:
        Configured APIRouter with operations endpoints:
        - POST /operations/svg-to-gcode - Convert SVG file to G-code and execute on machine
    """
    router = APIRouter(prefix="/operations", tags=["operations"])

    router.add_api_route(
        "/svg-to-gcode",
        svg_to_gcode_endpoint,
        methods=["POST"],
        response_model=SvgToGcodeResponse
    )

    return router
