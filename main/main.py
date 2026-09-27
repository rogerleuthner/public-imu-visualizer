# Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import json
import math
import sys
import time

from imu_server import IMUServer
from lib.banner import print_banner
from lib.esp32s_monitor import ESP32SystemMonitor
from lib.gy521 import (
    GY521,
    IMU_RATE_MAX_HZ,
    IMU_RATE_MIN_HZ,
)
from lib.lcd1602 import LCD1602
from lib.version import (  # type: ignore source file is generated at ui build
    APP_NAME,
    APP_VERSION,
)
from machine import I2C, Pin

print_banner(APP_VERSION, APP_NAME)

# ============================================================
# CONFIGURATION
# ============================================================

SDA_PIN = 8
SCL_PIN = 9

INT_PIN = 7

I2C_FREQ = 400000

# ------------------------------------------------------------
# MPU output rate
# ------------------------------------------------------------

IMU_RATE_HZ = 100


# ------------------------------------------------------------
# Output rates
# ------------------------------------------------------------

SERIAL_RATE_HZ = 10
NETWORK_RATE_HZ = 20

EVENT_RATE_MIN_HZ = 1
EVENT_RATE_MAX_HZ = 100


# ------------------------------------------------------------
# Complementary filter
# ------------------------------------------------------------

ALPHA = 0.98


# ============================================================
# LCD
# ============================================================

lcd = LCD1602()
lcd.writeNow(APP_VERSION, APP_NAME)


# ============================================================
# INTERRUPT STATE
#
# Do not use module-level globals for this.
# ============================================================


class IMUInterruptState:
    def __init__(self):

        self.ready = False
        self.interrupts = 0


imu_state = IMUInterruptState()


def imu_irq(pin):

    imu_state.ready = True
    imu_state.interrupts += 1


# ============================================================
# I2C
# ============================================================

i2c = I2C(0, scl=Pin(SCL_PIN), sda=Pin(SDA_PIN), freq=I2C_FREQ)

# ============================================================
# GY-521
# ============================================================

gyro = GY521(i2c)

# ============================================================
# TIME
# ============================================================


def now_us():
    return time.ticks_us()


# ============================================================
# NETWORK SERVER
# ============================================================

print("Creating network...")

server = IMUServer()

server.start_wifi()

server.start_server()

IMU_RATE_HZ = int(server.config.get("imu_rate_hz", IMU_RATE_HZ))

IMU_RATE_HZ = max(IMU_RATE_HZ, IMU_RATE_MIN_HZ)

IMU_RATE_HZ = min(IMU_RATE_HZ, IMU_RATE_MAX_HZ)

# ============================================================
# INITIALIZE GY-531
# ============================================================

print("Initializing MPU-6050...")

try:
    gyro.initialize(IMU_RATE_HZ)
except Exception as e:  # noqa: BLE001 don't allow sensor absence to kill loop
    print("Sensor initialize error:", e)

# ============================================================
# CONFIGURE ESP32 INTERRUPT PIN
# ============================================================

imu_int = Pin(INT_PIN, Pin.IN, Pin.PULL_DOWN)

imu_int.irq(trigger=Pin.IRQ_RISING, handler=imu_irq)

print("IMU interrupt enabled on GPIO", INT_PIN)


# ============================================================
# CLEAR PENDING INTERRUPT
# GYRO CALIBRATION
# INITIAL ORIENTATION
# ============================================================

try:
    # read_sensor() should already do this
    #gyro.clear_interrupt()

    gyro.calibrate_gyro()

    (ax_raw, ay_raw, az_raw, temp_raw, gx_raw, gy_raw, gz_raw) = gyro.read_sensor()

    (ax, ay, az, temperature, gx, gy, gz) = gyro.process_sensor_data(
        (ax_raw, ay_raw, az_raw, temp_raw, gx_raw, gy_raw, gz_raw)
    )

except Exception as e:  # noqa: BLE001 don't allow sensor absence to kill loop
    print("Sensor setup error:", e)
    temperature = ax = ay = az = gx = gy = gz = 0

