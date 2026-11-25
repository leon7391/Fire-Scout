
import { useEffect, useState } from 'react'
import './RobotMap.css'

type NodeInfo = {
    node_id: string
    current_status: string
    map_id?: string | null
    map_x?: number | null
    map_y?: number | null
    map_frame?: string | null
}

type MapData =
    | {
        available: false
        status: string
    }
    | {
        available: true
        map_id: string
        frame_id: string
        width: number
        height: number
        resolution: number
        origin: [number, number, number]
        updated_at: string
        source: string
        image_url: string
    }

type Props = {
    nodes: NodeInfo[]
}

function worldToPixel(
    x: number,
    y: number,
    origin: [number, number, number],
    resolution: number,
    height: number
) {
    const dx = x - origin[0]
    const dy = y - origin[1]
    const yaw = origin[2]

    const c = Math.cos(yaw)
    const s = Math.sin(yaw)

    const localX = c * dx + s * dy
    const localY = -s * dx + c * dy

    return {
        x: localX / resolution,
        y: height - localY / resolution
    }
}

export default function RobotMap({ nodes }: Props) {
    const [map, setMap] = useState<MapData | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [zoom, setZoom] = useState(100)

    useEffect(() => {
        let active = true

        async function loadMap() {
            try {
                const response = await fetch(
                    `/api/maps/current?t=${Date.now()}`,
                    { cache: 'no-store' }
                )

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`)
                }

                const result = (await response.json()) as MapData

                if (!active) return

                setMap(result)
                setError('')
            } catch (err) {
                if (!active) return

                setError(String(err))
            } finally {
                if (active) setLoading(false)
            }
        }

        void loadMap()

        const timer = window.setInterval(() => {
            void loadMap()
        }, 15000)

        return () => {
            active = false
            window.clearInterval(timer)
        }
    }, [])

    const markers = map?.available
        ? nodes.flatMap((node) => {
            if (
                node.map_id !== map.map_id ||
                node.map_frame !== map.frame_id ||
                node.map_x == null ||
                node.map_y == null ||
                !Number.isFinite(node.map_x) ||
                !Number.isFinite(node.map_y)
            ) {
                return []
            }

            const pixel = worldToPixel(
                node.map_x,
                node.map_y,
                map.origin,
                map.resolution,
                map.height
            )

            if (
                pixel.x < 0 ||
                pixel.x > map.width ||
                pixel.y < 0 ||
                pixel.y > map.height
            ) {
                return []
            }

            return [{ node, ...pixel }]
        })
        : []

    const markerRadius = map?.available
        ? Math.max(5, Math.min(map.width, map.height) * 0.012)
        : 6

    return (
        <section className="card fs-map-panel">
            <div className="fs-map-header">
                <div>
                    <h2>LiDAR / SLAM Map</h2>
                    <p className="muted">
                        FIRE SCOUT — Robot Mapping & Sensor Locations
                    </p>
                </div>

                <span className="fs-map-status">
                    {map?.available
                        ? map.source === 'demo'
                            ? 'DEMO MAP'
                            : 'MAP LOADED'
                        : 'WAITING FOR MAP'}
                </span>
            </div>

            {error && (
                <div className="error">
                    Cannot load map: {error}
                </div>
            )}

            {loading && !map && (
                <p className="muted">Loading map status...</p>
            )}

            {!map?.available && !loading && (
                <div className="fs-map-empty">
                    <div className="fs-map-empty-icon">⌖</div>
                    <h3>No SLAM map available</h3>

                    <p>
                        Raspberry Pi 5 chưa cung cấp bản đồ.
                    </p>

                    <p className="muted">
                        Dashboard đã sẵn sàng hiển thị bản đồ
                        sau khi được lưu vào FIRE SCOUT Server.
                    </p>
                </div>
            )}

            {map?.available && (
                <>
                    <div className="fs-map-toolbar">
                        <span>
                            Frame: <strong>{map.frame_id}</strong>
                        </span>

                        <span>
                            Resolution:{' '}
                            <strong>{map.resolution} m/px</strong>
                        </span>

                        <div className="fs-map-zoom">
                            <button
                                type="button"
                                onClick={() =>
                                    setZoom((v) => Math.max(100, v - 25))
                                }
                            >
                                −
                            </button>

                            <span>{zoom}%</span>

                            <button
                                type="button"
                                onClick={() =>
                                    setZoom((v) => Math.min(250, v + 25))
                                }
                            >
                                +
                            </button>

                            <button
                                type="button"
                                onClick={() => setZoom(100)}
                            >
                                Reset
                            </button>
                        </div>
                    </div>

                    <div className="fs-map-viewport">
                        <div
                            className="fs-map-canvas"
                            style={{ width: `${zoom}%` }}
                        >
                            <svg
                                viewBox={`0 0 ${map.width} ${map.height}`}
                                role="img"
                                aria-label="FIRE SCOUT occupancy map"
                            >
                                <image
                                    href={map.image_url}
                                    x="0"
                                    y="0"
                                    width={map.width}
                                    height={map.height}
                                />

                                {markers.map(({ node, x, y }) => (
                                    <g key={node.node_id}>
                                        <circle
                                            cx={x}
                                            cy={y}
                                            r={markerRadius}
                                            fill={
                                                node.current_status === 'online'
                                                    ? '#22c55e'
                                                    : '#f97316'
                                            }
                                            stroke="#ffffff"
                                            strokeWidth={markerRadius * 0.3}
                                        />

                                        <text
                                            x={x + markerRadius * 1.5}
                                            y={y - markerRadius}
                                            fill="#38bdf8"
                                            fontSize={markerRadius * 2}
                                            stroke="#0b1220"
                                            strokeWidth="2"
                                            paintOrder="stroke"
                                        >
                                            {node.node_id}
                                        </text>
                                    </g>
                                ))}
                            </svg>
                        </div>
                    </div>

                    <div className="fs-map-details">
                        <span>
                            Map: <strong>{map.map_id}</strong>
                        </span>

                        <span>
                            Size: {map.width} × {map.height} px
                        </span>

                        <span>
                            ESP32 placed: {markers.length}
                        </span>

                        <span>
                            Updated:{' '}
                            {new Date(map.updated_at).toLocaleString('vi-VN')}
                        </span>
                    </div>

                    <p className="fs-map-note">
                        Green: Node Online · Orange: Node Offline.
                        Only nodes registered to this map are shown.
                    </p>
                </>
            )}

            <div className="fs-map-footer">
                <span>Map refresh: 15 seconds</span>
                <span>Robot pose: Not connected</span>
            </div>
        </section>
    )
}
