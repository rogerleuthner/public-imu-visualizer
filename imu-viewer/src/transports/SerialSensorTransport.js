// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import { SensorTransport, normalizeSensorMessage } from "./SensorTransport";

/**
 * USB/Web Serial transport.
 *
 * Receives newline-delimited JSON from the ESP32.
 *
 * Example:
 *
 * {"seq":123,"t":12345,"ax":0.01,...}
 */
export class SerialSensorTransport extends SensorTransport {
  constructor(options = {}) {
    super();

    this.baudRate = options.baudRate || 115200;

    this.port = null;
    this.reader = null;

    this.readLoopRunning = false;

    this.buffer = "";
  }

  /**
   * Ask the browser to select a serial port and connect.
   *
   * No host arg; there is a serial or there isn't.
   */
  async connect() {
    if (!("serial" in navigator)) {
      throw new Error(
        "Web Serial is not supported by this browser. " + "Use Chrome or Edge.",
      );
    }

    if (this.connected) {
      return;
    }

    try {
      /*
       * Browser displays the serial-port chooser.
       */

      this.port = await navigator.serial.requestPort();

      await this.port.open({
        baudRate: this.baudRate,
      });

      this.setConnected(true);

      /*
       * Convert Uint8Array data from serial into text.
       */

      const decoder = new TextDecoderStream();

      this.port.readable.pipeTo(decoder.writable);

      this.reader = decoder.readable.getReader();

      this.readLoopRunning = true;

      this.buffer = "";

      /*
       * Start receiving JSON lines.
       *
       * connect() does NOT wait for the entire
       * read loop to finish.
       */

      this.readLoop();
    } catch (error) {
      this.setConnected(false);

      this.emitError(error);

      throw error;
    }
  }

  /**
   * Main serial receive loop.
   */
  async readLoop() {
    try {
      while (this.readLoopRunning && this.reader) {
        const { value, done } = await this.reader.read();

        if (done) {
          break;
        }

        if (!value) {
          continue;
        }

        this.buffer += value;

        /*
         * ESP32 sends CR/LF terminated JSON.
         *
         * Splitting on \n handles both:
         *
         * \n
         * \r\n
         */

        const lines = this.buffer.split("\n");

        /*
         * Last item may be an incomplete line.
         */

        this.buffer = lines.pop() || "";

        for (const line of lines) {
          this.processLine(line);
        }
      }
    } catch (error) {
      /*
       * Cancellation during normal disconnect isn't
       * really an error.
       */

      if (this.readLoopRunning) {
        this.emitError(error);
      }
    } finally {
      this.readLoopRunning = false;
    }
  }

  /**
   * Process one line received from ESP32.
   */
  processLine(line) {
    const text = line.trim();

    if (!text) {
      return;
    }

    /*
     * MicroPython can print diagnostic messages such as:
     *
     * Initializing MPU-6050...
     *
     * Those aren't JSON, so simply ignore them.
     */

    if (!text.startsWith("{") || !text.endsWith("}")) {
      return;
    }

    try {
      const data = JSON.parse(text);

      const message = normalizeSensorMessage(data);

      this.emitData(message);
    } catch (error) {
      /*
       * Don't kill the serial connection because
       * one malformed line appeared.
       */

      console.warn("Ignoring invalid sensor packet:", text);
    }
  }

  /**
   * Disconnect.
   */
  async disconnect() {
    this.readLoopRunning = false;

    try {
      if (this.reader) {
        try {
          await this.reader.cancel();
        } catch {
          // Reader may already be closed.
        }

        this.reader = null;
      }

      if (this.port) {
        try {
          await this.port.close();
        } catch {
          // Port may already be closed.
        }

        this.port = null;
      }
    } finally {
      this.buffer = "";

      this.setConnected(false);
    }
  }

  /**
   * Release everything.
   */
  dispose() {
    /*
     * Don't make dispose() itself async.
     * Fire-and-forget disconnect is sufficient here.
     */

    if (this.connected) {
      this.disconnect().catch(console.error);
    }

    super.dispose();
  }
}
