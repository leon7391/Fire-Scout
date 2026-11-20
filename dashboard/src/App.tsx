
import { useEffect, useState } from 'react'

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import NodeOverview from './components/NodeOverview'
import './index.css'

// ===========================
// TYPES
// ===========================

type NodeInfo = {
  node_id: string
  mqtt_node: string
  status: string
  current_status: string
  last_seen: string | null
  map_id?: string | null
  map_x?: number | null
  map_y?: number | null
  map_frame?: string | null
}

type Reading = {
  id: number
  received_at: string
  node_id: string
  temperature_c: number
  humidity_pct: number
  mq2_raw: number
}

type Overview = {
  total_nodes: number
  online_nodes: number
  offline_nodes: number
  unknown_nodes: number
  total_readings: number
}

type SensorKey =
  | 'temperature_c'
  | 'humidity_pct'
  | 'mq2_raw'

// ===========================
// API FUNCTIONS
// ===========================

async function getJSON<T>(url: string): Promise<T> {
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error(
      `${url}: HTTP ${response.status}`
    )
  }

  const contentType =
    response.headers.get('content-type') || ''

  if (!contentType.includes('application/json')) {
    throw new Error(
      `${url}: API returned HTML or non-JSON response`
    )
  }

  return (await response.json()) as T
}

// ===========================
// UTILITY FUNCTIONS
// ===========================

