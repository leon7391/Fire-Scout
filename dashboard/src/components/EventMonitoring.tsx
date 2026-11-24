
import { useEffect, useState } from 'react'
import './EventMonitoring.css'

type NodeInfo = {
  node_id: string
}

type SystemEvent = {
  id: number
  created_at: string
  node_id: string
  event_type: string
  severity: string
  message: string
  value: number | null
  threshold: number | null
  source: string
  is_simulated: number
  reading_id: number | null
}

type EventDetail = SystemEvent & {
  reading_received_at: string | null
  temperature_c: number | null
  humidity_pct: number | null
  mq2_raw: number | null
}

type Statistics = {
  period_hours: number
  node_id: string | null
  total_samples: number
  avg_temp: number | null
  min_temp: number | null
  max_temp: number | null
  avg_humidity: number | null
  min_mq2: number | null
  max_mq2: number | null
  total_events: number
  warning_events: number
}

type ActiveAlert = {
  node_id: string
  rule_code: string
  active: number
  high_count: number
  clear_count: number
  last_sample_epoch: number | null
}

type Props = {
  nodes: NodeInfo[]
}

const EVENT_TYPES = [
  { value: '', label: 'All Events' },
  { value: 'temperature_suspicious', label: 'Temperature Suspicious' },
  { value: 'temperature_normalized', label: 'Temperature Normalized' },
  { value: 'mq2_raw_suspicious', label: 'MQ-2 Suspicious' },
  { value: 'mq2_raw_normalized', label: 'MQ-2 Normalized' },
  { value: 'node_online', label: 'Node Online' },
  { value: 'node_offline', label: 'Node Offline' },
]

async function getJSON<T>(
  url: string,
  signal: AbortSignal
): Promise<T> {
  const response = await fetch(url, { signal })

  if (!response.ok) {
    throw new Error(`${url}: HTTP ${response.status}`)
  }

  const contentType = response.headers.get('content-type') ?? ''

  if (!contentType.includes('application/json')) {
    throw new Error(`${url}: Expected JSON response`)
  }

  return (await response.json()) as T
}

function formatTime(value: string | null | undefined) {
  if (!value) return '--'

  const date = new Date(value)

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('vi-VN')
}

function formatNumber(
  value: number | null | undefined,
  digits = 2
) {
  return value == null ? '--' : value.toFixed(digits)
}

function eventLabel(type: string) {
  return (
    EVENT_TYPES.find((item) => item.value === type)?.label ??
    type.replaceAll('_', ' ')
  )
}

