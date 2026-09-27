// Copyright © 2026 Roger B. Leuthner. All rights reserved.  This software is provided for informational and educational purposes. Use of this software does not imply endorsement by the author of any particular use or application. The author assumes no responsibility or liability for any damages or consequences arising from its use.

import { useEffect, useRef, useState, lazy, Suspense } from "react";

import { Canvas } from "@react-three/fiber";

import {
  Grid,
  OrbitControls,
  PerspectiveCamera,
  Text,
} from "@react-three/drei";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { WiFiSensorTransport } from "./transports/WiFiSensorTransport";

import { isaHealthJSON } from "./MessageFormat";

import "./App.css";

// bundle size optimization
const Esp32Dashboard = lazy(() => import("./Esp32Dashboard"));
const Settings = lazy(() => import("./Settings"));

const MAX_HISTORY = 300;
// this should match that hardcoded in the imu_server.py
const DEFAULT_IMU_SERVER_IP = "10.0.0.1";

/*
 * ============================================================
 * INITIAL VALUES
 * ============================================================
 */

const INITIAL_ORIENTATION = {
  roll: 0,
  pitch: 0,
  yaw: 0,
};

// Internal hierarchical packet format
const INITIAL_SENSOR = {
  accel: {
    x: 0,
    y: 0,
    z: 0,
  },

  gyro: {
    x: 0,
    y: 0,
    z: 0,
  },

  temperature: 0,
};

/*
 * ============================================================
 * ANGLE HELPERS
 * ============================================================
 */

/*
 * Convert an angle to the range:
 *
 *       -180 <= angle < +180
 *
 * This prevents yaw from eventually becoming:
 *
 * 359°
 * 721°
 * -542°
 *
 * etc.
 */

function normalizeAngle(angle) {
  let result = ((((angle + 180) % 360) + 360) % 360) - 180;

  return result;
}

/*
 * ============================================================
 * 3D BOARD
 * ============================================================
 */

