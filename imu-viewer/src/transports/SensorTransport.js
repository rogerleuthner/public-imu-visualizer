// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

/**
 * SensorTransport
 *
 * Base interface for sensor data transports.
 *
 * The visualization layer agnostic over transport
 * (USB serial, Wi-Fi, Bluetooth, etc.)
 *
 * Every transport produces the same SensorMessage structure.
 */

export class SensorTransport {
  constructor() {
    this.listeners = new Set();
    this.errorListeners = new Set();
    this.statusListeners = new Set();

    this.connected = false;
  }

  /**
   * Subscribe to sensor messages.
   *
   * callback(message)
   *
   * Returns an unsubscribe function.
   */
  onData(callback) {
    this.listeners.add(callback);

    return () => {
      this.listeners.delete(callback);
    };
  }

  /**
   * Subscribe to transport errors.
   */
  onError(callback) {
    this.errorListeners.add(callback);

    return () => {
      this.errorListeners.delete(callback);
    };
  }

  /**
   * Subscribe to connection state changes.
   *
   * callback(true/false)
   */
  onStatus(callback) {
    this.statusListeners.add(callback);

    return () => {
      this.statusListeners.delete(callback);
    };
  }

  /**
   * Called by subclasses when sensor data arrives.
   */
  emitData(message) {
    for (const callback of this.listeners) {
      try {
        callback(message);
      } catch (error) {
        console.error("Sensor data listener error:", error);
      }
    }
  }

  /**
   * Called by subclasses when an error occurs.
   */
  emitError(error) {
    console.error("Sensor transport error:", error);

    for (const callback of this.errorListeners) {
      try {
        callback(error);
      } catch (listenerError) {
        console.error("Sensor error listener failed:", listenerError);
      }
    }
  }

  /**
   * Called by subclasses when connection state changes.
   */
  setConnected(value) {
    this.connected = value;

    for (const callback of this.statusListeners) {
      try {
        callback(value);
      } catch (error) {
        console.error("Sensor status listener error:", error);
      }
    }
  }

  /**
   * Connect the transport.
   *
   * Subclasses must implement this.
   */
  async connect() {
    throw new Error("SensorTransport.connect() not implemented");
  }

  /**
   * Disconnect the transport.
   *
   * Subclasses must implement this.
   */
  async disconnect() {
    throw new Error("SensorTransport.disconnect() not implemented");
  }

  /**
   * Indicates whether this transport is connected.
   */
  isConnected() {
    return this.connected;
  }

  /**
   * Clean up listeners.
   */
  dispose() {
    this.listeners.clear();
    this.errorListeners.clear();
    this.statusListeners.clear();
  }
}
