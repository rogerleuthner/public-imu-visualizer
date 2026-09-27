# Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import gc
import json
import os
import socket
import time

import network

# ================================================================
# NON-BLOCKING SOCKET ERROR HELPER
#
# On a non-blocking socket, "the send/receive buffer isn't ready
# right now" is a NORMAL, EXPECTED condition -- not a dead
# connection. MicroPython's socket implementation (esp32/lwIP,
# rp2, unix) signals this by raising OSError with errno 11
# (EAGAIN / EWOULDBLOCK), rather than returning None the way some
# other stream objects do.
#
# Treating every OSError as a fatal, connection-ending error (as
# this file previously did on every write() call) means the
# connection gets torn down every time the TCP send buffer
# momentarily fills -- which happens routinely while streaming a
# multi-hundred-KB bundle in small chunks, especially over WiFi.
# That produces exactly the symptoms of stalled/failed loads and
# the server being unreachable while a half-torn-down connection
# is still occupying the single HTTP client slot.
#
# EAGAIN/EWOULDBLOCK is 11 on every lwIP-based and POSIX-like
# MicroPython port. Checking against the literal avoids depending
# on the `errno` module being frozen into a minimal build.
# ================================================================

_EAGAIN = 11
_EWOULDBLOCK = 11


def _would_block(exc):

    try:
        return exc.args[0] in (_EAGAIN, _EWOULDBLOCK)

    except (IndexError, AttributeError):
        return False