function BoardModel({ orientation }) {
  const boardRef = useRef();

  useEffect(() => {
    if (!boardRef.current) {
      return;
    }

    const roll = (orientation.roll * Math.PI) / 180;

    const pitch = (orientation.pitch * Math.PI) / 180;

    const yaw = (orientation.yaw * Math.PI) / 180;

    boardRef.current.rotation.x = pitch;

    boardRef.current.rotation.y = yaw;

    boardRef.current.rotation.z = roll;
  }, [orientation]);

  return (
    <group ref={boardRef}>
      {/* ==================================================
          ESP32 BOARD
          ================================================== */}

      <mesh position={[0, 0.15, 0]}>
        <boxGeometry args={[4.0, 0.22, 2.3]} />

        <meshStandardMaterial
          color="#1d252b"
          roughness={0.65}
          metalness={0.25}
        />
      </mesh>

      {/* PCB surface */}

      <mesh position={[0, 0.275, 0]}>
        <boxGeometry args={[3.85, 0.025, 2.15]} />

        <meshStandardMaterial color="#245d4b" roughness={0.7} />
      </mesh>

      {/* ==================================================
          ESP32 CHIP
          ================================================== */}

      <mesh position={[0.4, 0.34, 0]}>
        <boxGeometry args={[0.75, 0.12, 0.65]} />

        <meshStandardMaterial color="#111" />
      </mesh>

      {/* ==================================================
          USB
          ================================================== */}

      <mesh position={[2.12, 0.28, 0]}>
        <boxGeometry args={[0.32, 0.28, 0.65]} />

        <meshStandardMaterial color="#aaa" metalness={0.8} roughness={0.25} />
      </mesh>

      {/* ==================================================
          ESP32 PIN HEADERS
          ================================================== */}

      {Array.from({ length: 15 }).map((_, i) => (
        <mesh key={`left-${i}`} position={[-1.45 + i * 0.2, 0.43, -1.03]}>
          <cylinderGeometry args={[0.035, 0.035, 0.3, 8]} />

          <meshStandardMaterial color="#d0a33a" metalness={0.7} />
        </mesh>
      ))}

      {Array.from({ length: 15 }).map((_, i) => (
        <mesh key={`right-${i}`} position={[-1.45 + i * 0.2, 0.43, 1.03]}>
          <cylinderGeometry args={[0.035, 0.035, 0.3, 8]} />

          <meshStandardMaterial color="#d0a33a" metalness={0.7} />
        </mesh>
      ))}

      {/* ==================================================
          GY-521
          ================================================== */}

      <group position={[0, 0.48, 0]}>
        <mesh>
          <boxGeometry args={[1.65, 0.12, 1.1]} />

          <meshStandardMaterial color="#294f8f" roughness={0.65} />
        </mesh>

        {/* MPU-6050 */}

        <mesh position={[0, 0.1, 0]}>
          <boxGeometry args={[0.45, 0.12, 0.45]} />

          <meshStandardMaterial color="#111" />
        </mesh>

        {/* GY-521 header */}

        {Array.from({ length: 8 }).map((_, i) => (
          <mesh key={i} position={[-0.7 + i * 0.2, 0.18, -0.45]}>
            <cylinderGeometry args={[0.035, 0.035, 0.35, 8]} />

            <meshStandardMaterial color="#d0a33a" metalness={0.7} />
          </mesh>
        ))}
      </group>

      {/* ==================================================
          AXES
          ================================================== */}

      <arrowHelper
        args={[{ x: 1, y: 0, z: 0 }, { x: -1.8, y: 0.65, z: 0 }, 1.2, 0xff3333]}
      />

      <arrowHelper
        args={[{ x: 0, y: 1, z: 0 }, { x: 0, y: 0.65, z: -0.8 }, 1.2, 0x33ff66]}
      />

      <arrowHelper
        args={[{ x: 0, y: 0, z: 1 }, { x: 0, y: 0.65, z: 0 }, 1.2, 0x3388ff]}
      />

      <Text
        position={[-2.0, 0.65, 0]}
        color="#ff4444"
        fontSize={0.5}
        font="/fonts/Roboto-Regular.ttf"
        characters="XYZ"
      >
        X
      </Text>

      <Text
        position={[0, 2, -0.8]}
        color="#44ff66"
        fontSize={0.5}
        font="/fonts/Roboto-Regular.ttf"
        characters="XYZ"
      >
        Y
      </Text>

      <Text
        position={[0, 0.65, 1.5]}
        color="#4488ff"
        fontSize={0.5}
        font="/fonts/Roboto-Regular.ttf"
        characters="XYZ"
      >
        Z
      </Text>
    </group>
  );
}

/*
 * ============================================================
 * SCENE
 * ============================================================
 */

function Scene({ orientation }) {
  return (
    <Canvas>
      <PerspectiveCamera makeDefault position={[7, 5.5, 7]} />

      <ambientLight intensity={1.3} />

      <directionalLight position={[5, 8, 5]} intensity={2.5} />

      <directionalLight position={[-5, 4, -5]} intensity={1} />

      <Grid
        args={[20, 20]}
        cellSize={1}
        cellThickness={0.5}
        cellColor="#39414a"
        sectionSize={5}
        sectionThickness={1}
        sectionColor="#68717c"
        fadeDistance={25}
        infiniteGrid
      />

      <BoardModel orientation={orientation} />

      <OrbitControls />
    </Canvas>
  );
}

/*
 * ============================================================
 * ORIENTATION GRAPH
 * ============================================================
 */