function formatTime(value?: string | null): string {
  if (!value) {
    return 'No data'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString('vi-VN')
}

// ===========================
// METRIC CARD
// ===========================

function MetricCard({
  label,
  value,
  unit,
}: {
  label: string
  value: string
  unit: string
}) {
  return (
    <div className="card metric">
      <span className="muted">
        {label}
      </span>

      <strong>{value}</strong>

      <span className="muted">
        {unit}
      </span>
    </div>
  )
}

// ===========================
// SENSOR HISTORY CHART
// ===========================

function SensorChart({
  data,
  field,
  title,
  color,
}: {
  data: Reading[]
  field: SensorKey
  title: string
  color: string
}) {
  return (
    <section className="card chart-card">
      <h3>{title}</h3>

      {data.length === 0 ? (
        <p className="muted">
          No history data available
        </p>
      ) : (
        <div className="chart">
          <ResponsiveContainer
            width="100%"
            height="100%"
          >
            <LineChart data={data}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#273244"
              />

              <XAxis
                dataKey="received_at"
                stroke="#93a4b8"
                fontSize={11}
                minTickGap={30}
                tickFormatter={(value: string) =>
                  new Date(value).toLocaleTimeString(
                    'vi-VN'
                  )
                }
              />

              <YAxis
                stroke="#93a4b8"
                fontSize={11}
                width={45}
                domain={['auto', 'auto']}
              />

              <Tooltip
                labelFormatter={(value) =>
                  formatTime(String(value))
                }
              />

              <Line
                type="monotone"
                dataKey={field}
                stroke={color}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}

// ===========================
// MAIN APP
// ===========================

export default function App() {
  const [nodes, setNodes] = useState<NodeInfo[]>([])

  const [overview, setOverview] =
    useState<Overview | null>(null)

  const [selectedNode, setSelectedNode] =
    useState<string>('')

  const [latest, setLatest] =
    useState<Reading | null>(null)

  const [history, setHistory] =
    useState<Reading[]>([])

  const [error, setError] =
    useState<string>('')

  const [readingError, setReadingError] =
    useState<string>('')

  // ===========================
  // FETCH ALL NODES
  // ===========================

  useEffect(() => {
    let active = true

    async function loadNodes() {
      try {
        const [nodeData, overviewData] =
          await Promise.all([
            getJSON<NodeInfo[]>('/api/nodes'),
            getJSON<Overview>('/api/overview'),
          ])

        if (!active) return

        setNodes(nodeData)
        setOverview(overviewData)

        setSelectedNode((previous) => {
          const exists = nodeData.some(
            (node) => node.node_id === previous
          )

          if (exists) {
            return previous
          }

          return nodeData[0]?.node_id ?? ''
        })

        setError('')
      } catch (err) {
        if (!active) return

        setError(
          `Cannot connect to FastAPI: ${String(err)}`
        )
      }
    }

    void loadNodes()

    const timer = setInterval(() => {
      void loadNodes()
    }, 5000)

    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  // ===========================
  // FETCH SELECTED NODE DATA
  // ===========================

  useEffect(() => {
    if (!selectedNode) {
      setLatest(null)
      setHistory([])
      setReadingError('')
      return
    }

    let active = true

    setLatest(null)
    setHistory([])
    setReadingError('')

    async function loadReadings() {
      const nodeId =
        encodeURIComponent(selectedNode)

      try {
        const [latestResult, historyResult] =
          await Promise.all([
            fetch(
              `/api/nodes/${nodeId}/latest`
            ),
            getJSON<Reading[]>(
              `/api/nodes/${nodeId}/history?limit=100`
            ),
          ])

        if (!active) return

        if (latestResult.status === 404) {
          setLatest(null)
        } else {
          if (!latestResult.ok) {
            throw new Error(
              `Latest reading: HTTP ${latestResult.status}`
            )
          }

          const contentType =
            latestResult.headers.get('content-type') || ''

          if (!contentType.includes('application/json')) {
            throw new Error(
              'Latest reading API returned non-JSON data'
            )
          }

          const latestData =
            (await latestResult.json()) as Reading

          if (!active) return

          setLatest(latestData)
        }

        setHistory(historyResult)
        setReadingError('')
      } catch (err) {
        if (!active) return

        setReadingError(
          `Unable to load readings: ${String(err)}`
        )
      }
    }

    void loadReadings()

    const timer = setInterval(() => {
      void loadReadings()
    }, 5000)

    return () => {
      active = false
      clearInterval(timer)
    }
  }, [selectedNode])

  // ===========================
  // SELECTED NODE
  // ===========================

  const currentNode = nodes.find(
    (node) => node.node_id === selectedNode
  )

  const currentStatus =
    currentNode?.current_status ?? 'unknown'

  // ===========================
  // USER INTERFACE
  // ===========================

  return (
    <main className="app">

      {/* HEADER */}

      <header className="header">
        <div>
          <p className="eyebrow">
            AUTONOMOUS FIRE MONITORING SYSTEM
          </p>

          <h1>FIRE SCOUT</h1>

          <p className="muted">
            Multi-Node IoT Monitoring Dashboard
          </p>
        </div>

        <span className="refresh">
          ● Auto Refresh: 5s
        </span>
      </header>

      {/* API ERROR */}

      {error && (
        <div className="error">
          {error}
        </div>
      )}

      {/* SYSTEM OVERVIEW */}

      <section className="summary">
        <MetricCard
          label="Total Nodes"
          value={String(
            overview?.total_nodes ?? 0
          )}
          unit="Registered ESP32 Nodes"
        />

        <MetricCard
          label="Online Nodes"
          value={String(
            overview?.online_nodes ?? 0
          )}
          unit="Active Sensor Nodes"
        />

        <MetricCard
          label="Offline Nodes"
          value={String(
            overview?.offline_nodes ?? 0
          )}
          unit="Disconnected / Stale Nodes"
        />
      </section>

      {/* MULTI NODE MONITORING */}

      <NodeOverview
        nodes={nodes}
        selectedNode={selectedNode}
        onSelectNode={setSelectedNode}
      />

      {/* SELECTED NODE DETAILS */}

      <section className="card">
        <div className="node-heading">
          <div>
            <h2>
              {selectedNode || 'No Node Selected'}
            </h2>

            <p className="muted">
              Last Seen:{' '}
              {formatTime(currentNode?.last_seen)}
            </p>
          </div>

          <span
            className={`status ${
              currentStatus === 'online'
                ? 'online'
                : 'offline'
            }`}
          >
            {currentStatus.toUpperCase()}
          </span>
        </div>

        {/* SENSOR METRICS */}

        <div className="sensor-grid">
          <MetricCard
            label="Temperature"
            value={
              latest
                ? latest.temperature_c.toFixed(2)
                : '--'
            }
            unit="°C"
          />

          <MetricCard
            label="Humidity"
            value={
              latest
                ? latest.humidity_pct.toFixed(2)
                : '--'
            }
            unit="%"
          />

          <MetricCard
            label="MQ-2 Gas Sensor"
            value={
              latest
                ? String(latest.mq2_raw)
                : '--'
            }
            unit="Raw ADC (0–4095)"
          />
        </div>

        <p className="muted reading-time">
          Last Reading:{' '}
          {formatTime(latest?.received_at)}
        </p>

        {currentStatus !== 'online' && (
          <p className="muted">
            Node is not currently reporting.
            Displayed readings may be outdated.
          </p>
        )}

        {readingError && (
          <div className="error">
            {readingError}
          </div>
        )}
      </section>

      {/* SENSOR HISTORY CHARTS */}

      <section className="charts">
        <SensorChart
          data={history}
          field="temperature_c"
          title="Temperature History (°C)"
          color="#f97373"
        />

        <SensorChart
          data={history}
          field="humidity_pct"
          title="Humidity History (%)"
          color="#38bdf8"
        />

        <SensorChart
          data={history}
          field="mq2_raw"
          title="MQ-2 Raw ADC History"
          color="#fbbf24"
        />
      </section>

      {/* DATABASE INFORMATION */}

      <section
        className="card"
        style={{ marginTop: 20 }}
      >
        <h3>System Information</h3>

        <p className="muted">
          Database: SQLite (Supabase PostgreSQL planned)
        </p>

        <p className="muted">
          Backend: FastAPI
        </p>

        <p className="muted">
          Communication: Mosquitto MQTT
        </p>

        <p className="muted">
          Total Stored Readings:{' '}
          {overview?.total_readings ?? 0}
        </p>
      </section>

      {/* FOOTER */}

      <footer>
        FIRE SCOUT © 2026
        {' | '}
        ESP32 + MQTT + FastAPI + React
      </footer>

    </main>
  )
}
