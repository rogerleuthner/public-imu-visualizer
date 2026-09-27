
<p align="center">
  <img src="media/hero.jpg" alt="IMU Visualizer" width="900">
</p>

<h1 align="center">IMU Visualizer</h1>

<p align="center">
  ESP32-S3 appliance sensor visualizing built with MicroPython
</p>

<p align="center">
<!--
  <a href="[![Watch it in action](https://img.youtube.com/vi/D5P4xrF4DOM/hqdefault.jpg)](https://youtu.be/D5P4xrF4DOM)">▶ Watch it in action</a> -->
  <a href="https://www.youtube.com/watch?v=4rmvpj-eMhI">▶ Watch it in action</a>

</p>

<hr>

# ESP32-S3 / GY-521 6-Axis IMU Visualization

A MicroPython and React-based wireless IMU monitoring system built around an ESP32-S3 and GY-521 (MPU-6050) sensor module.

The ESP32-S3 runs the embedded application, manages the sensor acquisition loop, provides Wi-Fi connectivity, and hosts a web server that serves a React visualization application. The browser application displays live orientation, acceleration data, diagnostics, and a 3D representation of the device orientation.

## Features

- ESP32-S3 MicroPython firmware
  - Runs the main application loop.
  - Initializes and monitors the GY-521 IMU.
  - Performs sensor sampling and orientation calculations.
  - Runs the Wi-Fi and HTTP services.
  - Maintains hardware monitoring.

- Flexible Wi-Fi operation
  - Access Point mode.
  - Station mode joining an existing network.
  - Automatic mode selection with AP fallback.

- Embedded web server
  - Serves the React application directly from the ESP32 filesystem.
  - Provides REST-style configuration and status endpoints.
  - Provides Server-Sent Events (SSE) for live sensor streaming.

- React web application
  - Live 3D ESP32/GY-521 visualization.
  - Real-time orientation display.
  - Roll, pitch, and yaw graphs.
  - Accelerometer graphs.
  - Sensor diagnostics.
  - Orientation zeroing.
  - Wi-Fi and device settings interfaces.

## System Architecture

The system consists of three primary layers:

    +------------------------------------------------+
    |                React Web Application            |
    |                                                |
    |  3D View | Graphs | Diagnostics | Settings     |
    +--------------------------+---------------------+
                               |
                               | HTTP / SSE
                               |
    +--------------------------v---------------------+
    |              ESP32-S3 Web Server               |
    |                                                |
    |  Static Files | REST API | SSE Streaming       |
    +--------------------------+---------------------+
                               |
                               |
    +--------------------------v---------------------+
    |           MicroPython Application              |
    |                                                |
    | IMU Loop | Wi-Fi | LCD | Monitoring | Control  |
    +--------------------------+---------------------+
                               |
                               |
    +--------------------------v---------------------+
    |                 GY-521 MPU-6050                |
    |                                                |
    | Accelerometer + Gyroscope + Temperature       |
    +------------------------------------------------+

## Hardware

The project uses:

- ESP32-S3 development board.
- GY-521 module containing an MPU-6050 six-axis IMU.
- LCD1602 display module.
- I2C-connected peripherals.

The default I2C configuration in `main.py` is:

| Signal | GPIO |
| --- | ---: |
| SDA | 8 |
| SCL | 9 |
| IMU Interrupt | 7 |

## Firmware Overview

The MicroPython firmware entry point is `main.py`.

Responsibilities include:

- Starting the Wi-Fi subsystem.
- Starting the embedded HTTP server.
- Initializing the IMU.
- Handling IMU interrupts.
- Reading sensor data.
- Applying a complementary orientation filter.
- Generating sensor packets.
- Streaming data to connected clients.
- Reporting system statistics.

The main sensor packet contains:

    {
        "seq": 1,
        "t": 123456,
        "ax": 0.0,
        "ay": 0.0,
        "az": 1.0,
        "gx": 0.0,
        "gy": 0.0,
        "gz": 0.0,
        "roll": 0.0,
        "pitch": 0.0,
        "yaw": 0.0,
        "temp": 25.0
    }

## Network Server

`imu_server.py` provides the network services used by the application.

### Supported Wi-Fi Modes

The server supports:

| Mode | Description |
| --- | --- |
| `AP` | Starts the ESP32 as a Wi-Fi access point. |
| `STA` | Connects to an existing Wi-Fi network. |
| `AUTO` | Starts AP mode first, attempts STA connection, and falls back when necessary. |

The configuration file is:

    /wifi_config.json

Example configuration structure:

    {
        "mode": "AUTO",
        "ssid": "network_name",
        "password": "network_password",
        "ap_ssid": "ESP32-IMU",
        "ap_password": "YOUR_AP_PASSWORD",
        "ap_channel": 6,
        "imu_rate_hz": 50,
        "event_rate_hz": 5
    }

## HTTP API

The embedded server provides the following endpoints.

### Status

Request:

    GET /api/status

Returns current network information and server status.

### Configuration

Request:

    GET /api/config

Returns public configuration information.

Configuration updates:

    POST /api/config

The server accepts JSON configuration updates and applies network changes when required.

### Sensor Events

The live sensor stream uses Server-Sent Events:

    GET /events

The browser application receives sensor packets through this stream.

## Sensor Processing

The firmware:

1. Reads accelerometer and gyroscope values from the MPU-6050.
2. Converts raw sensor readings into processed values.
3. Calculates accelerometer-based orientation.
4. Integrates gyroscope rotation.
5. Combines both using a complementary filter.

The filter coefficient is configured in `main.py`:

    ALPHA = 0.98

## React Application

The React application is the browser interface for the device.

Main capabilities:

- Three-dimensional device visualization using React Three Fiber.
- Live sensor charts.
- Orientation monitoring.
- Packet diagnostics.
- Connection management.
- Orientation zeroing.

The main application component is:

    App.jsx

The application communicates with the ESP32 through:

    Wi-Fi / SSE

## Data Flow

    MPU-6050
        |
        v
    MicroPython sensor loop
        |
        v
    Orientation calculation
        |
        v
    SSE event stream
        |
        v
    React state updates
        |
        v
    3D display and charts

## Embedded Web Server Design

The HTTP server is designed for constrained embedded operation.

Characteristics:

- Non-blocking sockets.
- Bounded network work per polling cycle.
- Single active HTTP client.
- Single SSE client.
- Chunked static file transmission.
- Protection against stalled clients.
- Limited buffering to prevent memory growth.

## Project Structure

A typical project layout:

    .
    ├── main.py
    ├── imu_server.py
    ├── lib/
    │   ├── gy521.py
    │   ├── lcd1602.py
    │   ├── esp32s_monitor.py
    │   └── version.py
    └── web application files
        ├── App.jsx
        ├── App.css
        └── supporting React components

## Running the Device

1. Flash MicroPython onto the ESP32-S3.
2. Copy the firmware files to the device filesystem.
3. Build and deploy the React application files into the ESP32 web root.
4. Power on the ESP32-S3.
5. Connect to the configured Wi-Fi network.
6. Open the ESP32 web interface.

The default access point address configured by the server is:

    http://10.0.0.1/

## Development Notes

The firmware is designed around a continuous embedded control loop.

Important design goals:

- Keep sensor acquisition responsive.
- Avoid blocking network operations.
- Prevent network failures from stopping sensor monitoring.
- Keep memory usage predictable on MicroPython hardware.

## License

Copyright © 2026 Roger B. Leuthner. All rights reserved.

This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.
