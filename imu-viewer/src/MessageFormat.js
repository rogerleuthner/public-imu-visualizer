// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

/**
 * Discriminate and normalize message format as emitted by hardware interface
 * Discrimination for now is cheezy and based upon data content.  If more
 * sophisticated protocol is required add a top level discriminator field
 * instead and explicitly mark.
 */

export function isaHealthJSON(message) {
  if (message !== undefined)
    if (typeof message === "object")
      if (message.micropython !== undefined) return true;

  return false;
}

export function isaIMUJSON(message) {
  if (message !== undefined)
    if (typeof message === "object") if (message.yaw !== undefined) return true;

  return false;
}

class UnknownMessageTypeError extends Error {}

/**
 * @param {string|JSON object} data
 * @returns {JSON object}
 */
export function normalizeMessage(data) {
  const message = JSON.parse(data);

  if (isaIMUJSON(message)) return normalizeIMUSensorMessage(message);

  if (isaHealthJSON(message)) return normalizeHEALTHSensorMessage(message);

  throw new UnknownMessageTypeError(data);
}

/**
 *
 */
function normalizeHEALTHSensorMessage(data) {
  return data;
}

/**
 * Normalize an incoming ESP32 JSON object.
 * Flat (seq, t, ax, ay, az, gx, gy, gz, roll, pitch, yaw, temp)
 * into hierarchy (seq, timestamp, accel (x,y,z), gyro (x,y,z), orientation (roll,pitch,yaw), temperature)
 */
function normalizeIMUSensorMessage(data) {
  return {
    seq: Number.isFinite(data.seq) ? data.seq : null,

    timestamp: Number.isFinite(data.t) ? data.t : Date.now(),

    accel: {
      x: Number(data.ax) || 0,

      y: Number(data.ay) || 0,

      z: Number(data.az) || 0,
    },

    gyro: {
      x: Number(data.gx) || 0,

      y: Number(data.gy) || 0,

      z: Number(data.gz) || 0,
    },

    orientation: {
      roll: Number(data.roll) || 0,

      pitch: Number(data.pitch) || 0,

      yaw: Number(data.yaw) || 0,
    },

    temperature: Number(data.temp) || 0,
  };
}
