// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import React, { useMemo } from "react";
import "./ESP32Dashboard.css";

/*
 * Usage:
 *
 * <Esp32Dashboard connected data={deviceJson} />
 *
 * The component is intentionally data-driven. Pass a new JSON object
 * through `data` and React will re-render the dashboard automatically.
 */

const defaultData = {
  micropython: {
    version: "3.4.0; MicroPython v1.29.0 on 2026-08-24",
    platform: "esp32",
    implementation: "micropython",
  },
  buffers: {
    _total: { size: 0, free: 0, used: 0, used_percent: 0 },
  },
  cpu: {
    memory_variant: "N16R8",
    psram_mb: 8,
    frequency_mhz: 240,
    frequency_hz: 240000000,
    flash_mb: 16,
    target: "ESP32-S3-DevKitC-1",
    unique_id: "44b176cd6ebc",
  },
  stack: { available: true, used: 1584 },
  uptime: {
    days: 0,
    seconds: 105,
    hours: 0,
    milliseconds: 105017,
    minutes: 1,
  },
  filesystem: {
    free: 9551872,
    used_percent: 34.933036,
    available: true,
    total: 14680064,
    used: 5128192,
  },
  reset: {
    available: true,
    code: 1,
    name: "power_on",
  },
  wifi: {
    dns: "192.168.1.1",
    active: true,
    connected: true,
    rssi: -49,
    available: true,
    ip: "192.168.1.12",
    netmask: "255.255.255.0",
    gateway: "192.168.1.1",
  },
  sockets: { count: 0, sockets: {} },
  counters: {
    spi_errors: 0,
    http_errors: 0,
    errors: 0,
    exceptions: 0,
    uart_tx_overflows: 0,
    i2c_errors: 0,
    network_rx_errors: 0,
    uart_rx_overflows: 0,
    mqtt_reconnects: 0,
    network_tx_errors: 0,
    watchdog_feeds: 0,
    sensor_errors: 0,
  },
  psram: {
    available: false,
    free: 0,
    used: 0,
    total: 0,
  },
  memory: {
    minimum_free_ever: 8200912,
    used: 52272,
    used_percent: 0.6332573,
    maximum_used_ever: 53552,
    free: 8202192,
    free_percent: 99.366744,
    total: 8254464,
  },
  gc: {
    total_recovered: 0,
    collections: 0,
    current_free: 8201792,
  },
  loop: {
    max_ms: 326,
    iterations: 101773,
    min_ms: 0,
    average_ms: 1.031865,
  },
  health: {
    warnings: [],
    problems: [],
    status: "OK",
  },
};

const number = (value, digits = 0) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }

  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
  });
};

const percent = (value, digits = 1) =>
  value === null || value === undefined ? "—" : `${number(value, digits)}%`;

const bytes = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }

  const n = Number(value);

  if (n < 1024) return `${number(n)} B`;
  if (n < 1024 ** 2) return `${number(n / 1024, 1)} KB`;
  if (n < 1024 ** 3) return `${number(n / 1024 ** 2, 2)} MB`;

  return `${number(n / 1024 ** 3, 2)} GB`;
};

const duration = (uptime = {}) => {
  const days = Number(uptime.days || 0);
  const hours = Number(uptime.hours || 0);
  const minutes = Number(uptime.minutes || 0);
  const seconds = Number(uptime.seconds || 0);

  return [
    days ? `${days}d` : null,
    hours ? `${hours}h` : null,
    minutes ? `${minutes}m` : null,
    `${seconds}s`,
  ]
    .filter(Boolean)
    .join(" ");
};

const LabelValue = ({ label, value, className = "" }) => (
  <div className={className}>
    <span>{label}</span>
    <strong>{value}</strong>
  </div>
);

const DataRow = ({ label, value, className = "" }) => (
  <div className={className}>
    <span>{label}</span>
    <span>{value}</span>
  </div>
);

const Meter = ({ value, color = "blue" }) => (
  <div className="meter">
    <div
      className={`meter-fill ${color}`}
      style={{ width: `${Math.min(100, Math.max(0, Number(value) || 0))}%` }}
    />
  </div>
);

const Section = ({ title, children, className = "" }) => (
  <section className={`dashboard-section ${className}`}>
    <h2>{title}</h2>
    {children}
  </section>
);

const StatusBadge = ({ ok, children }) => (
  <span className={`status-badge ${ok ? "ok" : "bad"}`}>{children}</span>
);

const CounterGrid = ({ counters = {} }) => {
  const entries = Object.entries(counters);

  return (
    <div className="counter-grid">
      {entries.map(([key, value]) => {
        const isError =
          /error|exception|overflow|reconnect|sensor/i.test(key) &&
          Number(value) > 0;

        const label = key
          .replace(/_/g, " ")
          .replace(/\b\w/g, (c) => c.toUpperCase());

        return (
          <div
            className={`counter ${isError ? "counter-warning" : ""}`}
            key={key}
          >
            <span>{label}</span>
            <strong>{number(value)}</strong>
          </div>
        );
      })}
    </div>
  );
};

