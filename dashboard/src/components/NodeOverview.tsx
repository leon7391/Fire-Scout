
import { useEffect, useState } from 'react'
import './NodeOverview.css'

type NodeInfo = {
  node_id: string
  mqtt_node: string
  current_status: string
  last_seen: string | null
  connection_status: string
  sensor_health: string
  telemetry_status: string
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

type Props = {
  nodes: NodeInfo[]
  selectedNode: string
  onSelectNode: (id: string) => void
}

function formatTime(value: string | null | undefined) {
  if (!value) return 'Chưa có dữ liệu'

  const date = new Date(value)

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('vi-VN')
}

function getStatus(status: string) {
  if (status === 'online') return 'online'
  if (status === 'offline') return 'offline'
  return 'unknown'
}

function getWarnings(
  node: NodeInfo,
  reading: Reading | null,
  tempLimit: number,
  mq2Limit: number
): string[] {
  const warnings: string[] = []
  const connection = node.connection_status

  if (connection === 'offline') {
    warnings.push('ESP32 mất kết nối hoặc hết thời gian chờ')
  }

  if (connection === 'unknown') {
    warnings.push('Chưa xác định được kết nối ESP32')
  }

  if (connection === 'online') {
    if (node.sensor_health === 'fault') {
      warnings.push('SHT31 đang gặp lỗi')
    }

    if (node.telemetry_status === 'stale') {
      warnings.push('Dữ liệu cảm biến đã cũ')
    }

    if (node.telemetry_status === 'no_data') {
      warnings.push('Chưa có dữ liệu cảm biến')
    }
  }

  // Only use fresh telemetry for UI threshold warnings
  if (
    connection === 'online' &&
    node.telemetry_status === 'fresh' &&
    reading
  ) {
    if (reading.temperature_c >= tempLimit) {
      warnings.push(
        `Nhiệt độ vượt ngưỡng thử nghiệm ${tempLimit}°C`
      )
    }

    if (reading.mq2_raw >= mq2Limit) {
      warnings.push(
        `MQ-2 ADC vượt ngưỡng thử nghiệm ${mq2Limit}`
      )
    }
  }

  return warnings
}


export default function NodeOverview({
  nodes,
  selectedNode,
  onSelectNode,
}: Props) {
  const [latestByNode, setLatestByNode] = useState<
    Record<string, Reading | null>
  >({})

  const [failedNodes, setFailedNodes] = useState<string[]>([])
  const [tempLimit, setTempLimit] = useState(40)
  const [mq2Limit, setMq2Limit] = useState(2500)
  const [onlyWarnings, setOnlyWarnings] = useState(false)

  useEffect(() => {
    let active = true

    async function loadReadings() {
      const results = await Promise.all(
        nodes.map(async (node) => {
          try {
            const url = `/api/nodes/${encodeURIComponent(
              node.node_id
            )}/latest`

            const response = await fetch(url)

            if (response.status === 404) {
              return {
                id: node.node_id,
                reading: null,
                failed: false,
              }
            }

            if (!response.ok) {
              throw new Error(`HTTP ${response.status}`)
            }

            const reading =
              (await response.json()) as Reading

            return {
              id: node.node_id,
              reading,
              failed: false,
            }
          } catch {
            return {
              id: node.node_id,
              reading: null,
              failed: true,
            }
          }
        })
      )

      if (!active) return

      const next: Record<string, Reading | null> = {}

      for (const result of results) {
        next[result.id] = result.reading
      }

      setLatestByNode(next)
      setFailedNodes(
        results.filter((r) => r.failed).map((r) => r.id)
      )
    }

    void loadReadings()

    return () => {
      active = false
    }
  }, [nodes])

  const warningsByNode = new Map(
    nodes.map((node) => [
      node.node_id,
      getWarnings(
        node,
        latestByNode[node.node_id] ?? null,
        tempLimit,
        mq2Limit
      ),
    ])
  )

  const alerts = nodes.flatMap((node) =>
    (warningsByNode.get(node.node_id) ?? []).map(
      (message) => ({
        id: node.node_id,
        message,
      })
    )
  )

  const visibleNodes = nodes.filter(
    (node) =>
      !onlyWarnings ||
      (warningsByNode.get(node.node_id)?.length ?? 0) > 0
  )

  return (
    <section className="card fs-overview">
      <div className="fs-overview-header">
        <div>
          <h2>Multi-Node Monitoring</h2>
          <p className="muted">
            Giám sát tất cả ESP32 Node trong FIRE SCOUT
          </p>
        </div>

        <span className="fs-live">
          Auto refresh: 5 seconds
        </span>
      </div>

      <div className="fs-controls">
        <label className="fs-limit">
          <span>Temperature limit (°C) — test</span>
          <input
            type="number"
            min="-40"
            max="125"
            value={tempLimit}
            onChange={(e) =>
              setTempLimit(Number(e.target.value))
            }
          />
        </label>

        <label className="fs-limit">
          <span>MQ-2 raw limit — test</span>
          <input
            type="number"
            min="0"
            max="4095"
            value={mq2Limit}
            onChange={(e) =>
              setMq2Limit(Number(e.target.value))
            }
          />
        </label>

        <label className="fs-filter">
          <input
            type="checkbox"
            checked={onlyWarnings}
            onChange={(e) =>
              setOnlyWarnings(e.target.checked)
            }
          />
          Only warnings
        </label>
      </div>

      <p className="fs-note">
        Các ngưỡng này chỉ dành cho kiểm thử giao diện,
        không phải thuật toán phát hiện cháy.
      </p>

      <div className="fs-node-grid">
        {visibleNodes.map((node) => {
          const reading =
            latestByNode[node.node_id] ?? null

          const status = getStatus(node.current_status)

          const warnings =
            warningsByNode.get(node.node_id) ?? []

          const selected =
            selectedNode === node.node_id

          const hasMapPosition =
            node.map_x != null && node.map_y != null

          return (
            <button
              type="button"
              key={node.node_id}
              className={
                `fs-node-card ${selected ? 'fs-selected' : ''}`
              }
              onClick={() => onSelectNode(node.node_id)}
            >
              <div className="fs-node-top">
                <strong>{node.node_id}</strong>

                <span className={`fs-status fs-${status}`}>
                  {status.toUpperCase()}
                </span>
              </div>

              <p className="fs-node-subtitle">
                Last seen: {formatTime(node.last_seen)}
              </p>
              <p className="fs-node-subtitle">
                Connection: {node.connection_status.toUpperCase()}
              </p>

              <p className="fs-node-subtitle">
                SHT31: {node.sensor_health.toUpperCase()}
              </p>

              <p className="fs-node-subtitle">
                Telemetry: {node.telemetry_status.toUpperCase()}
              </p>

              <div className="fs-metrics">
                <div>
                  <span>Temperature</span>
                  <strong>
                    {reading
                      ? reading.temperature_c.toFixed(2)
                      : '--'}
                    °C
                  </strong>
                </div>

                <div>
                  <span>Humidity</span>
                  <strong>
                    {reading
                      ? reading.humidity_pct.toFixed(2)
                      : '--'}
                    %
                  </strong>
                </div>

                <div>
                  <span>MQ-2 ADC</span>
                  <strong>
                    {reading ? reading.mq2_raw : '--'}
                  </strong>
                </div>
              </div>

              <p className="fs-node-subtitle">
                Last reading: {
                  formatTime(reading?.received_at)
                }
              </p>

              <p className="fs-node-subtitle">
                Position: {
                  hasMapPosition
                    ? `${node.map_x}, ${node.map_y} m (${node.map_frame ?? 'map'})`
                    : 'Chưa có tọa độ'
                }
              </p>

              {failedNodes.includes(node.node_id) && (
                <div className="fs-warning">
                  Không tải được dữ liệu mới nhất
                </div>
              )}

              {warnings.map((warning, i) => (
                <div className="fs-warning" key={i}>
                  ⚠ {warning}
                </div>
              ))}

              <span className="fs-view-history">
                Xem biểu đồ lịch sử
              </span>
            </button>
          )
        })}
      </div>

      {visibleNodes.length === 0 && (
        <p className="muted">
          Không có node phù hợp với bộ lọc.
        </p>
      )}

      <div className="fs-alert-panel">
        <h3>System Notifications ({alerts.length})</h3>

        {alerts.length === 0 ? (
          <p className="muted">
            Chưa phát hiện vấn đề theo các quy tắc thử nghiệm.
          </p>
        ) : (
          <ul>
            {alerts.map((alert, i) => (
              <li key={`${alert.id}-${i}`}>
                <strong>{alert.id}:</strong> {alert.message}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

