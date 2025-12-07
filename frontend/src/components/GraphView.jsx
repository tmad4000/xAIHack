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
                nodeLabel={node => node.summary} // Show full text on tooltip
                nodeCanvasObject={(node, ctx, globalScale) => {
                    const label = node.summary || '';
                    const fontSize = 12 / globalScale;
                    ctx.font = `${fontSize}px Sans-Serif`;

                    // Truncate logic
                    const maxChars = 30;
                    const text = label.length > maxChars ? label.substring(0, maxChars) + '...' : label;

                    const textWidth = ctx.measureText(text).width;
                    const bckgDimensions = [textWidth, fontSize].map(n => n + fontSize * 0.2);

                    // Draw Node
                    ctx.fillStyle = selectedNode?.id === node.id ? '#f472b6' : '#60a5fa';
                    ctx.beginPath();
                    ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI, false); // size 5
                    ctx.fill();

                    // Draw Text Background (optional, maybe just text)
                    // Let's just draw text below
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'top';
                    ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
                    ctx.fillText(text, node.x, node.y + 6);

                    // Hover interactions rely on the node geometry. 
                    // Re-use node pointer area for interaction
                    node.__bckgDimensions = bckgDimensions; // to re-use in nodePointerAreaPaint
                }}
                nodePointerAreaPaint={(node, color, ctx) => {
                    ctx.fillStyle = color;
                    ctx.beginPath();
                    ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI, false);
                    ctx.fill();
                }}

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