roll = math.atan2(ay, az)

pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))

yaw = 0.0


# ============================================================
# DATA STATE
# ============================================================

sequence = 0


# ============================================================
# TIMING
# ============================================================

last_sample_time = now_us()

last_serial_time = last_sample_time

last_network_time = last_sample_time


serial_period_us = 1000000 // SERIAL_RATE_HZ

network_period_us = 1000000 // NETWORK_RATE_HZ

configured_imu_rate_hz = IMU_RATE_HZ

configured_event_rate_hz = NETWORK_RATE_HZ


# ============================================================
# RATE STATISTICS
# ============================================================

statistics_start = last_sample_time

statistics_samples = 0


# ============================================================
# PACKET GENERATION
# ============================================================


def make_packet():

    output = {
        "seq": sequence,
        "t": time.ticks_ms(),
        "ax": round(ax, 4),
        "ay": round(ay, 4),
        "az": round(az, 4),
        "gx": round(gx, 3),
        "gy": round(gy, 3),
        "gz": round(gz, 3),
        "roll": round(math.degrees(roll), 2),
        "pitch": round(math.degrees(pitch), 2),
        "yaw": round(math.degrees(yaw), 2),
        "temp": round(temperature, 2),
    }

    return json.dumps(output)


monitor = ESP32SystemMonitor(enable_wifi=True, watchdog_timeout_ms=None, auto_gc=True)

# ============================================================
# MAIN LOOP
# ============================================================