class IMUServer:
    PORT = 80
    WEB_ROOT = "/www"

    CONFIG_FILE = "/wifi_config.json"

    DEFAULT_MODE = "AUTO"

    DEFAULT_IMU_RATE_HZ = 50
    MIN_IMU_RATE_HZ = 4
    MAX_IMU_RATE_HZ = 1000

    DEFAULT_EVENT_RATE_HZ = 5
    MIN_EVENT_RATE_HZ = 1
    MAX_EVENT_RATE_HZ = 100

    DEFAULT_AP_SSID = "ESP32-IMU"
    DEFAULT_AP_PASSWORD = "YOUR_AP_PASSWORD"
    DEFAULT_AP_CHANNEL = 6

    DEFAULT_WIFI_SSID = "REMOVED"
    DEFAULT_WIFI_PASSWORD = "REMOVED"

    WIFI_TIMEOUT_MS = 15000

    # --------------------------------------------------------
    # HTTP limits
    # --------------------------------------------------------

    REQUEST_BUFFER_SIZE = 4096
    FILE_CHUNK_SIZE = 2048
    RESPONSE_BUFFER_SIZE = 4096

    # A client which starts a request and then disappears
    # should not be allowed to hold the HTTP server forever.
    REQUEST_TIMEOUT_MS = 5000

    # --------------------------------------------------------
    # Garbage collection
    # --------------------------------------------------------

    GC_INTERVAL_MS = 2000

    def __init__(self):

        # ====================================================
        # CONFIGURATION
        # ====================================================

        self.config = self.load_config()

        self.ap_ssid = self.config.get("ap_ssid", self.DEFAULT_AP_SSID)

        self.ap_password = self.config.get("ap_password", self.DEFAULT_AP_PASSWORD)

        self.ap_channel = self.config.get("ap_channel", self.DEFAULT_AP_CHANNEL)

        # ====================================================
        # WIFI
        # ====================================================

        self.ap = None
        self.sta = None

        # ====================================================
        # HTTP LISTENER
        # ====================================================

        self.server = None

        # ====================================================
        # HTTP CLIENT
        #
        # There is deliberately only ONE active ordinary HTTP
        # client at a time.
        #
        # This is intentional for this application.
        # ====================================================

        self.http_client = None
        self.http_addr = None

        self.http_state = None

        self.http_request = bytearray(self.REQUEST_BUFFER_SIZE)

        self.http_request_len = 0

        self.http_content_length = 0

        self.http_body_start = 0

        self.http_request_started_ms = 0

        self.http_pending = None
        self.http_pending_offset = 0

        self.http_file = None
        self.http_file_path = None
        self.http_file_size = 0
        self.http_file_sent = 0

        # ====================================================
        # SSE
        # ====================================================

        self.client = None
        self.sse = False

        self.sse_pending = None
        self.sse_pending_offset = 0

        # ====================================================
        # NETWORK CHANGE
        # ====================================================

        self.pending_config = None

        # ====================================================
        # STATUS
        # ====================================================

        self.last_network_result = "BOOT"

        # ====================================================
        # GC
        # ====================================================

        self.last_gc_ms = time.ticks_ms()

    # ========================================================
    # GARBAGE COLLECTION
    # ========================================================

    def service_gc(self):

        now = time.ticks_ms()

        if time.ticks_diff(now, self.last_gc_ms) >= self.GC_INTERVAL_MS:
            gc.collect()

            self.last_gc_ms = now

    # ========================================================
    # CONFIGURATION FILE
    # ========================================================

    def load_config(self):

        defaults = {
            "mode": self.DEFAULT_MODE,
            "ssid": self.DEFAULT_WIFI_SSID,
            "password": self.DEFAULT_WIFI_PASSWORD,
            "ap_ssid": self.DEFAULT_AP_SSID,
            "ap_password": self.DEFAULT_AP_PASSWORD,
            "ap_channel": self.DEFAULT_AP_CHANNEL,
            "imu_rate_hz": self.DEFAULT_IMU_RATE_HZ,
            "event_rate_hz": self.DEFAULT_EVENT_RATE_HZ,
        }

        try:
            with open(self.CONFIG_FILE, "r") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return defaults

            for key in defaults:
                if key not in data:
                    data[key] = defaults[key]

            return data

        except Exception:
            print("No WiFi config file; using defaults.")

            return defaults

    def save_config(self, config):

        try:
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(config, f)

            print("WiFi configuration saved.")

            return True

        except Exception as e:
            print("Could not save WiFi configuration:", e)

            return False

    # ========================================================
    # WIFI STARTUP
    # ========================================================

    def start_wifi(self):

        mode = self.config.get("mode", self.DEFAULT_MODE)

        print("Configured network mode:", mode)

        if mode == "AP":
            self.start_ap()

            self.last_network_result = "AP"

            return

        if mode == "STA":
            if self.start_sta():
                self.last_network_result = "STA"

                return

            print("STA failed at boot.")

            print("Falling back to AP.")

            self.start_ap()

            self.last_network_result = "STA_FAILED_AP_FALLBACK"

            return

        if mode == "AUTO":
            self.start_ap()

            print("AUTO: AP is available at", self.ip)

            if self.start_sta():
                print("AUTO: STA connection successful.")

                print("AUTO: Switching to STA-only mode.")

                self.stop_ap()

                self.last_network_result = "AUTO_STA"

                print("AUTO: STA active at", self.ip)

                return

            print("AUTO: STA connection failed.")

            print("AUTO: Keeping AP active.")

            self.stop_sta()

            self.last_network_result = "AUTO_AP_FALLBACK"

            print("AUTO: AP-only mode active at", self.ip)

            return

        print("Invalid saved network mode:", mode)

        print("Using AP.")

        self.start_ap()

        self.last_network_result = "INVALID_MODE_AP_FALLBACK"

    # ========================================================
    # ACCESS POINT
    # ========================================================

    def start_ap(self):

        print("Starting WiFi AP...")

        if self.ap is not None:
            try:
                self.ap.active(False)

            except Exception:
                pass

            self.ap = None

            time.sleep_ms(200)

        self.ap = network.WLAN(network.WLAN.IF_AP)

        try:
            self.ap.active(False)

        except Exception:
            pass

        time.sleep_ms(200)

        # ----------------------------------------------------
        # Defensive validation.
        #
        # network.WLAN.config() is a C-level call that expects
        # ssid/password to be actual strings. If a bad value
        # ever ends up in self.ap_ssid/self.ap_password (e.g.
        # a stale/corrupted entry in wifi_config.json written
        # before validation existed), this call fails with a
        # low-level TypeError that has no useful line number
        # and takes down the whole poll() cycle. Catch it here
        # instead, where we can fall back to a safe default.
        # ----------------------------------------------------

        ap_ssid = self.ap_ssid
        ap_password = self.ap_password

        if not isinstance(ap_ssid, str):
            print("ap_ssid was not a string, using default:", repr(ap_ssid))

            ap_ssid = self.DEFAULT_AP_SSID

        if not isinstance(ap_password, str):
            print("ap_password was not a string, using default:", repr(ap_password))

            ap_password = self.DEFAULT_AP_PASSWORD

        self.ap.config(
            ssid=ap_ssid,
            password=ap_password,
            channel=self.ap_channel,
            authmode=network.AUTH_WPA2_PSK,
        )

        self.ap.ifconfig(("10.0.0.1", "255.255.255.0", "10.0.0.1", "10.0.0.1"))

        self.ap.active(True)

        _ap_wait_start = time.ticks_ms()

        while not self.ap.active():
            if time.ticks_diff(time.ticks_ms(), _ap_wait_start) > 3000:
                # Previously this loop had no timeout at all and
                # could block the entire device forever if the AP
                # interface was ever slow to report active. Bail
                # out and let the caller continue rather than
                # freezing main.py's whole loop permanently.
                print("WiFi AP activation timed out.")

                break

            time.sleep_ms(100)

        print("WiFi AP active")

        print("SSID:", self.ap_ssid)

        print("IP:", self.ap.ifconfig()[0])

    # ========================================================
    # STOP AP
    # ========================================================

    def stop_ap(self):

        print("Stopping WiFi AP...")

        if self.ap is None:
            return

        try:
            self.ap.active(False)

        except Exception as e:
            print("AP shutdown error:", e)

        self.ap = None

        time.sleep_ms(300)

        print("WiFi AP stopped.")

    # ========================================================
    # STA
    # ========================================================

    def start_sta(self):

        ssid = self.config.get("ssid", "")

        password = self.config.get("password", "")

        if not ssid:
            print("No STA SSID configured.")

            return False

        # ----------------------------------------------------
        # Defensive validation -- see the matching comment in
        # start_ap(). A non-string ssid/password reaching
        # sta.connect() raises a low-level TypeError with no
        # useful traceback; catch it here instead.
        # ----------------------------------------------------

        if not isinstance(ssid, str):
            print("Stored ssid was not a string, aborting STA connect:", repr(ssid))

            return False

        if not isinstance(password, str):
            print(
                "Stored password was not a string, treating as empty:", repr(password)
            )

            password = ""

        print("Starting WiFi STA...")

        if self.sta is not None:
            try:
                self.sta.active(False)

            except Exception:
                pass

            self.sta = None

            time.sleep_ms(200)

        self.sta = network.WLAN(network.WLAN.IF_STA)

        try:
            self.sta.active(False)

        except Exception:
            pass

        time.sleep_ms(100)

        self.sta.active(True)

        try:
            self.sta.config(reconnects=0)

        except Exception as e:
            print("Could not configure reconnects:", e)

        if self.sta.isconnected():
            print("WiFi STA already connected.")

            print("IP:", self.sta.ifconfig()[0])

            return True

        print("Connecting to:", ssid)

        try:
            self.sta.connect(ssid, password)

        except OSError as e:
            print("WiFi connect error:", e)

            self.stop_sta()

            return False

        start_time = time.ticks_ms()

        last_status = None

        while not self.sta.isconnected():
            elapsed = time.ticks_diff(time.ticks_ms(), start_time)

            try:
                status = self.sta.status()

            except Exception:
                status = None

            if status != last_status:
                print("WiFi status:", self.status_name(status))

                last_status = status

            if elapsed >= self.WIFI_TIMEOUT_MS:
                print("WiFi connection timeout.")

                self.stop_sta()

                return False

            time.sleep_ms(100)

        print("WiFi STA connected.")

        print("SSID:", ssid)

        print("IP:", self.sta.ifconfig()[0])

        try:
            config = self.sta.ifconfig()

            print("Netmask:", config[1])

            print("Gateway:", config[2])

            print("DNS:", config[3])

        except Exception:
            pass

        return True

    # ========================================================
    # STOP STA
    # ========================================================

    def stop_sta(self):

        print("Stopping WiFi STA...")

        if self.sta is None:
            return

        try:
            self.sta.disconnect()

        except Exception:
            pass

        try:
            self.sta.active(False)

        except Exception:
            pass

        self.sta = None

        time.sleep_ms(500)

        print("WiFi STA stopped.")

    # ========================================================
    # WIFI STATUS NAME
    # ========================================================

    def status_name(self, status):

        if status is None:
            return "UNKNOWN"

        try:
            if status == network.STAT_IDLE:
                return "IDLE"

        except AttributeError:
            pass

        try:
            if status == network.STAT_CONNECTING:
                return "CONNECTING"

        except AttributeError:
            pass

        try:
            if status == network.STAT_WRONG_PASSWORD:
                return "WRONG_PASSWORD"

        except AttributeError:
            pass

        try:
            if status == network.STAT_NO_AP_FOUND:
                return "NO_AP_FOUND"

        except AttributeError:
            pass

        try:
            if status == network.STAT_CONNECT_FAIL:
                return "CONNECT_FAIL"

        except AttributeError:
            pass

        try:
            if status == network.STAT_GOT_IP:
                return "GOT_IP"

        except AttributeError:
            pass

        return str(status)

    # ========================================================
    # NETWORK MODE
    # ========================================================

    def current_mode(self):

        sta_connected = False
        ap_active = False

        if self.sta is not None:
            try:
                sta_connected = self.sta.isconnected()

            except Exception:
                pass

        if self.ap is not None:
            try:
                ap_active = self.ap.active()

            except Exception:
                pass

        if sta_connected:
            return "STA"

        if ap_active:
            return "AP"

        return "NONE"

    # ========================================================
    # IP
    # ========================================================

    @property
    def ip(self):

        if self.sta is not None:
            try:
                if self.sta.isconnected():
                    return self.sta.ifconfig()[0]

            except Exception:
                pass

        if self.ap is not None:
            try:
                if self.ap.active():
                    return self.ap.ifconfig()[0]

            except Exception:
                pass

        return "0.0.0.0"

    # ========================================================
    # SERVER
    # ========================================================

    def start_server(self):

        self.close_http_client()

        self.disconnect()

        if self.server is not None:
            self.stop_server()

        addr = socket.getaddrinfo("0.0.0.0", self.PORT)[0][-1]

        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.server.bind(addr)

        self.server.listen(2)

        self.server.setblocking(False)

        print(f"HTTP server ready at http://{self.ip}/")

    # ========================================================
    # STOP SERVER
    # ========================================================

    def stop_server(self):

        self.close_http_client()

        self.disconnect()

        if self.server is None:
            return

        try:
            self.server.close()

        except Exception:
            pass

        self.server = None

        time.sleep_ms(200)

    # ========================================================
    # RESTART SERVER
    # ========================================================

    def restart_server(self):

        self.stop_server()

        time.sleep_ms(300)

        self.start_server()

    # ========================================================
    # CLOSE HTTP CLIENT
    # ========================================================

    def close_http_client(self):

        f = self.http_file

        self.http_file = None

        if f is not None:
            try:
                f.close()

            except Exception:
                pass

        client = self.http_client

        self.http_client = None

        self.http_addr = None
        self.http_state = None

        self.http_request_len = 0
        self.http_content_length = 0
        self.http_body_start = 0
        self.http_request_started_ms = 0

        self.http_pending = None
        self.http_pending_offset = 0

        self.http_file_path = None
        self.http_file_size = 0
        self.http_file_sent = 0

        if client is not None:
            try:
                client.close()

            except Exception:
                pass

    # ========================================================
    # SERVICE HTTP CLIENT
    # ========================================================

    def service_http_client(self):

        client = self.http_client

        if client is None:
            return

        # ----------------------------------------------------
        # Request phase.
        # ----------------------------------------------------

        if self.http_state == "request":
            self.read_http_request()

            if self.http_client is None:
                return

            # ------------------------------------------------
            # read_http_request() may have already dispatched
            # the request and moved http_state on to
            # "response" or "file". Only apply the
            # incomplete-request timeout if we are still
            # actually waiting on the request -- otherwise a
            # slow-arriving request whose final byte just
            # barely completed past the timeout would have its
            # freshly-queued response discarded here before a
            # single byte of it is ever sent.
            # ------------------------------------------------

            if self.http_state != "request":
                return

            # Timeout incomplete request.
            if (
                time.ticks_diff(time.ticks_ms(), self.http_request_started_ms)
                > self.REQUEST_TIMEOUT_MS
            ):
                print("HTTP request timeout")

                self.close_http_client()

            return

        # ----------------------------------------------------
        # Response / file phase.
        # ----------------------------------------------------

        if self.http_state == "response":
            self.service_http_response()

            return

        if self.http_state == "file":
            self.service_http_file()

            return

        self.close_http_client()

    # ========================================================
    # READ HTTP REQUEST
    # ========================================================

    def read_http_request(self):

        client = self.http_client

        if client is None:
            return

        try:
            chunk = client.recv(1024)

        except OSError as e:
            if _would_block(e):
                # No data available yet -- normal, keep
                # waiting (bounded by REQUEST_TIMEOUT_MS).
                return

            # A genuinely dead connection (e.g. ECONNRESET).
            # Free the single HTTP client slot immediately
            # rather than holding it for the full timeout.
            self.close_http_client()

            return

        if not chunk:
            self.close_http_client()

            return

        available = self.REQUEST_BUFFER_SIZE - self.http_request_len

        if len(chunk) > available:
            print("HTTP request too large")

            self.begin_error_response(413, "Request Too Large")

            return

        self.http_request[
            self.http_request_len : self.http_request_len + len(chunk)
        ] = chunk

        self.http_request_len += len(chunk)

        data = self.http_request[: self.http_request_len]

        header_end = data.find(b"\r\n\r\n")

        if header_end < 0:
            return

        # ----------------------------------------------------
        # Parse headers.
        # ----------------------------------------------------

        try:
            header_text = bytes(data[:header_end]).decode("utf-8", "ignore")

        except Exception:
            self.begin_error_response(400, "Bad Request")

            return

        content_length = 0

        for line in header_text.split("\r\n"):
            lower = line.lower()

            if lower.startswith("content-length:"):
                try:
                    content_length = int(line.split(":", 1)[1].strip())

                except Exception:
                    content_length = 0

        body_start = header_end + 4

        body_received = self.http_request_len - body_start

        if content_length > (self.REQUEST_BUFFER_SIZE - body_start):
            self.begin_error_response(413, "Request Too Large")

            return

        if body_received < content_length:
            self.http_content_length = content_length
            self.http_body_start = body_start

            return

        self.http_content_length = content_length
        self.http_body_start = body_start

        self.dispatch_http_request(header_text)

    # ========================================================
    # DISPATCH HTTP REQUEST
    # ========================================================

    def dispatch_http_request(self, header_text):

        data = self.http_request[: self.http_request_len]

        try:
            first_line_end = data.find(b"\r\n")

            first_line = bytes(data[:first_line_end]).decode("utf-8", "ignore")

        except Exception:
            self.begin_error_response(400, "Bad Request")

            return

        print("HTTP:", first_line)

        # ====================================================
        # OPTIONS
        # ====================================================

        if first_line.startswith("OPTIONS /api/"):
            self.begin_cors_options()

            return

        # ====================================================
        # STATUS
        # ====================================================

        if first_line == "GET /api/status HTTP/1.1":
            self.begin_json_response(self.get_status())

            return

        # ====================================================
        # CONFIG
        # ====================================================

        if first_line == "GET /api/config HTTP/1.1":
            self.begin_json_response(self.get_public_config())

            return

        # ====================================================
        # CONFIG POST
        # ====================================================

        if first_line.startswith("POST /api/config "):
            body_start = self.http_body_start
            body_end = body_start + self.http_content_length

            try:
                body_text = bytes(data[body_start:body_end]).decode("utf-8", "ignore")

            except Exception:
                self.begin_error_response(400, "Bad Request")

                return

            self.handle_config_post(body_text)

            return

        # ====================================================
        # SSE
        # ====================================================

        if first_line.startswith("GET /events"):
            self.start_sse_from_http_client()

            return

        # ====================================================
        # STATIC
        # ====================================================

        if first_line.startswith("GET "):
            self.begin_static_response(first_line)

            return

        self.begin_error_response(405, "Method Not Allowed")

    # ========================================================
    # QUEUE RESPONSE
    # ========================================================

    def begin_response(self, response):

        if self.http_client is None:
            return

        self.http_pending = response
        self.http_pending_offset = 0
        self.http_state = "response"

    # ========================================================
    # SERVICE RESPONSE
    # ========================================================

    def service_http_response(self):

        client = self.http_client

        if client is None:
            return

        pending = self.http_pending

        if pending is None:
            self.close_http_client()

            return

        offset = self.http_pending_offset

        try:
            written = client.write(pending[offset:])

        except OSError as e:
            if _would_block(e):
                # Send buffer is momentarily full.
                # Try again on the next poll().
                return

            print("HTTP response write failed:", e)

            self.close_http_client()

            return

        except Exception as e:
            print("HTTP response write failed:", e)

            self.close_http_client()

            return

        if written is None:
            return

        if written <= 0:
            return

        self.http_pending_offset += written

        if self.http_pending_offset >= len(pending):
            self.http_pending = None
            self.http_pending_offset = 0

            self.close_http_client()

    # ========================================================
    # JSON RESPONSE
    # ========================================================

    def begin_json_response(self, data, status="200 OK"):

        try:
            body = json.dumps(data).encode("utf-8")

        except Exception:
            self.begin_error_response(500, "Internal Server Error")

            return

        response = (
            f"HTTP/1.1 {status}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "Cache-Control: no-cache\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "\r\n"
        ).encode() + body

        self.begin_response(response)

    # ========================================================
    # CORS
    # ========================================================

    def begin_cors_options(self):

        response = (
            b"HTTP/1.1 204 No Content\r\n"
            b"Access-Control-Allow-Origin: *\r\n"
            b"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            b"Access-Control-Allow-Headers: Content-Type\r\n"
            b"Access-Control-Max-Age: 600\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n"
            b"\r\n"
        )

        self.begin_response(response)

    # ========================================================
    # STATIC FILE RESPONSE
    # ========================================================

    def begin_static_response(self, request_line):

        try:
            parts = request_line.split(" ")

            if len(parts) < 2:
                self.begin_error_response(400, "Bad Request")

                return

            path = parts[1]

            if "?" in path:
                path = path.split("?", 1)[0]

            if path == "/":
                path = "/index.html"

            if path == "/settings":
                path = "/settings.html"

            if ".." in path:
                self.begin_error_response(400, "Bad Request")

                return

            file_path = self.WEB_ROOT + path

            print("Serving:", file_path)

            stat = os.stat(file_path)

            file_size = stat[6]

            content_type = self.get_content_type(file_path)

            f = open(file_path, "rb")

        except OSError:
            self.begin_error_response(404, "Not Found")

            return

        except Exception:
            self.begin_error_response(400, "Bad Request")

            return

        self.http_file = f
        self.http_file_path = file_path
        self.http_file_size = file_size
        self.http_file_sent = 0

        headers = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {file_size}\r\n"
            "Connection: close\r\n"
            "Cache-Control: no-cache\r\n"
            "\r\n"
        ).encode()

        self.http_pending = headers
        self.http_pending_offset = 0
        self.http_state = "file"

    # ========================================================
    # SERVICE STATIC FILE
    #
    # IMPORTANT:
    #
    # Only ONE socket write is attempted per poll().
    #
    # Only ONE 2048-byte file chunk is ever resident here.
    # ========================================================

    def service_http_file(self):

        client = self.http_client

        if client is None:
            return

        # ----------------------------------------------------
        # Header still pending.
        # ----------------------------------------------------

        if self.http_pending is not None:
            pending = self.http_pending
            offset = self.http_pending_offset

            try:
                written = client.write(pending[offset:])

            except OSError as e:
                if _would_block(e):
                    return

                print("HTTP file header write failed:", e)

                self.close_http_client()

                return

            except Exception as e:
                print("HTTP file header write failed:", e)

                self.close_http_client()

                return

            if written is None:
                return

            if written <= 0:
                return

            self.http_pending_offset += written

            if self.http_pending_offset < len(pending):
                return

            self.http_pending = None
            self.http_pending_offset = 0

            return

        # ----------------------------------------------------
        # If the entire file has been transmitted, close.
        # ----------------------------------------------------

        if self.http_file_sent >= self.http_file_size:
            print(f"Sent {self.http_file_sent} bytes")

            self.close_http_client()

            return

        # ----------------------------------------------------
        # Read ONE small chunk.
        # ----------------------------------------------------

        try:
            chunk = self.http_file.read(self.FILE_CHUNK_SIZE)

        except Exception:
            self.close_http_client()

            return

        if not chunk:
            print(
                f"File ended after {self.http_file_sent} of {self.http_file_size} bytes"
            )

            self.close_http_client()

            return

        # ----------------------------------------------------
        # Keep the chunk until it has actually been written.
        # ----------------------------------------------------

        self.http_pending = chunk
        self.http_pending_offset = 0

        # ----------------------------------------------------
        # Attempt ONE write now.
        # ----------------------------------------------------

        try:
            written = client.write(chunk)

        except OSError as e:
            if _would_block(e):
                # Send buffer is momentarily full. The chunk
                # is still held in self.http_pending/offset=0
                # and will be retried on the next poll() --
                # this is the normal, expected case while
                # streaming a large file over a non-blocking
                # socket, not a dead connection.
                return

            print("HTTP file chunk write failed:", e)

            self.close_http_client()

            return

        except Exception as e:
            print("HTTP file chunk write failed:", e)

            self.close_http_client()

            return

        if written is None:
            return

        if written <= 0:
            return

        self.http_pending_offset = written

        if written >= len(chunk):
            self.http_file_sent += len(chunk)

            self.http_pending = None
            self.http_pending_offset = 0

        else:
            # Partial non-blocking write.
            #
            # The same chunk remains referenced by
            # self.http_pending and will be continued on
            # the next poll().
            pass

    # ========================================================
    # ERROR RESPONSE
    # ========================================================

    def begin_error_response(self, status, message):

        body = (
            f"<!DOCTYPE html><html><body><h1>{status} {message}</h1></body></html>"
        ).encode()

        response = (
            f"HTTP/1.1 {status} {message}\r\n"
            "Content-Type: text/html\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode() + body

        self.begin_response(response)

    # ========================================================
    # PUBLIC CONFIG
    # ========================================================

    def get_public_config(self):

        return {
            "mode": self.config.get("mode", self.DEFAULT_MODE),
            "ssid": self.config.get("ssid", ""),
            "password_set": bool(self.config.get("password", "")),
            "ap_ssid": self.ap_ssid,
            "imu_rate_hz": self.config.get("imu_rate_hz", self.DEFAULT_IMU_RATE_HZ),
            "event_rate_hz": self.config.get(
                "event_rate_hz", self.DEFAULT_EVENT_RATE_HZ
            ),
        }

    # ========================================================
    # STATUS
    # ========================================================

    def get_status(self):

        status = {
            "configured_mode": self.config.get("mode", self.DEFAULT_MODE),
            "current_mode": self.current_mode(),
            "ip": self.ip,
            "result": self.last_network_result,
            "sta_connected": False,
            "sta_ssid": "",
            "sta_ip": "",
            "ap_active": False,
            "ap_ssid": self.ap_ssid,
            "ap_ip": "",
        }

        if self.sta is not None:
            try:
                status["sta_connected"] = self.sta.isconnected()

            except Exception:
                pass

            status["sta_ssid"] = self.config.get("ssid", "")

            try:
                if self.sta.isconnected():
                    status["sta_ip"] = self.sta.ifconfig()[0]

            except Exception:
                pass

        if self.ap is not None:
            try:
                status["ap_active"] = self.ap.active()

            except Exception:
                pass

            try:
                if self.ap.active():
                    status["ap_ip"] = self.ap.ifconfig()[0]

            except Exception:
                pass

        return status

    # ========================================================
    # CONFIG POST
    # ========================================================

    def handle_config_post(self, body_text):

        try:
            requested = json.loads(body_text)

        except Exception:
            self.begin_error_response(400, "Invalid JSON")

            return

        mode = requested.get("mode", "")

        if mode not in ("AUTO", "AP", "STA"):
            self.begin_error_response(400, "Mode must be AUTO, AP, or STA")

            return

        new_config = dict(self.config)

        new_config["mode"] = mode

        # ----------------------------------------------------
        # SSID
        # ----------------------------------------------------

        if "ssid" in requested:
            ssid = requested["ssid"]

            if not isinstance(ssid, str):
                self.begin_error_response(400, "SSID must be text")

                return

            new_config["ssid"] = ssid.strip()

        # ----------------------------------------------------
        # Password
        # ----------------------------------------------------

        if "password" in requested:
            password = requested["password"]

            if not isinstance(password, str):
                self.begin_error_response(400, "Password must be text")

                return

            if password != "":
                new_config["password"] = password

        # ----------------------------------------------------
        # IMU rate
        # ----------------------------------------------------

        if "imu_rate_hz" in requested:
            try:
                imu_rate_hz = int(requested["imu_rate_hz"])

            except Exception:
                self.begin_error_response(400, "IMU data rate must be an integer")

                return

            if imu_rate_hz < self.MIN_IMU_RATE_HZ or imu_rate_hz > self.MAX_IMU_RATE_HZ:
                self.begin_error_response(
                    400,
                    f"IMU data rate must be between {self.MIN_IMU_RATE_HZ} and {self.MAX_IMU_RATE_HZ} Hz",
                )

                return

            new_config["imu_rate_hz"] = imu_rate_hz

        # ----------------------------------------------------
        # Event rate
        # ----------------------------------------------------

        if "event_rate_hz" in requested:
            try:
                event_rate_hz = int(requested["event_rate_hz"])

            except Exception:
                self.begin_error_response(400, "Event data rate must be an integer")

                return

            if (
                event_rate_hz < self.MIN_EVENT_RATE_HZ
                or event_rate_hz > self.MAX_EVENT_RATE_HZ
            ):
                self.begin_error_response(
                    400,
                    f"Event data rate must be between {self.MIN_EVENT_RATE_HZ} and {self.MAX_EVENT_RATE_HZ} Hz",
                )

                return

            new_config["event_rate_hz"] = event_rate_hz

        # ----------------------------------------------------
        # Determine network change BEFORE replacing config.
        # ----------------------------------------------------

        network_changed = (
            new_config.get("mode") != self.config.get("mode")
            or new_config.get("ssid") != self.config.get("ssid")
            or new_config.get("password") != self.config.get("password")
        )

        # ----------------------------------------------------
        # Save
        # ----------------------------------------------------

        if not self.save_config(new_config):
            self.begin_error_response(500, "Could not save configuration")

            return

        # ----------------------------------------------------
        # Update memory
        # ----------------------------------------------------

        self.config = new_config

        # ----------------------------------------------------
        # Queue network change.
        # ----------------------------------------------------

        if network_changed:
            self.pending_config = dict(new_config)

        response = {
            "ok": True,
            "applying": network_changed,
            "mode": mode,
            "message": (
                "Configuration saved. Network change is being applied."
                if network_changed
                else "Configuration saved."
            ),
        }

        self.begin_json_response(response)

    # ========================================================
    # APPLY PENDING CONFIG
    # ========================================================

    def apply_pending_config(self):

        if self.pending_config is None:
            return

        config = self.pending_config

        self.pending_config = None

        print()
        print("========================================")
        print("Applying network configuration...")
        print("Requested mode:", config.get("mode"))
        print("========================================")

        # ----------------------------------------------------
        # Kill SSE before changing interfaces.
        # ----------------------------------------------------

        self.disconnect()

        # ----------------------------------------------------
        # HTTP listener must be stopped before WiFi changes.
        # ----------------------------------------------------

        self.stop_server()

        self.stop_sta()
        self.stop_ap()

        time.sleep_ms(500)

        mode = config.get("mode", "AUTO")

        if mode == "AP":
            self.start_ap()

            self.last_network_result = "AP"

        elif mode == "STA":
            if self.start_sta():
                self.last_network_result = "STA"

            else:
                print("Requested STA failed.")

                print("Falling back to AP.")

                self.start_ap()

                self.last_network_result = "STA_FAILED_AP_FALLBACK"

        elif mode == "AUTO":
            self.start_ap()

            if self.start_sta():
                print("AUTO: STA succeeded.")

                self.stop_ap()

                self.last_network_result = "AUTO_STA"

            else:
                print("AUTO: STA failed.")

                self.stop_sta()

                self.last_network_result = "AUTO_AP_FALLBACK"

        time.sleep_ms(500)

        self.start_server()

        print("Network configuration applied.")

        print("Current mode:", self.current_mode())

        print("IP:", self.ip)

        print("========================================")
        print("")

    # ========================================================
    # SSE
    # ========================================================

    def start_sse_from_http_client(self):

        if self.http_client is None:
            return

        # ----------------------------------------------------
        # Only one SSE client.
        # ----------------------------------------------------

        if self.client is not None:
            self.disconnect()

        client = self.http_client

        self.http_client = None
        self.http_addr = None
        self.http_state = None

        self.http_pending = None
        self.http_pending_offset = 0

        self.http_file = None
        self.http_file_path = None

        headers = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/event-stream\r\n"
            b"Cache-Control: no-cache\r\n"
            b"Connection: keep-alive\r\n"
            b"Access-Control-Allow-Origin: *\r\n"
            b"\r\n"
            b": connected\n\n"
        )

        try:
            client.setblocking(False)

            self.client = client
            self.sse = True

            self.sse_pending = headers
            self.sse_pending_offset = 0

            print("SSE stream connected")

        except Exception as e:
            print("SSE connection failed:", e)

            try:
                client.close()

            except Exception:
                pass

    # ========================================================
    # SSE SEND
    # ========================================================

    def send(self, data):

        if self.client is None:
            return False

        if not self.sse:
            return False

        # ----------------------------------------------------
        # Do not queue unlimited SSE data.
        #
        # If the previous event has not drained, drop this
        # event rather than allowing RAM usage to grow.
        # ====================================================

        if self.sse_pending is not None:
            return False

        try:
            message = ("data: " + data + "\n\n").encode("utf-8")

        except Exception:
            return False

        self.sse_pending = message
        self.sse_pending_offset = 0

        # ----------------------------------------------------
        # Attempt one write immediately.
        # ----------------------------------------------------

        self.service_sse()

        return self.client is not None

    # ========================================================
    # SERVICE SSE
    #
    # Called from poll().
    # ========================================================

    def service_sse(self):

        if self.client is None:
            return

        pending = self.sse_pending

        if pending is None:
            return

        offset = self.sse_pending_offset

        try:
            written = self.client.write(pending[offset:])

        except OSError as e:
            if _would_block(e):
                # Send buffer is momentarily full. Leave
                # sse_pending in place; the next send() call
                # (or the next poll()) will retry the drain.
                return

            print("SSE send failed:", e)

            self.disconnect()

            return

        except Exception as e:
            print("SSE send failed:", e)

            self.disconnect()

            return

        if written is None:
            return

        if written <= 0:
            return

        self.sse_pending_offset += written

        if self.sse_pending_offset >= len(pending):
            self.sse_pending = None
            self.sse_pending_offset = 0

    # ========================================================
    # DISCONNECT SSE
    # ========================================================

    def disconnect(self):

        client = self.client

        self.client = None
        self.sse = False

        self.sse_pending = None
        self.sse_pending_offset = 0

        if client is not None:
            try:
                client.close()

            except Exception:
                pass

            print("SSE client disconnected")

    # ========================================================
    # POLL
    #
    # This is the only poll() in the class (a duplicate
    # definition used to exist further up and silently shadow
    # this one -- Python keeps only the last `def` with a given
    # name in a class body, so that earlier copy never actually
    # ran and has been removed).
    #
    # This function is deliberately bounded. It does NOT:
    #
    #   - send a complete file
    #   - loop until a socket is writable
    #   - block waiting for a client
    #
    # (apply_pending_config(), called below, is the one
    # exception to that -- it is fully synchronous and can
    # block for several seconds up to WIFI_TIMEOUT_MS during a
    # WiFi mode change.)
    # ========================================================

    def poll(self):

        if self.server is None:
            return

        self.service_gc()

        # ----------------------------------------------------
        # Always give SSE exactly one opportunity to drain.
        # ----------------------------------------------------

        self.service_sse()

        # ----------------------------------------------------
        # Network configuration changes have priority only
        # when no ordinary HTTP transaction exists.
        # ----------------------------------------------------

        if self.pending_config is not None and self.http_client is None:
            self.apply_pending_config()

            return

        # ----------------------------------------------------
        # Existing HTTP transaction.
        # ----------------------------------------------------

        if self.http_client is not None:
            self.service_http_client()

            return

        # ----------------------------------------------------
        # Accept one new client.
        # ----------------------------------------------------

        try:
            client, addr = self.server.accept()

        except OSError:
            return

        print("Client connected:", addr)

        try:
            client.setblocking(False)

        except Exception:
            try:
                client.close()

            except Exception:
                pass

            return

        self.http_client = client
        self.http_addr = addr
        self.http_state = "request"

        self.http_request_len = 0
        self.http_content_length = 0
        self.http_body_start = 0
        self.http_request_started_ms = time.ticks_ms()

        self.http_pending = None
        self.http_pending_offset = 0

        self.http_file = None
        self.http_file_path = None
        self.http_file_size = 0
        self.http_file_sent = 0

    # ========================================================
    # CONTENT TYPES
    # ========================================================

    def get_content_type(self, path):

        if path.endswith(".html"):
            return "text/html"

        if path.endswith(".js"):
            return "application/javascript"

        if path.endswith(".css"):
            return "text/css"

        if path.endswith(".svg"):
            return "image/svg+xml"

        if path.endswith(".json"):
            return "application/json"

        if path.endswith(".png"):
            return "image/png"

        if path.endswith((".jpg", ".jpeg")):
            return "image/jpeg"

        if path.endswith(".ico"):
            return "image/x-icon"

        if path.endswith(".woff"):
            return "font/woff"

        if path.endswith(".woff2"):
            return "font/woff2"

        if path.endswith(".ttf"):
            return "font/ttf"

        return "application/octet-stream"
