// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import { SensorTransport } from "./SensorTransport";
import { normalizeMessage } from "../MessageFormat";

export class WiFiSensorTransport extends SensorTransport {
  constructor() {
    super();

    this.eventSource = null;

    this.connected = false;

    this.dataListeners = [];
    this.statusListeners = [];
    this.errorListeners = [];
  }

  /*
   * ========================================================
   * DATA LISTENER
   * ========================================================
   */

  onData(callback) {
    this.dataListeners.push(callback);

    return () => {
      this.dataListeners = this.dataListeners.filter(
        (listener) => listener !== callback,
      );
    };
  }

  /*
   * ========================================================
   * STATUS LISTENER
   * ========================================================
   */

  onStatus(callback) {
    this.statusListeners.push(callback);

    return () => {
      this.statusListeners = this.statusListeners.filter(
        (listener) => listener !== callback,
      );
    };
  }

  /*
   * ========================================================
   * ERROR LISTENER
   * ========================================================
   */

  onError(callback) {
    this.errorListeners.push(callback);

    return () => {
      this.errorListeners = this.errorListeners.filter(
        (listener) => listener !== callback,
      );
    };
  }

  /*
   * ========================================================
   * EMIT DATA
   * ========================================================
   */

  emitData(data) {
    this.dataListeners.forEach((callback) => callback(data));
  }

  /*
   * ========================================================
   * EMIT STATUS
   * ========================================================
   */

  emitStatus(status) {
    this.statusListeners.forEach((callback) => callback(status));
  }

  /*
   * ========================================================
   * EMIT ERROR
   * ========================================================
   */

  emitError(error) {
    this.errorListeners.forEach((callback) => callback(error));
  }

  /*
   * ========================================================
   * CONNECT
   * ========================================================
   */

  connect() {
    const url = new URL(window.location.origin + "/events");

    console.log("Connecting to ESP32 SSE:", url);

    return new Promise((resolve, reject) => {
      /*
       * Close an existing connection first.
       */

      if (this.eventSource) {
        this.eventSource.close();

        this.eventSource = null;
      }

      let opened = false;

      const eventSource = new EventSource(url);

      this.eventSource = eventSource;

      /*
       * ----------------------------------------------
       * CONNECTED
       * ----------------------------------------------
       */

      eventSource.onopen = () => {
        opened = true;

        this.connected = true;

        console.log("ESP32 Wi-Fi connected");

        this.emitStatus(true);

        resolve();
      };

      /*
       * ----------------------------------------------
       * SENSOR DATA
       * ----------------------------------------------
       */

      eventSource.onmessage = (event) => {
        try {
          const message = normalizeMessage(event.data);
          this.emitData(message);
        } catch (error) {
          console.error("Invalid ESP32 data:", event.data, error);

          this.emitError(error);
        }
      };

      /*
       * ----------------------------------------------
       * ERROR / DISCONNECT
       * ----------------------------------------------
       */

      eventSource.onerror = (event) => {
        console.error("ESP32 SSE error:", event);

        const error = new Error(`ESP32 connection error at ${url}`);

        this.emitError(error);

        /*
         * Initial connection failed.
         */

        if (!opened) {
          eventSource.close();

          this.eventSource = null;

          reject(error);

          return;
        }

        /*
         * Existing connection lost.
         *
         * EventSource itself will attempt
         * to reconnect.
         */

        if (this.connected) {
          this.connected = false;

          this.emitStatus(false);
        }
      };
    });
  }

  /*
   * ========================================================
   * DISCONNECT
   * ========================================================
   */

  disconnect() {
    return new Promise((resolve) => {
      if (this.eventSource) {
        this.eventSource.close();

        this.eventSource = null;
      }

      if (this.connected) {
        this.connected = false;

        this.emitStatus(false);
      }

      resolve();
    });
  }

  /*
   * ========================================================
   * DISPOSE
   * ========================================================
   */

  dispose() {
    /*
     * Don't call disconnect() here.
     *
     * App.jsx explicitly does:
     *
     *   disconnect().catch(...)
     *   dispose()
     */

    this.eventSource = null;

    this.dataListeners = [];

    this.statusListeners = [];

    this.errorListeners = [];
  }
}
