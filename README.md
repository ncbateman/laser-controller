# Laser Controller API

![Coverage](https://img.shields.io/badge/coverage-22.7%25-orange.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-00a398.svg)
![Docker](https://img.shields.io/badge/docker-ready-blue.svg)

FastAPI backend application for controlling a laser cutter. This API provides endpoints to manage GRBL-based laser cutting operations, including homing, calibration, G-code execution, and machine control.

## ⚠️ Important Warning

**This software is designed for a very custom laser cutter configuration and is NOT intended for use with off-the-shelf laser cutting machines.**

This repository is public for reference purposes only. **We strongly advise against using this software on any machine other than the specific custom configuration it was designed for.**

**NO LIABILITY:** The authors and contributors of this software take no responsibility or liability for any damage, injury, or loss that may result from using this software on any machine. Use at your own risk.

## Features

- **Machine Control**: Homing, calibration, and movement commands
- **G-code Execution**: Run G-code files with automatic Y/Z axis coupling (dual motor Y axis)
- **Settings Management**: Configure feed rates, acceleration, and steps per mm
- **Health Monitoring**: Health check endpoint for service status

## Prerequisites

- Docker and Docker Compose (plugin)
- Make (for Linux/Mac)

## Local Setup

### 1. USB Device Requirements

The API needs access to USB serial devices for GRBL and limit controller communication. Ensure:
- USB devices are plugged in before starting the container
- Devices are accessible (typically `/dev/ttyUSB*` or `/dev/ttyACM*`)
- The container has been restarted after adding device mounts in `docker-compose.yaml`

The docker-compose.yaml is configured to mount common USB serial devices (`/dev/ttyUSB0-4` and `/dev/ttyACM0-1`) with privileged access.

### 2. Start Services

```bash
make up
```

This will:
- Build the Docker images
- Start the API service
- Follow the API logs

**Note:** If you've updated `docker-compose.yaml` to add USB device mounts, restart the container:
```bash
make restart
```

### 3. Access the API

- API: http://localhost
- Health check: http://localhost/health/
- API Documentation: http://localhost/docs (Swagger UI)
- Alternative Docs: http://localhost/redoc (ReDoc)

## Available Commands

- `make up` - Build and start services, then follow API logs
- `make down` - Stop and remove containers
- `make rebuild` - Full rebuild cycle (down, build, up, logs)
- `make restart` - Quick restart (down, up, logs)
- `make api-logs` - Follow API logs
- `make test` - Run tests
- `make test-cov` - Run tests with coverage report

## Development

The `src/` directory is mounted as a volume, so code changes are reflected immediately with hot reload enabled.

## API Endpoints

### Health
- `GET /health/` - Health check endpoint

_More endpoints will be added as the API is developed._

## Tests

**Overall Coverage:** 22.7% (Lines) | 0.0% (Branches)

### Coverage by Module

| Module | Lines | Branches |
|--------|-------|----------|
| `.` | 20.0% | 0.0% |
| `modules` | 11.8% | 0.0% |
| `routers` | 65.9% | 100.0% |
| `schemas` | 86.3% | 0.0% |
| `services` | 4.8% | 0.0% |
