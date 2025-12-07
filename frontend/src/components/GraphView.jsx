import { useRef, useEffect, useMemo, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'


// Simple hook for window size in the same file to save time/files
const useWindowDimensions = () => {
    const [windowDimensions, setWindowDimensions] = useState({
        width: window.innerWidth,
        height: window.innerHeight
    })

    useEffect(() => {
        function handleResize() {
            setWindowDimensions({
                width: window.innerWidth,
                height: window.innerHeight
            })
        }
        window.addEventListener('resize', handleResize)
        return () => window.removeEventListener('resize', handleResize)
    }, [])

    return windowDimensions
}

import { useState } from 'react'

const GraphView = ({ data, onNodeClick, selectedNode }) => {
    const fgRef = useRef()
    const { width, height } = useWindowDimensions()

    // Process data to ensure valid structure
    const graphData = useMemo(() => {
        if (!data) return { nodes: [], edges: [] }

        // Clone to avoid mutation issues with force-graph
        const nodes = data.nodes.map(node => ({
            ...node,
            // Add visual properties
            val: node.connections?.length || 5, // Size
            color: '#60a5fa' // blue-400
        }))

        const links = data.edges.map(edge => ({
            source: edge.source_id,
            target: edge.target_id,
            reason: edge.reason
        }))

        return { nodes, links }
    }, [data])

    useEffect(() => {
        // Initial camera position
        if (fgRef.current) {
            fgRef.current.d3Force('charge').strength(-100)
        }
    }, [])

    // Highlight handled by react-force-graph props often, but we can do custom painting

    return (
        <div className="w-full h-full">
            <ForceGraph2D
                ref={fgRef}
                width={width}
                height={height}
                graphData={graphData}
                nodeLabel="username"
                nodeColor={node => selectedNode?.id === node.id ? '#f472b6' : '#60a5fa'} // Pink if selected, Blue otherwise
                nodeRelSize={6}
                linkLabel="reason"
                linkWidth={1.5}
                linkDirectionalParticles={2}
                linkDirectionalParticleSpeed={0.005}
                linkColor={() => 'rgba(148, 163, 184, 0.4)'} // Slate 400 with opacity
                onNodeClick={(node) => {
                    // Zoom to node?
                    fgRef.current.centerAt(node.x, node.y, 1000)
                    fgRef.current.zoom(4, 2000)
                    onNodeClick(node)
                }}
                onBackgroundClick={() => onNodeClick(null)}
                backgroundColor="#0f172a"
            />
        </div>
    )
}

export default GraphView
