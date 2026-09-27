// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import { useEffect, useState } from "react";

import "./Settings.css";

export default function Settings({ serverIp, onBack }) {
  const [mode, setMode] = useState("AUTO");

  const [ssid, setSsid] = useState("");

  const [password, setPassword] = useState("");

  const [passwordSet, setPasswordSet] = useState(false);

  const [imuRateHz, setImuRateHz] = useState(100);

  const [eventRateHz, setEventRateHz] = useState(20);

  const [status, setStatus] = useState(null);

  const [loading, setLoading] = useState(true);

  function apiUrl(path) {
    const hostname = window.location.hostname;

    const localBrowser =
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "::1";

    if (!localBrowser) {
      return `${window.location.origin}${path}`;
    }

    return `http://${serverIp}${path}`;
  }

  /*
   * ==========================================================
   * LOAD CURRENT SETTINGS
   * ==========================================================
   */

  useEffect(() => {
    async function loadSettings() {
      try {
        const response = await fetch(apiUrl("/api/config"));

        if (!response.ok) {
          throw new Error("Unable to read ESP32 settings");
        }

        const data = await response.json();

        setMode(data.mode || "AUTO");

        setSsid(data.ssid || "");

        setPasswordSet(Boolean(data.password_set));

        setEventRateHz(Number(data.event_rate_hz) || 20);

        setImuRateHz(Number(data.imu_rate_hz) || 100);
      } catch (error) {
        console.error(error);

        setStatus({
          type: "error",
          message: error.message,
        });
      } finally {
        setLoading(false);
      }
    }

    loadSettings();
  }, []);

  /*
   * ==========================================================
   * SAVE SETTINGS
   * ==========================================================
   */

  async function saveSettings() {
    setStatus({
      type: "info",
      message: "Saving...",
    });

    try {
      const response = await fetch(apiUrl("/api/config"), {
        method: "POST",

        headers: {
          "Content-Type": "application/json",
        },

        body: JSON.stringify({
          mode,

          ssid,

          password,

          imu_rate_hz: imuRateHz,

          event_rate_hz: eventRateHz,
        }),
      });

      if (!response.ok) {
        let message = "Unable to save settings";

        try {
          const data = await response.json();

          if (data.error) {
            message = data.error;
          }
        } catch (_) {
          // Ignore JSON parsing failure.
        }

        throw new Error(message);
      }

      const data = await response.json();

      setStatus({
        type: "success",
        message:
          data.message || "Settings saved. Network change is being applied.",
      });

      /*
       * The ESP32 may change IP addresses after
       * switching Wi-Fi modes.
       *
       * Do not immediately navigate away.
       */
    } catch (error) {
      console.error(error);

      setStatus({
        type: "error",
        message: error.message,
      });
    }
  }

  /*
   * ==========================================================
   * RENDER
   * ==========================================================
   */

  return (
    <div className="settings-page">
      <header className="settings-header">
        <div>
          <h1>ESP32-S3 / GY-521</h1>

          <div className="subtitle">Wi-Fi Settings</div>
        </div>

        <button onClick={onBack}>Back to IMU</button>

        <button className="save-button" onClick={saveSettings}>
          Save Settings
        </button>
      </header>

      <main className="settings-main">
        <section className="settings-card">
          <h2>Network Mode</h2>

          {loading ? (
            <p>Loading settings...</p>
          ) : (
            <>
              <label className="mode-option">
                <input
                  type="radio"
                  name="wifi-mode"
                  value="AUTO"
                  checked={mode === "AUTO"}
                  onChange={() => setMode("AUTO")}
                />

                <span>
                  <strong>Auto</strong>

                  <small>
                    Try the configured Wi-Fi network first. If it cannot
                    connect, keep the ESP32 Access Point available.
                  </small>
                </span>
              </label>

              <label className="mode-option">
                <input
                  type="radio"
                  name="wifi-mode"
                  value="AP"
                  checked={mode === "AP"}
                  onChange={() => setMode("AP")}
                />

                <span>
                  <strong>Access Point</strong>

                  <small>Always create the ESP32-IMU Wi-Fi network.</small>
                </span>
              </label>

              <label className="mode-option">
                <input
                  type="radio"
                  name="wifi-mode"
                  value="STA"
                  checked={mode === "STA"}
                  onChange={() => setMode("STA")}
                />

                <span>
                  <strong>Existing Wi-Fi</strong>

                  <small>Connect to the configured Wi-Fi network.</small>
                </span>
              </label>

              {status && (
                <div className={`settings-status ${status.type}`}>
                  {status.message}
                </div>
              )}
            </>
          )}
        </section>

        <section className="settings-card">
          <div className="wifi-fields">
            <label>
              <span>Network SSID</span>

              <input
                type="text"
                value={ssid}
                onChange={(event) => setSsid(event.target.value)}
                placeholder="Wi-Fi network name"
                autoComplete="off"
              />
            </label>

            <label>
              <span>Wi-Fi Password</span>

              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={
                  passwordSet
                    ? "Leave blank to keep existing password"
                    : "Wi-Fi password"
                }
                autoComplete="new-password"
              />
            </label>
          </div>

          <div className="imu-rate-field">
            <label>
              <span>IMU Data Rate</span>

              <div className="imu-rate-value">{imuRateHz} Hz</div>
            </label>

            <input
              type="range"
              min="4"
              max="1000"
              step="1"
              value={imuRateHz}
              onChange={(event) => setImuRateHz(Number(event.target.value))}
            />

            <div className="imu-rate-range">4 Hz – 1000 Hz</div>
          </div>

          <div className="imu-rate-field">
            <label>
              <span>Event Data Rate</span>

              <div className="imu-rate-value">{eventRateHz} Hz</div>
            </label>

            <input
              type="range"
              min="1"
              max="100"
              step="1"
              value={eventRateHz}
              onChange={(event) => setEventRateHz(Number(event.target.value))}
            />

            <div className="imu-rate-range">1 Hz – 100 Hz</div>
          </div>
        </section>
      </main>
    </div>
  );
}
