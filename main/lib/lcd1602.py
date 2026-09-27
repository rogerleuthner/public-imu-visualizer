# Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import math
import sys
import time
from time import sleep_ms

from machine import Pin

# ============================================================
# LCD1602 - HD44780 4-bit interface
#
# GPIO:
# RS = 4
# E  = 5
# D4 = 15
# D5 = 16
# D6 = 17
# D7 = 18
#
# Initialization uses the exact sequence from the known-good
# standalone LCD test.
#
# Runtime updates are non-blocking.
# ============================================================

RS = Pin(4, Pin.OUT)
E = Pin(5, Pin.OUT)

D4 = Pin(15, Pin.OUT)
D5 = Pin(16, Pin.OUT)
D6 = Pin(17, Pin.OUT)
D7 = Pin(18, Pin.OUT)

LCD_RATE_HZ = 2
LCD_PAGE_TIME_MS = 3000


class LCD1602:
    def __init__(self):

        self.last_lcd_time = time.ticks_us()

        self.lcd_period_us = 1000000 // LCD_RATE_HZ

        self.lcd_page = 0

        self.lcd_page_time = time.ticks_ms()

        self.lcd_last_imu_rate = 0.0
        self.lcd_last_irq_rate = 0.0

        self.ready = False
        self.busy = False

        self.line1 = "                "
        self.line2 = "                "

        self.target_line1 = "                "
        self.target_line2 = "                "

        self.position = 0

        # ----------------------------------------------------
        # Runtime byte state.
        #
        # 0 = idle
        # 1 = high nibble pulse
        # 2 = low nibble pulse
        # 3 = byte settling
        # ----------------------------------------------------

        self.state = 0

        # What operation happens after the current byte?
        #
        # 0 = none
        # 1 = address byte
        # 2 = character byte
        #
        self.operation = 0

        self.pending_line = 0
        self.pending_index = 0
        self.pending_char = " "

        self.byte_value = 0

        self.deadline = 0

        try:
            RS.value(0)
            E.value(0)

            # ====================================================
            # EXACT KNOWN-GOOD INITIALIZATION
            # ====================================================

            sleep_ms(100)

            self.nibble(0x03)
            sleep_ms(5)

            self.nibble(0x03)
            sleep_ms(5)

            self.nibble(0x03)
            sleep_ms(1)

            self.nibble(0x02)
            sleep_ms(1)

            self.command(0x28)
            self.command(0x0C)
            self.command(0x06)
            self.command(0x01)

            sleep_ms(5)

            self.ready = True

            print("LCD initialized")

        except Exception as e:  # noqa: BLE001 This is done so LCD class instance always exists, it just might not do anything
            print("Failed to initialize LCD")
            sys.print_exception(e)

    # ========================================================
    # LOW LEVEL - PROVEN BLOCKING FUNCTIONS
    # ========================================================

    def set_nibble(self, value):

        D4.value((value >> 0) & 1)
        D5.value((value >> 1) & 1)
        D6.value((value >> 2) & 1)
        D7.value((value >> 3) & 1)

    def nibble(self, value):

        self.set_nibble(value)

        E.value(1)
        sleep_ms(1)

        E.value(0)
        sleep_ms(1)

    def command(self, value):

        RS.value(0)

        self.nibble(value >> 4)
        self.nibble(value & 0x0F)

        sleep_ms(2)

    def char(self, value):

        RS.value(1)

        self.nibble(value >> 4)
        self.nibble(value & 0x0F)

        sleep_ms(1)

    # ========================================================
    # START NON-BLOCKING BYTE
    # ========================================================

    def start_byte(self, rs, value):

        self.byte_value = value

        RS.value(rs)

        self.set_nibble(value >> 4)

        E.value(1)

        self.state = 1

        self.deadline = time.ticks_add(time.ticks_us(), 100)

    # ========================================================
    # SERVICE NON-BLOCKING BYTE
    #
    # Returns True only when the byte is completely finished.
    # ========================================================

    def service_byte(self):

        now = time.ticks_us()

        if time.ticks_diff(now, self.deadline) < 0:
            return False

        # ----------------------------------------------------
        # Finish high-nibble pulse.
        # ----------------------------------------------------

        if self.state == 1:
            E.value(0)

            self.set_nibble(self.byte_value & 0x0F)

            E.value(1)

            self.state = 2

            self.deadline = time.ticks_add(now, 100)

            return False

        # ----------------------------------------------------
        # Finish low-nibble pulse.
        # ----------------------------------------------------

        if self.state == 2:
            E.value(0)

            self.state = 3

            self.deadline = time.ticks_add(now, 100)

            return False

        # ----------------------------------------------------
        # Byte completely finished.
        # ----------------------------------------------------

        if self.state == 3:
            self.state = 0

            return True

        self.state = 0

        return True

    # ========================================================
    # REQUEST DISPLAY UPDATE
    # ========================================================

    def show(self, line1="", line2=""):

        if not self.ready:
            return False

        if self.busy:
            return False

        line1 = str(line1)[:16]
        line2 = str(line2)[:16]

        while len(line1) < 16:
            line1 += " "

        while len(line2) < 16:
            line2 += " "

        self.target_line1 = line1
        self.target_line2 = line2

        self.position = 0

        self.busy = True

        return True

    # ========================================================
    # SERVICE
    #
    # This is called every pass through the existing main loop.
    #
    # It performs no sleeps.
    # ========================================================

    def service(self):

        if not self.ready:
            return

        # ====================================================
        # Finish an LCD byte already in progress.
        # ====================================================

        if self.state != 0:
            if not self.service_byte():
                return

            # ------------------------------------------------
            # Address byte just completed.
            # Now start the character byte.
            # ------------------------------------------------

            if self.operation == 1:
                self.operation = 2

                self.start_byte(1, ord(self.pending_char))

                return

            # ------------------------------------------------
            # Character byte just completed.
            # Commit it to our local display state.
            # ------------------------------------------------

            if self.operation == 2:
                if self.pending_line == 1:
                    index = self.pending_index

                    self.line1 = (
                        self.line1[:index] + self.pending_char + self.line1[index + 1 :]
                    )

                else:
                    index = self.pending_index

                    self.line2 = (
                        self.line2[:index] + self.pending_char + self.line2[index + 1 :]
                    )

                self.operation = 0

                return

        # ====================================================
        # Nothing is currently being transmitted.
        # ====================================================

        if not self.busy:
            return

        # ====================================================
        # Entire display update complete.
        # ====================================================

        if self.position >= 32:
            self.busy = False

            return

        # ====================================================
        # Determine current position.
        # ====================================================

        if self.position < 16:
            index = self.position

            current = self.line1[index]
            target = self.target_line1[index]

            address = 0x80 + index

            pending_line = 1

        else:
            index = self.position - 16

            current = self.line2[index]
            target = self.target_line2[index]

            address = 0xC0 + index

            pending_line = 2

        # ====================================================
        # Character already correct.
        # ====================================================

        if current == target:
            self.position += 1

            return

        # ====================================================
        # Character needs changing.
        #
        # First send DDRAM address.
        # ====================================================

        self.pending_line = pending_line
        self.pending_index = index
        self.pending_char = target

        self.position += 1

        self.operation = 1

        self.start_byte(0, address)

    ###
    # Convenience interface
    ##

    # write the text lines (now!), silently returning if it can't
    def writeNow(self, line1, line2):

        if self.ready:
            self.show(line1, line2)

            while self.busy:
                self.service()


    # need to make sure 'service' call is required for this computation; if not move to update_lcd
    def is_update_due(self, now):
        self.service()
        if self.ready:
            return time.ticks_diff(now, self.last_lcd_time) >= self.lcd_period_us

    def update_lcd(
        self,
        now,
        roll,
        pitch,
        yaw,
        temp,
        ax,
        ay,
        az,
        gx,
        gy,
        gz,
        event_rate,
        serial_rate,
        sequence,
        ip,
    ):

        self.last_lcd_time = now

        now_ms = time.ticks_ms()

        if time.ticks_diff(now_ms, self.lcd_page_time) >= LCD_PAGE_TIME_MS:
            self.lcd_page = (self.lcd_page + 1) % 6
            self.lcd_page_time = now_ms

        if self.lcd_page == 0:
            self.show(
                f"R{math.degrees(roll):6.1f} P{math.degrees(pitch):6.1f}",
                f"Y{math.degrees(yaw):6.1f} T{temp:5.1f}",
            )

        elif self.lcd_page == 1:
            self.show(f"AX{ax:6.2f} AY{ay:5.2f}", f"AZ{az:6.2f}")

        elif self.lcd_page == 2:
            self.show(f"GX{gx:6.2f} GY{gy:5.2f}", f"GZ{gz:6.2f}")

        elif self.lcd_page == 3:
            self.show(
                f"IMU {self.lcd_last_imu_rate:6.1f}Hz",
                f"IRQ {self.lcd_last_irq_rate:6.1f}Hz",
            )

        elif self.lcd_page == 4:
            self.show(
                f"EVT{event_rate:3d} SER{serial_rate:3d}",
                f"SEQ {sequence:08d}",
            )

        elif self.lcd_page == 5:
            self.show(f"IP{ip}")