function OrientationGraph({ history }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={history}>
        <CartesianGrid stroke="#303740" />

        <XAxis dataKey="time" stroke="#89939f" tick={{ fontSize: 10 }} />

        <YAxis stroke="#89939f" tick={{ fontSize: 10 }} />

        <Tooltip
          contentStyle={{
            background: "#181d24",
            border: "1px solid #3a424d",
          }}
        />

        <Line
          type="monotone"
          dataKey="roll"
          stroke="#ff5555"
          dot={false}
          strokeWidth={2}
        />

        <Line
          type="monotone"
          dataKey="pitch"
          stroke="#55ff77"
          dot={false}
          strokeWidth={2}
        />

        <Line
          type="monotone"
          dataKey="yaw"
          stroke="#5599ff"
          dot={false}
          strokeWidth={2}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/*
 * ============================================================
 * SENSOR GRAPH
 * ============================================================
 */

function SensorGraph({ history }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={history}>
        <CartesianGrid stroke="#303740" />

        <XAxis dataKey="time" stroke="#89939f" tick={{ fontSize: 10 }} />

        <YAxis stroke="#89939f" tick={{ fontSize: 10 }} />

        <Tooltip
          contentStyle={{
            background: "#181d24",
            border: "1px solid #3a424d",
          }}
        />

        <Line
          type="monotone"
          dataKey="ax"
          stroke="#ff5555"
          dot={false}
          strokeWidth={1.5}
        />

        <Line
          type="monotone"
          dataKey="ay"
          stroke="#55ff77"
          dot={false}
          strokeWidth={1.5}
        />

        <Line
          type="monotone"
          dataKey="az"
          stroke="#5599ff"
          dot={false}
          strokeWidth={1.5}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/*
 * ============================================================
 * MAIN APPLICATION
 * ============================================================
 */

export default function App() {
  const transportRef = useRef(null);

  const [showSettings, setShowSettings] = useState(false);

  const [showDashboard, setShowDashboard] = useState(false);

  const [deviceData, setDeviceData] = useState(null);

  /*
   * This ref stores the latest raw orientation.
   *
   * We need the raw value separately from the displayed
   * zeroed value because Zero needs to capture the actual
   * current sensor orientation.
   */

  const rawOrientationRef = useRef({
    roll: 0,
    pitch: 0,
    yaw: 0,
  });

  /*
   * Zero offsets.
   *
   * These are the sensor values that existed when the
   * user pressed Zero Orientation.
   */

  const orientationOffsetRef = useRef({
    roll: 0,
    pitch: 0,
    yaw: 0,
  });

  const [connected, setConnected] = useState(false);

  const [orientation, setOrientation] = useState(INITIAL_ORIENTATION);

  const [sensor, setSensor] = useState(INITIAL_SENSOR);

  const [orientationHistory, setOrientationHistory] = useState([]);

  const [sensorHistory, setSensorHistory] = useState([]);

  const [packetCount, setPacketCount] = useState(0);

  const [lastPacket, setLastPacket] = useState(null);

  const [lastSequence, setLastSequence] = useState(null);

  const [droppedPackets, setDroppedPackets] = useState(0);

  const [error, setError] = useState(null);

  /*
   * ==========================================================
   * CREATE TRANSPORT
   * ==========================================================
   */

  useEffect(() => {
    const transport = new WiFiSensorTransport();

    transportRef.current = transport;

    const unsubscribeData = transport.onData(handleSensorMessage);

    const unsubscribeStatus = transport.onStatus((value) => {
      setConnected(value);

      if (value) {
        setError(null);
      }
    });

    const unsubscribeError = transport.onError((transportError) => {
      setError(transportError?.message || String(transportError));
    });

    return () => {
      unsubscribeData();

      unsubscribeStatus();

      unsubscribeError();

      transport.disconnect().catch(() => {});

      transport.dispose();

      transportRef.current = null;
    };
  }, []);

  /*
   * ==========================================================
   * APPLY ZERO OFFSET
   * ==========================================================
   */

  function applyOrientationZero(raw) {
    const offset = orientationOffsetRef.current;

    return {
      roll: raw.roll - offset.roll,

      pitch: raw.pitch - offset.pitch,

      yaw: normalizeAngle(raw.yaw - offset.yaw),
    };
  }

  /*
   * ==========================================================
   * ZERO ORIENTATION
   * ==========================================================
   */

  function zeroOrientation() {
    /*
     * Capture the actual sensor orientation NOW.
     */

    const raw = rawOrientationRef.current;

    orientationOffsetRef.current = {
      roll: raw.roll,

      pitch: raw.pitch,

      yaw: raw.yaw,
    };

    /*
     * Immediately display zero rather than waiting
     * for the next sensor packet.
     */

    setOrientation({
      roll: 0,
      pitch: 0,
      yaw: 0,
    });

    /*
     * Start a new graph segment.
     *
     * This makes it visually obvious where zeroing
     * happened.
     */

    setOrientationHistory([]);
  }

  /*
   * ==========================================================
   * HANDLE SENSOR MESSAGE
   * ==========================================================
   */

  function handleSensorMessage(message) {
    const now = Date.now();

    if (isaHealthJSON(message)) {
      setDeviceData(message);
    } else {
      /*
       * Save raw orientation BEFORE applying offset.
       */

      rawOrientationRef.current = message.orientation;

      /*
       * Convert raw orientation into zero-relative
       * orientation.
       */

      const zeroedOrientation = applyOrientationZero(message.orientation);

      /*
       * Packet diagnostics.
       */

      setPacketCount((count) => count + 1);

      setLastPacket(now);

      /*
       * Detect missing sequence numbers.
       */

      const previousSequence = lastSequence;

      if (message.seq !== null && previousSequence !== null) {
        const expected = previousSequence + 1;

        if (message.seq > expected) {
          const lost = message.seq - expected;

          setDroppedPackets((count) => count + lost);
        }
      }

      if (message.seq !== null) {
        setLastSequence(message.seq);
      }

      /*
       * Update displayed orientation.
       */

      setOrientation(zeroedOrientation);

      /*
       * Update raw sensor values.
       */

      setSensor({
        accel: message.accel,

        gyro: message.gyro,

        temperature: message.temperature,
      });

      /*
       * Graph orientation AFTER zeroing.
       */

      const time = new Date().toLocaleTimeString();

      setOrientationHistory((old) => {
        const next = [
          ...old,

          {
            time,

            roll: zeroedOrientation.roll,

            pitch: zeroedOrientation.pitch,

            yaw: zeroedOrientation.yaw,
          },
        ];

        return next.slice(-MAX_HISTORY);
      });

      /*
       * Accelerometer history remains raw.
       */

      setSensorHistory((old) => {
        const next = [
          ...old,

          {
            time,

            ax: message.accel.x,

            ay: message.accel.y,

            az: message.accel.z,
          },
        ];

        return next.slice(-MAX_HISTORY);
      });
    }
  }

  /*
   * ==========================================================
   * CONNECT
   * ==========================================================
   */

  async function connect(host) {
    setError(null);

    try {
      await transportRef.current.connect(host);
    } catch (transportError) {
      setError(transportError?.message || String(transportError));
    }
  }

  /*
   * ==========================================================
   * DISCONNECT
   * ==========================================================
   */

  async function disconnect() {
    try {
      await transportRef.current?.disconnect();
    } catch (transportError) {
      console.error(transportError);
    }
  }

  /*
   * ==========================================================
   * RESET GRAPH ONLY
   * ==========================================================
   */

  function clearHistory() {
    setOrientationHistory([]);

    setSensorHistory([]);
  }

  /*
   * ==========================================================
   * DIAGNOSTICS
   * ==========================================================
   */

  const packetAge = lastPacket !== null ? Date.now() - lastPacket : null;

  const [ip, setIp] = useState(DEFAULT_IMU_SERVER_IP);

  if (showSettings) {
    return (
      <Suspense fallback={<div>Loading...</div>}>
        <Settings serverIp={ip} onBack={() => setShowSettings(false)} />
      </Suspense>
    );
  }

  if (showDashboard) {
    return (
      <Suspense fallback={<div>Loading...</div>}>
        <Esp32Dashboard
          data={deviceData}
          connected={connected}
          onBack={() => setShowDashboard(false)}
        />
      </Suspense>
    );
  }

  /*
   * ==========================================================
   * RENDER
   * ==========================================================
   */

  return (
    <div className="app">
      {/* ==================================================
          HEADER
          ================================================== */}

      <header>
        <div>
          <h1>ESP32-S3 / GY-521</h1>

          <div className="subtitle">6-axis IMU visualization</div>
        </div>

        <div>
          <button onClick={() => setShowDashboard(true)}>Dashboard</button>
        </div>

        <div className="connection">
          <span className={connected ? "status connected" : "status"} />

          {connected ? "Wi-Fi Connected" : "Disconnected"}

          <button onClick={() => setShowSettings(true)}>Settings</button>

          {!connected ? (
            <>
              <button onClick={() => connect()}>Connect</button>
            </>
          ) : (
            <button onClick={disconnect}>
              Disconnect {window.location.origin}/events
            </button>
          )}
        </div>
      </header>

      {/* ==================================================
          ERROR
          ================================================== */}

      {error && (
        <div
          style={{
            padding: "8px 16px",
            background: "#5b2424",
            color: "#ffd6d6",
            borderBottom: "1px solid #8b3838",
            fontSize: "12px",
          }}
        >
          {error}
        </div>
      )}

      {/* ==================================================
          MAIN
          ================================================== */}

      <main>
        {/* ==================================================
            LEFT
            ================================================== */}

        <section className="left">
          <div className="viewer">
            <Scene orientation={orientation} />
          </div>

          <div className="graphs">
            <div className="graph">
              <div className="graph-title">
                Orientation
                <span>
                  <i className="red" />
                  Roll
                  <i className="green" />
                  Pitch
                  <i className="blue" />
                  Yaw
                </span>
              </div>

              <OrientationGraph history={orientationHistory} />
            </div>

            <div className="graph">
              <div className="graph-title">
                Accelerometer
                <span>
                  <i className="red" />
                  X
                  <i className="green" />
                  Y
                  <i className="blue" />Z
                </span>
              </div>

              <SensorGraph history={sensorHistory} />
            </div>
          </div>
        </section>

        {/* ==================================================
            RIGHT PANEL
            ================================================== */}

        <aside>
          <h2>Orientation</h2>

          <div className="big-value">
            <span>Roll</span>

            <strong>{orientation.roll.toFixed(2)}°</strong>
          </div>

          <div className="big-value">
            <span>Pitch</span>

            <strong>{orientation.pitch.toFixed(2)}°</strong>
          </div>

          <div className="big-value">
            <span>Yaw</span>

            <strong>{orientation.yaw.toFixed(2)}°</strong>
          </div>

          {/* ==================================================
              ZERO BUTTON
              ================================================== */}

          <button className="reset" onClick={zeroOrientation}>
            Zero Orientation
          </button>

          <button
            className="reset"
            onClick={clearHistory}
            style={{
              background: "#3a424d",
            }}
          >
            Clear Graphs
          </button>

          {/* ==================================================
              ACCELEROMETER
              ================================================== */}

          <h2>Accelerometer</h2>

          <div className="data">
            <div>
              X<span>{sensor.accel.x.toFixed(3)} g</span>
            </div>

            <div>
              Y<span>{sensor.accel.y.toFixed(3)} g</span>
            </div>

            <div>
              Z<span>{sensor.accel.z.toFixed(3)} g</span>
            </div>
          </div>

          {/* ==================================================
              GYROSCOPE
              ================================================== */}

          <h2>Gyroscope</h2>

          <div className="data">
            <div>
              X<span>{sensor.gyro.x.toFixed(2)} °/s</span>
            </div>

            <div>
              Y<span>{sensor.gyro.y.toFixed(2)} °/s</span>
            </div>

            <div>
              Z<span>{sensor.gyro.z.toFixed(2)} °/s</span>
            </div>
          </div>

          {/* ==================================================
              TEMPERATURE
              ================================================== */}

          <h2>Temperature</h2>

          <div className="temperature">{sensor.temperature.toFixed(2)} °C</div>

          {/* ==================================================
              DIAGNOSTICS
              ================================================== */}

          <h2>Diagnostics</h2>

          <div className="diagnostics">
            <div>
              Transport
              <span>Wi-Fi / SSE</span>
            </div>

            <div>
              Packets
              <span>{packetCount}</span>
            </div>

            <div>
              Dropped
              <span>{droppedPackets}</span>
            </div>

            <div>
              Last packet
              <span>{packetAge !== null ? `${packetAge} ms` : "--"}</span>
            </div>

            <div>
              Sequence
              <span>{lastSequence !== null ? lastSequence : "--"}</span>
            </div>
          </div>
        </aside>
      </main>
    </div>
  );
}