export default function Esp32Dashboard({
  data = defaultData,
  connected,
  onBack,
}) {
  /*
   * Merge the incoming object with the default structure so the dashboard
   * remains usable if a future firmware version omits a section or field.
   */
  const d = useMemo(
    () => ({
      ...defaultData,
      ...data,
      cpu: { ...defaultData.cpu, ...(data?.cpu || {}) },
      wifi: { ...defaultData.wifi, ...(data?.wifi || {}) },
      memory: { ...defaultData.memory, ...(data?.memory || {}) },
      filesystem: { ...defaultData.filesystem, ...(data?.filesystem || {}) },
      uptime: { ...defaultData.uptime, ...(data?.uptime || {}) },
      loop: { ...defaultData.loop, ...(data?.loop || {}) },
      health: { ...defaultData.health, ...(data?.health || {}) },
      reset: { ...defaultData.reset, ...(data?.reset || {}) },
      psram: { ...defaultData.psram, ...(data?.psram || {}) },
      stack: { ...defaultData.stack, ...(data?.stack || {}) },
      gc: { ...defaultData.gc, ...(data?.gc || {}) },
      sockets: { ...defaultData.sockets, ...(data?.sockets || {}) },
      counters: { ...defaultData.counters, ...(data?.counters || {}) },
      micropython: {
        ...defaultData.micropython,
        ...(data?.micropython || {}),
      },
    }),
    [data],
  );

  const wifiConnected = Boolean(d.wifi.connected && d.wifi.active);
  const healthOk =
    String(d.health.status || "").toUpperCase() === "OK" &&
    !(d.health.problems?.length > 0);

  const memoryUsed = Number(d.memory.used_percent || 0);
  const filesystemUsed = Number(d.filesystem.used_percent || 0);

  return (
    <div className="app esp32-dashboard">
      <header>
        <div>
          <h1>ESP32 Device Dashboard</h1>
          <div className="subtitle">
            {d.cpu.target} · {d.micropython.platform} ·{" "}
            {d.micropython.implementation}
          </div>
        </div>
        <button onClick={onBack}>Back to IMU</button>
        <div className="connection">
          <span className={`status ${connected ? "connected" : ""}`} />
          <span>{connected ? "Connected" : "Disconnected"}</span>
        </div>
      </header>

      <main>
        <div className="left">
          <div className="viewer">
            <div className="dashboard-overview">
              <div className="overview-title">
                <span className="eyebrow">DEVICE HEALTH</span>
                <StatusBadge ok={healthOk}>
                  {d.health.status || "UNKNOWN"}
                </StatusBadge>
              </div>

              <div className="overview-grid">
                <div className="overview-card">
                  <span>CPU</span>
                  <strong>{number(d.cpu.frequency_mhz)} MHz</strong>
                  <small>{d.cpu.memory_variant}</small>
                </div>

                <div className="overview-card">
                  <span>RAM</span>
                  <strong>{percent(memoryUsed, 2)}</strong>
                  <Meter value={memoryUsed} color="green" />
                  <small>
                    {bytes(d.memory.used)} used / {bytes(d.memory.total)}
                  </small>
                </div>

                <div className="overview-card">
                  <span>FLASH</span>
                  <strong>{percent(filesystemUsed, 1)}</strong>
                  <Meter value={filesystemUsed} color="blue" />
                  <small>{bytes(d.filesystem.free)} free</small>
                </div>

                <div className="overview-card">
                  <span>UPTIME</span>
                  <strong>{duration(d.uptime)}</strong>
                  <small>{number(d.uptime.milliseconds)} ms total</small>
                </div>
              </div>

              <div className="device-mark">
                <div className="chip">
                  <div className="chip-core">
                    <span>ESP32</span>
                    <strong>S3</strong>
                  </div>
                  <i />
                  <i />
                  <i />
                  <i />
                  <i />
                  <i />
                  <i />
                  <i />
                </div>

                <div className="device-label">
                  <span>MICROPYTHON</span>
                  <strong>{d.micropython.version}</strong>
                  <small>ID: {d.cpu.unique_id}</small>
                </div>
              </div>
            </div>
          </div>

          <div className="graphs">
            <div className="graph">
              <div className="graph-title">
                <span>MEMORY</span>
                <span>
                  <i className="green" />
                  HEAP
                </span>
              </div>

              <div className="graph-content">
                <div className="graph-metric">
                  <strong>{bytes(d.memory.free)}</strong>
                  <span>free</span>
                </div>

                <div className="graph-track">
                  <div
                    className="graph-bar green-fill"
                    style={{
                      width: `${Math.min(100, memoryUsed)}%`,
                    }}
                  />
                </div>

                <div className="graph-footer">
                  <span>{percent(memoryUsed, 2)} used</span>
                  <span>min free {bytes(d.memory.minimum_free_ever)}</span>
                </div>
              </div>
            </div>

            <div className="graph">
              <div className="graph-title">
                <span>MAIN LOOP</span>
                <span>
                  <i className="blue" />
                  TIMING
                </span>
              </div>

              <div className="graph-content">
                <div className="graph-metric">
                  <strong>{number(d.loop.average_ms, 2)} ms</strong>
                  <span>average</span>
                </div>

                <div className="timing-bars">
                  <div>
                    <span>MIN</span>
                    <strong>{number(d.loop.min_ms)} ms</strong>
                  </div>
                  <div className="timing-average">
                    <span>AVG</span>
                    <strong>{number(d.loop.average_ms, 2)} ms</strong>
                  </div>
                  <div>
                    <span>MAX</span>
                    <strong>{number(d.loop.max_ms)} ms</strong>
                  </div>
                </div>

                <div className="graph-footer">
                  <span>{number(d.loop.iterations)} iterations</span>
                  <span>MAX {number(d.loop.max_ms)} ms</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <aside>
          <Section title="System">
            <div className="big-value">
              <span>Health</span>
              <StatusBadge ok={healthOk}>
                {d.health.status || "UNKNOWN"}
              </StatusBadge>
            </div>

            <div className="data">
              <DataRow label="Target" value={d.cpu.target} />
              <DataRow label="Variant" value={d.cpu.memory_variant} />
              <DataRow
                label="CPU"
                value={`${number(d.cpu.frequency_mhz)} MHz`}
              />
              <DataRow label="Flash" value={`${number(d.cpu.flash_mb)} MB`} />
              <DataRow label="PSRAM" value={`${number(d.cpu.psram_mb)} MB`} />
              <DataRow label="Stack used" value={bytes(d.stack.used)} />
            </div>
          </Section>

          <Section title="Wi-Fi">
            <div className="wifi-status">
              <span className={`status ${wifiConnected ? "connected" : ""}`} />
              <strong>{wifiConnected ? "Connected" : "Offline"}</strong>
              <span className="rssi">{number(d.wifi.rssi)} dBm</span>
            </div>

            <div className="data">
              <DataRow label="IP" value={d.wifi.ip} />
              <DataRow label="Gateway" value={d.wifi.gateway} />
              <DataRow label="DNS" value={d.wifi.dns} />
              <DataRow label="Netmask" value={d.wifi.netmask} />
            </div>
          </Section>

          <Section title="Memory">
            <div className="resource">
              <div className="resource-heading">
                <span>Heap</span>
                <strong>{percent(d.memory.used_percent, 2)}</strong>
              </div>
              <Meter value={d.memory.used_percent} color="green" />
              <div className="resource-detail">
                {bytes(d.memory.used)} / {bytes(d.memory.total)}
              </div>
            </div>

            <div className="resource">
              <div className="resource-heading">
                <span>Filesystem</span>
                <strong>{percent(d.filesystem.used_percent, 1)}</strong>
              </div>
              <Meter value={d.filesystem.used_percent} color="blue" />
              <div className="resource-detail">
                {bytes(d.filesystem.used)} / {bytes(d.filesystem.total)}
              </div>
            </div>

            <div className="data compact">
              <DataRow label="GC free" value={bytes(d.gc.current_free)} />
              <DataRow
                label="GC recovered"
                value={bytes(d.gc.total_recovered)}
              />
              <DataRow label="Collections" value={number(d.gc.collections)} />
            </div>
          </Section>

          <Section title="Uptime">
            <div className="temperature">{duration(d.uptime)}</div>

            <div className="data">
              <DataRow label="Days" value={number(d.uptime.days)} />
              <DataRow label="Hours" value={number(d.uptime.hours)} />
              <DataRow label="Minutes" value={number(d.uptime.minutes)} />
              <DataRow label="Seconds" value={number(d.uptime.seconds)} />
            </div>
          </Section>

          <Section title="Reset">
            <div className="data">
              <DataRow label="Reason" value={d.reset.name} />
              <DataRow label="Code" value={number(d.reset.code)} />
            </div>
          </Section>

          <Section title="Sockets">
            <div className="big-value">
              <span>Active sockets</span>
              <strong>{number(d.sockets.count)}</strong>
            </div>
          </Section>

          <Section title="Diagnostics">
            <CounterGrid counters={d.counters} />
          </Section>

          {(d.health.warnings?.length > 0 || d.health.problems?.length > 0) && (
            <Section title="Alerts" className="alerts-section">
              {d.health.problems?.map((problem, index) => (
                <div className="alert problem" key={`problem-${index}`}>
                  {problem}
                </div>
              ))}

              {d.health.warnings?.map((warning, index) => (
                <div className="alert warning" key={`warning-${index}`}>
                  {warning}
                </div>
              ))}
            </Section>
          )}
        </aside>
      </main>
    </div>
  );
}