while True:
    monitor.loop_tick()

    # --------------------------------------------------------
    # Network
    #
    # This is intentionally called every loop.
    # It performs only a bounded amount of network work.
    # --------------------------------------------------------

    try:
        server.poll()

    except Exception as e:
        # Last-resort safety net: an uncaught exception here
        # would otherwise take down the whole main loop (and
        # therefore the IMU sampling too), not just the
        # network layer. Log it and keep the loop alive.
        #
        # sys.print_exception() gives the actual file/line
        # traceback -- str(e) alone (used previously) only
        # shows the exception's message, which for low-level
        # TypeErrors from C-level calls is not enough to find
        # the offending line.
        print("server.poll() error:")

        sys.print_exception(e)

        server.close_http_client()

    # --------------------------------------------------------
    # Apply updated IMU rate.  
    # TODO This is kind of expensive - consider requiring
    # reboot to employ an updated IMU rate.
    # --------------------------------------------------------

    try:
        requested_imu_rate_hz = int(
            server.config.get("imu_rate_hz", configured_imu_rate_hz)
        )

    except Exception:
        requested_imu_rate_hz = configured_imu_rate_hz

    if requested_imu_rate_hz != configured_imu_rate_hz:
        requested_imu_rate_hz = max(requested_imu_rate_hz, IMU_RATE_MIN_HZ)

        requested_imu_rate_hz = min(requested_imu_rate_hz, IMU_RATE_MAX_HZ)

        gyro.set_rate(requested_imu_rate_hz)

        IMU_RATE_HZ = requested_imu_rate_hz

        configured_imu_rate_hz = requested_imu_rate_hz

    # --------------------------------------------------------
    # Apply updated event rate.
    # --------------------------------------------------------

    try:
        requested_event_rate_hz = int(
            server.config.get("event_rate_hz", configured_event_rate_hz)
        )

    except Exception:
        requested_event_rate_hz = configured_event_rate_hz

    requested_event_rate_hz = max(requested_event_rate_hz, EVENT_RATE_MIN_HZ)

    requested_event_rate_hz = min(requested_event_rate_hz, EVENT_RATE_MAX_HZ)

    if requested_event_rate_hz != configured_event_rate_hz:
        network_period_us = 1000000 // requested_event_rate_hz

        configured_event_rate_hz = requested_event_rate_hz

    # --------------------------------------------------------
    # IMU data-ready interrupt.
    # --------------------------------------------------------

    if imu_state.ready:
        imu_state.ready = False

        # ----------------------------------------------------
        # Clear MPU interrupt. (removed - read_sensor() should already do this internally)
        # ----------------------------------------------------

        # try:
        #     gyro.read_reg(0x3A)

        # except OSError:
        #     continue

        # ----------------------------------------------------
        # Read sensor.
        # ----------------------------------------------------

        try:
            (ax_raw, ay_raw, az_raw, temp_raw, gx_raw, gy_raw, gz_raw) = (
                gyro.read_sensor()
            )

        except (OSError, ValueError) as e:
            # OSError: I2C bus error (NACK, arbitration, etc).
            # ValueError: struct.unpack got the wrong number of
            # bytes back -- e.g. a truncated/glitched I2C read.
            # Neither should be allowed to escape the main loop.
            print("Sensor read error:", e)

            continue

        # ----------------------------------------------------
        # Sample timing.
        # ----------------------------------------------------

        sample_time = now_us()

        dt = time.ticks_diff(sample_time, last_sample_time) / 1000000.0

        last_sample_time = sample_time

        if dt <= 0:
            dt = 1.0 / IMU_RATE_HZ

        # ----------------------------------------------------
        # Accelerometer.
        # ----------------------------------------------------

        (ax, ay, az, temperature, gx, gy, gz) = gyro.process_sensor_data(
            (ax_raw, ay_raw, az_raw, temp_raw, gx_raw, gy_raw, gz_raw)
        )

        # ----------------------------------------------------
        # Accelerometer angles.
        # ----------------------------------------------------

        accel_roll = math.atan2(ay, az)

        accel_pitch = math.atan2(-ax, math.sqrt(ay * ay + az * az))

        # ----------------------------------------------------
        # Gyro integration.
        # ----------------------------------------------------

        gyro_roll = roll + math.radians(gx) * dt

        gyro_pitch = pitch + math.radians(gy) * dt

        yaw += math.radians(gz) * dt

        # ----------------------------------------------------
        # Complementary filter.
        # ----------------------------------------------------

        roll = ALPHA * gyro_roll + (1.0 - ALPHA) * accel_roll

        pitch = ALPHA * gyro_pitch + (1.0 - ALPHA) * accel_pitch

        # ----------------------------------------------------
        # Sample counter.
        # ----------------------------------------------------

        sequence += 1

        statistics_samples += 1

        # ----------------------------------------------------
        # SSE
        #
        # send() is now non-blocking and bounded.
        # If the previous event hasn't drained, the server
        # deliberately drops this event rather than building
        # an unbounded queue.
        # ----------------------------------------------------

        sample_now = now_us()

        if time.ticks_diff(sample_now, last_network_time) >= network_period_us:
            last_network_time = sample_now

            packet = make_packet()

            server.send(packet)

    # ========================================================
    # SERIAL
    # TODO consider sharing make_packet() with above
    # ========================================================

    now = now_us()

    if time.ticks_diff(now, last_serial_time) >= serial_period_us:
        last_serial_time = now

        packet = make_packet()

        print(packet)

    # ========================================================
    # RATE STATISTICS
    # ========================================================

    elapsed = time.ticks_diff(now, statistics_start)

    if elapsed >= 5000000:
        actual_rate = statistics_samples / (elapsed / 1000000.0)

        irq_rate = imu_state.interrupts / (elapsed / 1000000.0)

        lcd.lcd_last_imu_rate = actual_rate
        lcd.lcd_last_irq_rate = irq_rate

        print(
            f"IMU rate: {actual_rate:.1f} Hz | IRQ rate: {irq_rate:.1f} Hz | "
            f"samples: {statistics_samples} | interrupts: {imu_state.interrupts}"
        )

        statistics_start = now
        statistics_samples = 0
        imu_state.interrupts = 0

        _str = monitor.jsonStr()
        print(_str)
        server.send(_str)

    if lcd.is_update_due(now):
        lcd.update_lcd(
            now, roll, pitch, yaw,
            temperature, ax, ay, az, gx, gy, gz,
            requested_event_rate_hz,
            serial_period_us, sequence, server.ip )

    # Feed the watchdog only when the main application loop
    # is known to be healthy.
    monitor.feed_watchdog()
