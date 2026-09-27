# Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import struct
import time

# ============================================================
# GY-521 / MPU-6050
# ============================================================

MPU_ADDR = 0x68

# ------------------------------------------------------------
# Sensor scaling
# ------------------------------------------------------------

ACCEL_SCALE = 16384.0
GYRO_SCALE = 131.0


# ------------------------------------------------------------
# MPU output rate
# ------------------------------------------------------------

IMU_RATE_MIN_HZ = 4
IMU_RATE_MAX_HZ = 1000


# ------------------------------------------------------------
# Gyro calibration
# ------------------------------------------------------------

CALIBRATION_SAMPLES = 200


# ============================================================
# MPU-6050 REGISTERS
# ============================================================

PWR_MGMT_1 = 0x6B
SMPLRT_DIV = 0x19
CONFIG = 0x1A
GYRO_CONFIG = 0x1B
ACCEL_CONFIG = 0x1C
INT_PIN_CFG = 0x37
INT_ENABLE = 0x38
INT_STATUS = 0x3A
ACCEL_XOUT_H = 0x3B
WHO_AM_I = 0x75


class GY521:
    def __init__(self, i2c, address=MPU_ADDR):

        self.i2c = i2c
        self.address = address

        self.gyro_bias_x = 0.0
        self.gyro_bias_y = 0.0
        self.gyro_bias_z = 0.0

    def write_reg(self, reg, value):

        self.i2c.writeto_mem(self.address, reg, bytes([value]))

    def read_reg(self, reg):

        return self.i2c.readfrom_mem(self.address, reg, 1)[0]

    def read_sensor(self):

        data = self.i2c.readfrom_mem(self.address, ACCEL_XOUT_H, 14)

        (ax, ay, az, temp, gx, gy, gz) = struct.unpack(">hhhhhhh", data)

        return (ax, ay, az, temp, gx, gy, gz)

    def initialize(self, imu_rate_hz):

        # ----------------------------------------------------
        # Wake MPU
        # ----------------------------------------------------

        self.write_reg(PWR_MGMT_1, 0x00)

        time.sleep_ms(100)

        # ----------------------------------------------------
        # Sample rate
        # ----------------------------------------------------

        imu_rate_hz = int(imu_rate_hz)

        imu_rate_hz = max(imu_rate_hz, IMU_RATE_MIN_HZ)

        imu_rate_hz = min(imu_rate_hz, IMU_RATE_MAX_HZ)

        self.set_rate(imu_rate_hz)

        # ----------------------------------------------------
        # Digital Low Pass Filter
        # ----------------------------------------------------

        self.write_reg(CONFIG, 0x03)

        # ----------------------------------------------------
        # Gyroscope
        # ----------------------------------------------------

        self.write_reg(GYRO_CONFIG, 0x00)

        # ----------------------------------------------------
        # Accelerometer
        # ----------------------------------------------------

        self.write_reg(ACCEL_CONFIG, 0x00)

        # ----------------------------------------------------
        # Interrupt configuration
        # ----------------------------------------------------

        self.write_reg(INT_PIN_CFG, 0x00)

        # ----------------------------------------------------
        # Enable Data Ready interrupt
        # ----------------------------------------------------

        self.write_reg(INT_ENABLE, 0x01)

        # ----------------------------------------------------
        # Check device identity
        # ----------------------------------------------------

        who = self.read_reg(WHO_AM_I)

        print("WHO_AM_I:", hex(who))

    def set_rate(self, imu_rate_hz):

        imu_rate_hz = int(imu_rate_hz)

        imu_rate_hz = max(imu_rate_hz, IMU_RATE_MIN_HZ)

        imu_rate_hz = min(imu_rate_hz, IMU_RATE_MAX_HZ)

        sample_rate_div_value = max(0, min(255, int(round(1000 / imu_rate_hz) - 1)))

        self.write_reg(SMPLRT_DIV, sample_rate_div_value)

    def clear_interrupt(self):

        try:
            self.read_reg(INT_STATUS)

        except OSError:
            pass

    def calibrate_gyro(self):

        print("Keep sensor still...")

        print("Calibration starts in 3 seconds.")

        time.sleep(3)

        gx_sum = 0
        gy_sum = 0
        gz_sum = 0

        for i in range(CALIBRATION_SAMPLES):
            (ax_raw, ay_raw, az_raw, temp_raw, gx_raw, gy_raw, gz_raw) = (
                self.read_sensor()
            )

            gx_sum += gx_raw
            gy_sum += gy_raw
            gz_sum += gz_raw

            time.sleep_ms(5)

        self.gyro_bias_x = gx_sum / CALIBRATION_SAMPLES / GYRO_SCALE

        self.gyro_bias_y = gy_sum / CALIBRATION_SAMPLES / GYRO_SCALE

        self.gyro_bias_z = gz_sum / CALIBRATION_SAMPLES / GYRO_SCALE

        print("Calibration complete.")

        print("Bias:", self.gyro_bias_x, self.gyro_bias_y, self.gyro_bias_z)

    def process_sensor_data(self, sensor_data):

        (ax_raw, ay_raw, az_raw, temp_raw, gx_raw, gy_raw, gz_raw) = sensor_data

        ax = ax_raw / ACCEL_SCALE
        ay = ay_raw / ACCEL_SCALE
        az = az_raw / ACCEL_SCALE

        gx = gx_raw / GYRO_SCALE
        gy = gy_raw / GYRO_SCALE
        gz = gz_raw / GYRO_SCALE

        gx -= self.gyro_bias_x
        gy -= self.gyro_bias_y
        gz -= self.gyro_bias_z

        temperature = (temp_raw / 340.0) + 36.53

        return (ax, ay, az, temperature, gx, gy, gz)
