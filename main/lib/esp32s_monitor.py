# Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

"""
ESP32-S3 MicroPython Production System Monitor

Target:
    ESP32-S3-DevKitC-1 N16R8

Features:
    - MicroPython heap statistics
    - Heap low-water/high-water history
    - Garbage collection statistics
    - Stack usage when available
    - Filesystem statistics
    - CPU frequency
    - Unique device ID
    - MicroPython runtime information
    - Reset reason
    - WiFi state/IP/RSSI
    - Application buffer tracking
    - Application socket tracking
    - Application error counters
    - Main-loop timing
    - Hardware watchdog
    - Health evaluation
    - JSON telemetry
    - Human-readable diagnostic report

N16R8:
    - 16 MB flash
    - 8 MB PSRAM

Important:
    gc.mem_free() and gc.mem_alloc() describe the MicroPython
    managed heap. They do NOT represent total ESP32-S3 RAM or
    total PSRAM.
"""

import gc
import json
import os
import sys
import time

import machine

try:
    import micropython
except ImportError:
    micropython = None


try:
    import network
except ImportError:
    network = None


try:
    import esp32
except ImportError:
    esp32 = None


class ESP32SystemMonitor:
    """
    Production-oriented system monitor for ESP32-S3 MicroPython.

    Designed for ESP32-S3-DevKitC-1 N16R8.

    Optional MicroPython/ESP-IDF APIs are detected at runtime so
    the monitor remains compatible across different firmware builds.
    """

    def __init__(
        self,
        enable_wifi=True,
        watchdog_timeout_ms=None,
        auto_gc=True,
    ):
        self.auto_gc = bool(auto_gc)

        # ---------------------------------------------------------
        # Timing
        # ---------------------------------------------------------

        self._boot_ms = time.ticks_ms()

        self._loop_count = 0
        self._loop_last_ms = None
        self._loop_min_ms = None
        self._loop_max_ms = 0
        self._loop_total_ms = 0

        # ---------------------------------------------------------
        # Heap history
        # ---------------------------------------------------------

        self._min_free_heap = None
        self._max_used_heap = 0

        # ---------------------------------------------------------
        # Garbage collection
        # ---------------------------------------------------------

        self._gc_count = 0
        self._gc_recovered = 0

        # ---------------------------------------------------------
        # Application counters
        # ---------------------------------------------------------

        self._counters = {
            "exceptions": 0,
            "errors": 0,
            "uart_rx_overflows": 0,
            "uart_tx_overflows": 0,
            "network_rx_errors": 0,
            "network_tx_errors": 0,
            "mqtt_reconnects": 0,
            "http_errors": 0,
            "sensor_errors": 0,
            "i2c_errors": 0,
            "spi_errors": 0,
            "watchdog_feeds": 0,
        }

        # ---------------------------------------------------------
        # Application buffers
        # ---------------------------------------------------------

        self._buffers = {}

        # ---------------------------------------------------------
        # Application sockets
        # ---------------------------------------------------------

        self._sockets = {}

        # ---------------------------------------------------------
        # WiFi
        # ---------------------------------------------------------

        self._wifi = None

        if enable_wifi and network is not None:
            try:
                self._wifi = network.WLAN(network.STA_IF)
            except Exception:
                self._wifi = None

        # ---------------------------------------------------------
        # Watchdog
        # ---------------------------------------------------------

        self._wdt = None

        if watchdog_timeout_ms is not None:
            try:
                self._wdt = machine.WDT(timeout=int(watchdog_timeout_ms))
            except Exception:
                self._wdt = None

    # =============================================================
    # UPTIME
    # =============================================================

    def uptime_ms(self):
        """Return milliseconds since monitor initialization."""

        elapsed = time.ticks_diff(
            time.ticks_ms(),
            self._boot_ms,
        )

        return int(elapsed)

    def uptime(self):
        """Return uptime in useful units."""

        milliseconds = self.uptime_ms()
        seconds = milliseconds // 1000

        return {
            "milliseconds": milliseconds,
            "seconds": seconds,
            "minutes": seconds // 60,
            "hours": seconds // 3600,
            "days": seconds // 86400,
        }

    # =============================================================
    # MEMORY
    # =============================================================

    def memory(self):
        """
        Return MicroPython heap statistics.

        This describes the MicroPython managed heap, not total
        ESP32-S3 RAM or PSRAM.
        """

        if self.auto_gc:
            gc.collect()

        free = int(gc.mem_free())
        used = int(gc.mem_alloc())
        total = free + used

        if self._min_free_heap is None or free < self._min_free_heap:
            self._min_free_heap = free

        self._max_used_heap = max(self._max_used_heap, used)

        used_percent = 0.0
        free_percent = 0.0

        if total > 0:
            used_percent = used * 100.0 / total
            free_percent = free * 100.0 / total

        return {
            "total": total,
            "used": used,
            "free": free,
            "used_percent": used_percent,
            "free_percent": free_percent,
            "minimum_free_ever": self._min_free_heap,
            "maximum_used_ever": self._max_used_heap,
        }

    # =============================================================
    # PSRAM
    # =============================================================

    def psram(self):
        """
        Return PSRAM information when supported by the firmware.

        MicroPython builds expose different ESP-IDF APIs, so this
        method is deliberately conservative.
        """

        result = {
            "available": False,
            "total": 0,
            "free": 0,
            "used": 0,
        }

        if esp32 is None:
            return result

        heap_info = getattr(
            esp32,
            "idf_heap_info",
            None,
        )

        if heap_info is None:
            return result

        try:
            info = heap_info()

            if isinstance(info, dict):
                total = int(info.get("total", 0))

                free = int(info.get("free", 0))

                result["available"] = total > 0
                result["total"] = total
                result["free"] = free
                result["used"] = max(
                    0,
                    total - free,
                )

        except Exception:
            pass

        return result

    # =============================================================
    # STACK
    # =============================================================

    def stack(self):
        """Return stack usage when supported."""

        if micropython is None:
            return {
                "available": False,
                "used": 0,
            }

        stack_use = getattr(
            micropython,
            "stack_use",
            None,
        )

        if stack_use is None:
            return {
                "available": False,
                "used": 0,
            }

        try:
            return {
                "available": True,
                "used": int(stack_use()),
            }

        except Exception:
            return {
                "available": False,
                "used": 0,
            }

    # =============================================================
    # GARBAGE COLLECTION
    # =============================================================

    def collect_garbage(self):
        """Force GC and report recovered memory."""

        before = int(gc.mem_free())

        gc.collect()

        after = int(gc.mem_free())

        recovered = after - before

        if recovered > 0:
            self._gc_recovered += recovered

        self._gc_count += 1

        return {
            "before_free": before,
            "after_free": after,
            "recovered": recovered,
            "collections": self._gc_count,
            "total_recovered": self._gc_recovered,
        }

    def gc_stats(self):
        """Return garbage collection statistics."""

        return {
            "collections": self._gc_count,
            "total_recovered": self._gc_recovered,
            "current_free": int(gc.mem_free()),
        }

    # =============================================================
    # FILESYSTEM
    # =============================================================

    def filesystem(self):
        """
        Return filesystem capacity and usage.

        getattr() is intentional.

        It prevents Pylance from reporting:

            "statvfs is not a known attribute of module os"

        while still allowing MicroPython to call os.statvfs()
        when the firmware provides it.
        """

        statvfs = getattr(
            os,
            "statvfs",
            None,
        )

        if statvfs is None:
            return {
                "available": False,
                "total": 0,
                "used": 0,
                "free": 0,
                "used_percent": 0.0,
            }

        try:
            stat = statvfs("/")

            block_size = int(stat[0])
            total_blocks = int(stat[2])
            free_blocks = int(stat[3])

            total = block_size * total_blocks

            free = block_size * free_blocks

            used = max(
                0,
                total - free,
            )

            used_percent = 0.0

            if total > 0:
                used_percent = used * 100.0 / total

            return {
                "available": True,
                "total": total,
                "used": used,
                "free": free,
                "used_percent": used_percent,
            }

        except Exception:
            return {
                "available": False,
                "total": 0,
                "used": 0,
                "free": 0,
                "used_percent": 0.0,
            }

    # =============================================================
    # CPU / DEVICE
    # =============================================================

    def cpu(self):
        """Return CPU and board information."""

        frequency_hz = 0

        try:
            frequency_hz = int(machine.freq())
        except Exception:
            pass

        unique_id = ""

        try:
            unique_id = machine.unique_id().hex()
        except Exception:
            pass

        return {
            "frequency_hz": frequency_hz,
            "frequency_mhz": (frequency_hz / 1_000_000),
            "unique_id": unique_id,
            "target": "ESP32-S3-DevKitC-1",
            "memory_variant": "N16R8",
            "flash_mb": 16,
            "psram_mb": 8,
        }

    # =============================================================
    # MICROPYTHON
    # =============================================================

    def micropython_info(self):
        """Return MicroPython runtime information."""

        version = ""
        implementation = ""
        platform = ""

        try:
            version = str(sys.version)
        except Exception:
            pass

        try:
            implementation = str(sys.implementation.name)
        except Exception:
            pass

        try:
            platform = str(sys.platform)
        except Exception:
            pass

        return {
            "version": version,
            "implementation": implementation,
            "platform": platform,
        }

    # =============================================================
    # RESET
    # =============================================================

    def reset_reason(self):
        """Return the ESP32 reset cause."""

        reset_cause = getattr(
            machine,
            "reset_cause",
            None,
        )

        if reset_cause is None:
            return {
                "available": False,
                "code": 0,
                "name": "unavailable",
            }

        try:
            reason = int(reset_cause())

        except Exception:
            return {
                "available": False,
                "code": 0,
                "name": "unavailable",
            }

        names = {}

        constants = (
            ("PWRON_RESET", "power_on"),
            ("HARD_RESET", "hard_reset"),
            ("WDT_RESET", "watchdog"),
            ("DEEPSLEEP_RESET", "deep_sleep"),
            ("SOFT_RESET", "soft_reset"),
        )

        for attribute, name in constants:
            value = getattr(
                machine,
                attribute,
                None,
            )

            if value is not None:
                names[value] = name

        return {
            "available": True,
            "code": reason,
            "name": names.get(
                reason,
                "unknown",
            ),
        }

    # =============================================================
    # WIFI
    # =============================================================

    def wifi(self):
        """Return WiFi state and connection information."""

        if self._wifi is None:
            return {
                "available": False,
                "active": False,
                "connected": False,
                "ip": "",
                "netmask": "",
                "gateway": "",
                "dns": "",
                "rssi": 0,
            }

        try:
            active = bool(self._wifi.active())
        except Exception:
            active = False

        try:
            connected = bool(self._wifi.isconnected())
        except Exception:
            connected = False

        ip = ""
        netmask = ""
        gateway = ""
        dns = ""

        if connected:
            try:
                config = self._wifi.ifconfig()

                if len(config) >= 4:
                    ip = str(config[0])
                    netmask = str(config[1])
                    gateway = str(config[2])
                    dns = str(config[3])

            except Exception:
                pass

        rssi = 0

        if connected:
            try:
                rssi = int(self._wifi.status("rssi"))
            except Exception:
                pass

        return {
            "available": True,
            "active": active,
            "connected": connected,
            "ip": ip,
            "netmask": netmask,
            "gateway": gateway,
            "dns": dns,
            "rssi": rssi,
        }

    # =============================================================
    # APPLICATION BUFFERS
    # =============================================================

    def register_buffer(
        self,
        name,
        size,
        kind="application",
    ):
        """Register an application buffer."""

        self._buffers[str(name)] = {
            "size": max(0, int(size)),
            "used": 0,
            "peak_used": 0,
            "overflow_count": 0,
            "kind": str(kind),
        }

    def update_buffer(
        self,
        name,
        used,
    ):
        """Update current buffer occupancy."""

        name = str(name)
        current_used = max(
            0,
            int(used),
        )

        if name not in self._buffers:
            self.register_buffer(
                name,
                0,
            )

        info = self._buffers[name]

        info["used"] = current_used

        if current_used > info["peak_used"]:
            info["peak_used"] = current_used

        size = info["size"]

        if size > 0 and current_used > size:
            info["overflow_count"] += 1

    def buffer_overflow(self, name):
        """Record an explicit buffer overflow."""

        name = str(name)

        if name not in self._buffers:
            self.register_buffer(
                name,
                0,
            )

        self._buffers[name]["overflow_count"] += 1

    def buffer_stats(self):
        """Return application buffer statistics."""

        result = {}

        total_size = 0
        total_used = 0

        for name, info in self._buffers.items():
            size = int(info["size"])
            used = int(info["used"])

            total_size += size

            if size > 0:
                total_used += min(
                    used,
                    size,
                )

                free = max(
                    0,
                    size - used,
                )

                used_percent = used * 100.0 / size

            else:
                total_used += used
                free = 0
                used_percent = 0.0

            result[name] = {
                "size": size,
                "used": used,
                "free": free,
                "peak_used": int(info["peak_used"]),
                "used_percent": used_percent,
                "overflow_count": int(info["overflow_count"]),
                "kind": str(info["kind"]),
            }

        total_percent = 0.0

        if total_size > 0:
            total_percent = total_used * 100.0 / total_size

        result["_total"] = {
            "size": total_size,
            "used": total_used,
            "free": max(
                0,
                total_size - total_used,
            ),
            "used_percent": total_percent,
        }

        return result

    # =============================================================
    # SOCKET TRACKING
    # =============================================================

    def register_socket(
        self,
        name,
        kind="tcp",
    ):
        """Register an application socket."""

        self._sockets[str(name)] = {
            "kind": str(kind),
            "created_ms": time.ticks_ms(),
        }

    def unregister_socket(self, name):
        """Unregister an application socket."""

        self._sockets.pop(
            str(name),
            None,
        )

    def socket_stats(self):
        """Return application socket information."""

        now = time.ticks_ms()

        sockets = {}

        for name, info in self._sockets.items():
            age_ms = int(
                time.ticks_diff(
                    now,
                    info["created_ms"],
                )
            )

            sockets[name] = {
                "kind": info["kind"],
                "age_ms": age_ms,
            }

        return {
            "count": len(self._sockets),
            "sockets": sockets,
        }

    # =============================================================
    # APPLICATION COUNTERS
    # =============================================================

    def increment(
        self,
        name,
        amount=1,
    ):
        """Increment an application counter."""

        name = str(name)

        if name not in self._counters:
            self._counters[name] = 0

        self._counters[name] += int(amount)

    def set_counter(
        self,
        name,
        value,
    ):
        """Set an application counter."""

        self._counters[str(name)] = int(value)

    def counters(self):
        """Return a copy of all counters."""

        return dict(self._counters)

    # =============================================================
    # MAIN LOOP TIMING
    # =============================================================

    def loop_tick(self):
        """
        Call once per main application loop.

        Measures elapsed time between successive calls.
        """

        now = time.ticks_ms()

        if self._loop_last_ms is not None:
            elapsed = int(
                time.ticks_diff(
                    now,
                    self._loop_last_ms,
                )
            )

            self._loop_count += 1
            self._loop_total_ms += elapsed

            if self._loop_min_ms is None:
                self._loop_min_ms = elapsed

            elif elapsed < self._loop_min_ms:
                self._loop_min_ms = elapsed

            if elapsed > self._loop_max_ms:
                self._loop_max_ms = elapsed

        self._loop_last_ms = now

    def loop_stats(self):
        """Return main-loop timing statistics."""

        average = 0.0

        if self._loop_count > 0:
            average = self._loop_total_ms / self._loop_count

        minimum = 0

        if self._loop_min_ms is not None:
            minimum = self._loop_min_ms

        return {
            "iterations": self._loop_count,
            "min_ms": minimum,
            "max_ms": self._loop_max_ms,
            "average_ms": average,
        }

    # =============================================================
    # WATCHDOG
    # =============================================================

    def watchdog_enabled(self):
        """Return whether the watchdog is enabled."""

        return self._wdt is not None

    def feed_watchdog(self):
        """Feed the hardware watchdog."""

        if self._wdt is None:
            return False

        try:
            self._wdt.feed()

            self._counters["watchdog_feeds"] += 1

            return True

        except Exception:
            return False

    # =============================================================
    # HEALTH
    # =============================================================

    def health(self):
        """Evaluate current system health."""

        memory = self.memory()
        buffers = self.buffer_stats()
        loop = self.loop_stats()

        warnings = []
        problems = []

        # ---------------------------------------------------------
        # Heap
        # ---------------------------------------------------------

        if memory["free_percent"] < 10.0:
            problems.append("MicroPython heap critically low")

        elif memory["free_percent"] < 20.0:
            warnings.append("MicroPython heap getting low")

        # ---------------------------------------------------------
        # Buffers
        # ---------------------------------------------------------

        for name, info in buffers.items():
            if name == "_total":
                continue

            if info["overflow_count"] > 0:
                problems.append(f"Buffer overflow: {name}")

            if info["size"] > 0 and info["used_percent"] > 90.0:
                warnings.append(f"Buffer nearly full: {name}")

        # ---------------------------------------------------------
        # Loop latency
        # ---------------------------------------------------------

        if loop["max_ms"] > 1000:
            warnings.append("Main loop exceeded 1 second")

        status = "OK"

        if warnings:
            status = "WARNING"

        if problems:
            status = "CRITICAL"

        return {
            "status": status,
            "warnings": warnings,
            "problems": problems,
        }

    # =============================================================
    # COMPLETE SNAPSHOT
    # =============================================================

    def snapshot(self):
        """Return a complete system snapshot."""

        return {
            "uptime": self.uptime(),
            "memory": self.memory(),
            "psram": self.psram(),
            "stack": self.stack(),
            "gc": self.gc_stats(),
            "filesystem": self.filesystem(),
            "cpu": self.cpu(),
            "micropython": self.micropython_info(),
            "reset": self.reset_reason(),
            "wifi": self.wifi(),
            "buffers": self.buffer_stats(),
            "sockets": self.socket_stats(),
            "counters": self.counters(),
            "loop": self.loop_stats(),
            "health": self.health(),
        }

    # =============================================================
    # JSON
    # =============================================================

    def jsonStr(self):
        """Return the complete system snapshot as JSON."""

        return json.dumps(self.snapshot())

    # =============================================================
    # HUMAN-READABLE REPORT
    # =============================================================

    def report(self):
        """Print a human-readable diagnostic report."""

        data = self.snapshot()

        health = data["health"]
        uptime = data["uptime"]
        memory = data["memory"]
        psram = data["psram"]
        filesystem = data["filesystem"]
        cpu = data["cpu"]
        wifi = data["wifi"]
        loop = data["loop"]
        reset = data["reset"]

        print()
        print("=" * 64)
        print(" ESP32-S3 SYSTEM HEALTH")
        print("=" * 64)

        print("TARGET       : ESP32-S3-DevKitC-1 N16R8")

        print(f"HEALTH       : {health['status']}")

        for warning in health["warnings"]:
            print(f"  WARNING    : {warning}")

        for problem in health["problems"]:
            print(f"  ERROR      : {problem}")

        # ---------------------------------------------------------
        # Uptime
        # ---------------------------------------------------------

        print()
        print(
            "UPTIME       : "
            f"{uptime['days']}d "
            f"{uptime['hours'] % 24:02d}:"
            f"{uptime['minutes'] % 60:02d}:"
            f"{uptime['seconds'] % 60:02d}"
        )

        # ---------------------------------------------------------
        # MicroPython heap
        # ---------------------------------------------------------

        print()
        print("MICROPYTHON HEAP")

        print(f"  Total      : {memory['total']:,} B")

        print(f"  Used       : {memory['used']:,} B ({memory['used_percent']:.1f}%)")

        print(f"  Free       : {memory['free']:,} B ({memory['free_percent']:.1f}%)")

        print(f"  Min free   : {memory['minimum_free_ever']:,} B")

        print(f"  Max used   : {memory['maximum_used_ever']:,} B")

        # ---------------------------------------------------------
        # PSRAM
        # ---------------------------------------------------------

        print()
        print("PSRAM")

        if psram["available"]:
            print(f"  Total      : {psram['total']:,} B")

            print(f"  Used       : {psram['used']:,} B")

            print(f"  Free       : {psram['free']:,} B")

        else:
            print("  Runtime API unavailable")

        # ---------------------------------------------------------
        # Stack
        # ---------------------------------------------------------

        stack = data["stack"]

        print()
        print("STACK")

        if stack["available"]:
            print(f"  Used       : {stack['used']:,} B")

        else:
            print("  Unavailable")

        # ---------------------------------------------------------
        # Filesystem
        # ---------------------------------------------------------

        print()
        print("FILESYSTEM")

        if filesystem["available"]:
            print(f"  Total      : {filesystem['total']:,} B")

            print(
                f"  Used       : "
                f"{filesystem['used']:,} B "
                f"({filesystem['used_percent']:.1f}%)"
            )

            print(f"  Free       : {filesystem['free']:,} B")

        else:
            print("  Unavailable")

        # ---------------------------------------------------------
        # CPU
        # ---------------------------------------------------------

        print()
        print("CPU")

        print(f"  Frequency  : {cpu['frequency_mhz']:.1f} MHz")

        # ---------------------------------------------------------
        # WiFi
        # ---------------------------------------------------------

        print()
        print("WIFI")

        if wifi["available"]:
            print(f"  Active     : {wifi['active']}")

            print(f"  Connected  : {wifi['connected']}")

            if wifi["connected"]:
                print(f"  IP         : {wifi['ip']}")

                print(f"  RSSI       : {wifi['rssi']} dBm")

        else:
            print("  Unavailable")

        # ---------------------------------------------------------
        # Application buffers
        # ---------------------------------------------------------

        print()
        print("APPLICATION BUFFERS")

        for name, info in data["buffers"].items():
            if name == "_total":
                continue

            print(
                f"  {name:16s} "
                f"{info['used']:5d}/"
                f"{info['size']:<5d} B "
                f"{info['used_percent']:5.1f}%"
            )

            print(
                f"  {'':16s} "
                f"peak={info['peak_used']:<6d} "
                f"overflow={info['overflow_count']}"
            )

        # ---------------------------------------------------------
        # Sockets
        # ---------------------------------------------------------

        print()
        print(f"SOCKETS      : {data['sockets']['count']}")

        # ---------------------------------------------------------
        # Main loop
        # ---------------------------------------------------------

        print()
        print("MAIN LOOP")

        print(f"  Iterations : {loop['iterations']}")

        print(f"  Min        : {loop['min_ms']} ms")

        print(f"  Max        : {loop['max_ms']} ms")

        print(f"  Average    : {loop['average_ms']:.2f} ms")

        # ---------------------------------------------------------
        # Counters
        # ---------------------------------------------------------

        print()
        print("NON-ZERO COUNTERS")

        found_counter = False

        for name, value in data["counters"].items():
            if value != 0:
                found_counter = True

                print(f"  {name:24s}: {value}")

        if not found_counter:
            print("  None")

        # ---------------------------------------------------------
        # Reset
        # ---------------------------------------------------------

        print()
        print(f"RESET        : {reset['name']} ({reset['code']})")

        print("=" * 64)
        print()


# =================================================================
# EXAMPLE
# =================================================================

if __name__ == "__main__":
    monitor = ESP32SystemMonitor(
        enable_wifi=True,
        watchdog_timeout_ms=None,
        auto_gc=True,
    )

    monitor.register_buffer(
        "uart_rx",
        4096,
        "uart",
    )

    monitor.register_buffer(
        "mqtt_rx",
        2048,
        "mqtt",
    )

    while True:
        # Call once per application-loop iteration.
        monitor.loop_tick()

        # Example:
        #
        # monitor.update_buffer(
        #     "uart_rx",
        #     uart_rx_used,
        # )
        #
        # monitor.update_buffer(
        #     "mqtt_rx",
        #     mqtt_rx_used,
        # )

        # Feed the watchdog only when the main application loop
        # is known to be healthy.
        monitor.feed_watchdog()

        # Example telemetry:
        #
        # print(monitor.json())

        time.sleep_ms(100)