export default function EventMonitoring({ nodes }: Props) {
  const [nodeFilter, setNodeFilter] = useState('')
  const [eventFilter, setEventFilter] = useState('')
  const [hours, setHours] = useState(24)

  const [events, setEvents] = useState<SystemEvent[]>([])
  const [stats, setStats] = useState<Statistics | null>(null)
  const [alerts, setAlerts] = useState<ActiveAlert[]>([])

  const [selectedEventId, setSelectedEventId] =
    useState<number | null>(null)
  const [eventDetail, setEventDetail] =
    useState<EventDetail | null>(null)
  const [detailError, setDetailError] = useState('')

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const eventParams = new URLSearchParams({
    hours: String(hours),
    limit: '100',
  })

  const statsParams = new URLSearchParams({
    hours: String(hours),
  })

  if (nodeFilter) {
    eventParams.set('node_id', nodeFilter)
    statsParams.set('node_id', nodeFilter)
  }

  if (eventFilter) {
    eventParams.set('event_type', eventFilter)
  }

  const exportUrl =
    `/api/events/export?${eventParams.toString()}`

  useEffect(() => {
    let active = true
    let currentRequest: AbortController | null = null

    async function loadData() {
      currentRequest?.abort()

      const controller = new AbortController()
      currentRequest = controller

      const eventQuery = new URLSearchParams({
        hours: String(hours),
        limit: '100',
      })

      const statisticsQuery = new URLSearchParams({
        hours: String(hours),
      })

      if (nodeFilter) {
        eventQuery.set('node_id', nodeFilter)
        statisticsQuery.set('node_id', nodeFilter)
      }

      if (eventFilter) {
        eventQuery.set('event_type', eventFilter)
      }

      try {
        const [newEvents, newStats, newAlerts] =
          await Promise.all([
            getJSON<SystemEvent[]>(
              `/api/events?${eventQuery.toString()}`,
              controller.signal
            ),
            getJSON<Statistics>(
              `/api/statistics?${statisticsQuery.toString()}`,
              controller.signal
            ),
            getJSON<ActiveAlert[]>(
              '/api/alerts/active',
              controller.signal
            ),
          ])

        if (!active || controller.signal.aborted) return

        setEvents(newEvents)
        setStats(newStats)
        setAlerts(newAlerts)
        setError('')
      } catch (err) {
        if (!active || controller.signal.aborted) return
        setError(String(err))
      } finally {
        if (active && !controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    setLoading(true)
    void loadData()

    const timer = window.setInterval(() => {
      void loadData()
    }, 10000)

    return () => {
      active = false
      window.clearInterval(timer)
      currentRequest?.abort()
    }
  }, [nodeFilter, eventFilter, hours])

  useEffect(() => {
    if (selectedEventId === null) {
      setEventDetail(null)
      setDetailError('')
      return
    }

    const controller = new AbortController()

    setEventDetail(null)
    setDetailError('')

    async function loadDetail() {
      try {
        const detail = await getJSON<EventDetail>(
          `/api/events/${selectedEventId}`,
          controller.signal
        )

        if (!controller.signal.aborted) {
          setEventDetail(detail)
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setDetailError(String(err))
        }
      }
    }

    void loadDetail()

    return () => controller.abort()
  }, [selectedEventId])

  const visibleAlerts = alerts.filter(
    (alert) =>
      !nodeFilter || alert.node_id === nodeFilter
  )

  return (
    <section className="card fs3-monitoring">
      <div className="fs3-header">
        <div>
          <h2>Event & Alert Monitoring</h2>
          <p className="muted">
            FIRE SCOUT Dashboard V3
          </p>
        </div>

        <span className="fs3-refresh">
          Auto Refresh: 10s
        </span>
      </div>

      <div className="fs3-filters">
        <label>
          Sensor Node
          <select
            value={nodeFilter}
            onChange={(e) => setNodeFilter(e.target.value)}
          >
            <option value="">All Nodes</option>

            {nodes.map((node) => (
              <option
                key={node.node_id}
                value={node.node_id}
              >
                {node.node_id}
              </option>
            ))}
          </select>
        </label>

        <label>
          Time Range
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
          >
            <option value={1}>Last 1 Hour</option>
            <option value={24}>Last 24 Hours</option>
            <option value={168}>Last 7 Days</option>
            <option value={720}>Last 30 Days</option>
          </select>
        </label>

        <label>
          Event Type
          <select
            value={eventFilter}
            onChange={(e) => setEventFilter(e.target.value)}
          >
            {EVENT_TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <a className="fs3-export" href={exportUrl}>
          Export CSV
        </a>
      </div>

      {error && (
        <div className="fs3-error">
          API Error: {error}
        </div>
      )}

      {loading && (
        <p className="muted">Loading monitoring data...</p>
      )}

      <h3>Sensor Statistics</h3>

      <div className="fs3-stat-grid">
        <div className="fs3-stat">
          <span>Total Samples</span>
          <strong>{stats?.total_samples ?? '--'}</strong>
        </div>

        <div className="fs3-stat">
          <span>Average Temperature</span>
          <strong>
            {formatNumber(stats?.avg_temp)}°C
          </strong>
        </div>

        <div className="fs3-stat">
          <span>Minimum Temperature</span>
          <strong>
            {formatNumber(stats?.min_temp)}°C
          </strong>
        </div>

        <div className="fs3-stat">
          <span>Maximum Temperature</span>
          <strong>
            {formatNumber(stats?.max_temp)}°C
          </strong>
        </div>

        <div className="fs3-stat">
          <span>Average Humidity</span>
          <strong>
            {formatNumber(stats?.avg_humidity)}%
          </strong>
        </div>

        <div className="fs3-stat">
          <span>Maximum MQ-2 ADC</span>
          <strong>{stats?.max_mq2 ?? '--'}</strong>
        </div>

        <div className="fs3-stat">
          <span>Total Events</span>
          <strong>{stats?.total_events ?? '--'}</strong>
        </div>

        <div className="fs3-stat">
          <span>Warning Events</span>
          <strong>{stats?.warning_events ?? '--'}</strong>
        </div>
      </div>

      <div className="fs3-section-heading">
        <h3>Active Alerts</h3>
        <span>{visibleAlerts.length} active rules</span>
      </div>

      <p className="fs3-note">
        Trạng thái cảnh báo được lưu từ lần đo gần nhất.
        Node mất kết nối có thể giữ trạng thái cũ;
        không được coi đây là kết quả đánh giá an toàn trực tiếp.
      </p>

      {visibleAlerts.length === 0 ? (
        <div className="fs3-empty">
          No active alert rules recorded.
        </div>
      ) : (
        <div className="fs3-alert-grid">
          {visibleAlerts.map((alert) => (
            <div
              className="fs3-alert"
              key={`${alert.node_id}-${alert.rule_code}`}
            >
              <strong>{alert.node_id}</strong>

              <span className="fs3-warning-badge">
                ACTIVE
              </span>

              <p>Rule: {alert.rule_code}</p>
              <p>
                Last Sample:{' '}
                {alert.last_sample_epoch == null
                  ? '--'
                  : formatTime(
                      new Date(
                        alert.last_sample_epoch * 1000
                      ).toISOString()
                    )}
              </p>
            </div>
          ))}
        </div>
      )}

      <div className="fs3-section-heading">
        <h3>Event History</h3>
        <span>{events.length} displayed events</span>
      </div>

      <div className="fs3-table-wrapper">
        <table className="fs3-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Node</th>
              <th>Event Type</th>
              <th>Severity</th>
              <th>Source</th>
              <th>Test</th>
              <th>Details</th>
            </tr>
          </thead>

          <tbody>
            {events.map((event) => (
              <tr key={event.id}>
                <td>{formatTime(event.created_at)}</td>
                <td>{event.node_id}</td>
                <td>{eventLabel(event.event_type)}</td>

                <td>
                  <span
                    className={
                      event.severity === 'warning'
                        ? 'fs3-warning-badge'
                        : 'fs3-info-badge'
                    }
                  >
                    {event.severity.toUpperCase()}
                  </span>
                </td>

                <td>{event.source}</td>

                <td>
                  {event.is_simulated
                    ? 'Simulated'
                    : 'Not marked'}
                </td>

                <td>
                  <button
                    type="button"
                    className="fs3-detail-button"
                    onClick={() =>
                      setSelectedEventId(event.id)
                    }
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {!loading && !error && events.length === 0 && (
          <p className="fs3-empty">
            No events found for the selected filters.
          </p>
        )}
      </div>

      {selectedEventId !== null && (
        <div className="fs3-detail">
          <div className="fs3-section-heading">
            <h3>Event Detail #{selectedEventId}</h3>

            <button
              type="button"
              className="fs3-detail-button"
              onClick={() => setSelectedEventId(null)}
            >
              Close
            </button>
          </div>

          {detailError && (
            <p className="fs3-error">{detailError}</p>
          )}

          {!eventDetail && !detailError && (
            <p className="muted">Loading event detail...</p>
          )}

          {eventDetail && (
            <div className="fs3-detail-content">
              <p>
                <strong>Node:</strong> {eventDetail.node_id}
              </p>
              <p>
                <strong>Event:</strong>{' '}
                {eventLabel(eventDetail.event_type)}
              </p>
              <p>
                <strong>Message:</strong>{' '}
                {eventDetail.message}
              </p>
              <p>
                <strong>Time:</strong>{' '}
                {formatTime(eventDetail.created_at)}
              </p>
              <p>
                <strong>Value / Threshold:</strong>{' '}
                {eventDetail.value ?? '--'} /{' '}
                {eventDetail.threshold ?? '--'}
              </p>
              <p>
                <strong>Temperature:</strong>{' '}
                {formatNumber(eventDetail.temperature_c)}°C
              </p>
              <p>
                <strong>Humidity:</strong>{' '}
                {formatNumber(eventDetail.humidity_pct)}%
              </p>
              <p>
                <strong>MQ-2 ADC:</strong>{' '}
                {eventDetail.mq2_raw ?? '--'}
              </p>
            </div>
          )}
        </div>
      )}

      <p className="fs3-note">
        Experimental monitoring only. Temperature
        and MQ-2 thresholds are not certified
        fire detection criteria.
      </p>
    </section>
  )
}

