
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
import './index.css'

type NodeInfo = {
  node_id: string
  mqtt_node: string
  status: string
  current_status: string
  last_seen: string | null
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

type SensorKey = 'temperature_c' | 'humidity_pct' | 'mq2_raw'

async function getJSON<T>(url: string): Promise<T> {
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  return response.json() as Promise<T>
}

function formatTime(value?: string | null) {
  if (!value) return 'Chưa có dữ liệu'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString('vi-VN')
}

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
      <span className="muted">{label}</span>
      <strong>{value}</strong>
      <span className="muted">{unit}</span>
    </div>
  )
}

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
        <p className="muted">Chưa có dữ liệu lịch sử</p>
      ) : (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="#273244" />
              <XAxis
                dataKey="received_at"
                tickFormatter={(v) =>
                  new Date(v).toLocaleTimeString('vi-VN')
                }
                stroke="#93a4b8"
                minTickGap={30}
                fontSize={11}
              />
              <YAxis
                stroke="#93a4b8"
                width={45}
                domain={['auto', 'auto']}
                fontSize={11}
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

export default function App() {
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [overview, setOverview] = useState<Overview | null>(null)
  const [selectedNode, setSelectedNode] = useState('')
  const [latest, setLatest] = useState<Reading | null>(null)
  const [history, setHistory] = useState<Reading[]>([])
  const [error, setError] = useState('')

  // Refresh node list and system overview
  useEffect(() => {
    let active = true

    async function loadNodes() {
      try {
        const [nodeData, overviewData] = await Promise.all([
          getJSON<NodeInfo[]>('/api/nodes'),
          getJSON<Overview>('/api/overview'),
        ])

        if (!active) return

        setNodes(nodeData)
        setOverview(overviewData)
        setSelectedNode((previous) =>
          nodeData.some((n) => n.node_id === previous)
            ? previous
            : (nodeData[0]?.node_id ?? '')
        )
        setError('')
      } catch (err) {
        if (active) {
          setError(`Không kết nối được FastAPI: ${String(err)}`)
        }
      }
    }

    void loadNodes()
    const timer = setInterval(loadNodes, 5000)

    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  // Refresh selected node readings
  useEffect(() => {
    if (!selectedNode) {
      setLatest(null)
      setHistory([])
      return
    }

    let active = true
    setLatest(null)
    setHistory([])

    async function loadReadings() {
      const id = encodeURIComponent(selectedNode)

      try {
        const [latestData, historyData] = await Promise.all([
          getJSON<Reading>(`/api/nodes/${id}/latest`),
          getJSON<Reading[]>(
            `/api/nodes/${id}/history?limit=100`
          ),
        ])

        if (!active) return

        setLatest(latestData)
        setHistory(historyData)
      } catch (err) {
        if (active) {
          console.error('Unable to load sensor readings', err)
        }
      }
    }

    void loadReadings()
    const timer = setInterval(loadReadings, 5000)

    return () => {
      active = false
      clearInterval(timer)
    }
  }, [selectedNode])

  const currentNode = nodes.find(
    (node) => node.node_id === selectedNode
  )

  return (
    <main className="app">
      <header className="header">
        <div>
          <p className="eyebrow">IoT FIRE MONITORING SYSTEM</p>
          <h1>FIRE SCOUT</h1>
          <p className="muted">
            ESP32 Sensor Network — Monitoring Dashboard
          </p>
        </div>
        <span className="refresh">● Auto refresh: 5s</span>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="summary">
        <MetricCard
          label="Total Nodes"
          value={String(overview?.total_nodes ?? 0)}
          unit="ESP32 devices"
        />
        <MetricCard
          label="Online Nodes"
          value={String(overview?.online_nodes ?? 0)}
          unit="Connected / sending"
        />
        <MetricCard
          label="Total Records"
          value={String(overview?.total_readings ?? 0)}
          unit="Sensor readings"
        />
      </section>

      <section className="card node-selector">
        <div>
          <h2>Sensor Nodes</h2>
          <p className="muted">
            Chọn node để xem dữ liệu cảm biến
          </p>
        </div>

        <select
          value={selectedNode}
          onChange={(event) =>
            setSelectedNode(event.target.value)
          }
        >
          {nodes.length === 0 && (
            <option value="">Không có node</option>
          )}
          {nodes.map((node) => (
            <option key={node.node_id} value={node.node_id}>
              {node.node_id}
            </option>
          ))}
        </select>
      </section>

      <section className="card">
        <div className="node-heading">
          <div>
            <h2>{selectedNode || 'No Node Selected'}</h2>
            <p className="muted">
              Last seen: {formatTime(currentNode?.last_seen)}
            </p>
          </div>
          <span
            className={`status ${
              currentNode?.current_status === 'online'
                ? 'online'
                : 'offline'
            }`}
          >
            {currentNode?.current_status ?? 'unknown'}
          </span>
        </div>

        <div className="sensor-grid">
          <MetricCard
            label="Temperature"
            value={
              latest ? latest.temperature_c.toFixed(2) : '--'
            }
            unit="°C"
          />
          <MetricCard
            label="Humidity"
            value={
              latest ? latest.humidity_pct.toFixed(2) : '--'
            }
            unit="%"
          />
          <MetricCard
            label="MQ-2"
            value={latest ? String(latest.mq2_raw) : '--'}
            unit="Raw ADC (0–4095)"
          />
        </div>

        <p className="muted reading-time">
          Last reading: {formatTime(latest?.received_at)}
        </p>
      </section>

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
          title="MQ-2 Raw History"
          color="#fbbf24"
        />
      </section>

      <footer>
        FIRE SCOUT • FastAPI + SQLite • React Dashboard V1
      </footer>
    </main>
  )
}

