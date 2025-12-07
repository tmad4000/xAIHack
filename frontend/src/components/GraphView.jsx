import { useRef, useEffect, useMemo, useState, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { Settings2 } from 'lucide-react'
import * as d3 from 'd3'

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

const GraphView = ({ data, onNodeClick, selectedNode }) => {
    const fgRef = useRef()
    const { width, height } = useWindowDimensions()
    const [chargeStrength, setChargeStrength] = useState(-300)
    const [linkDistance, setLinkDistance] = useState(50)
    const [collisionSpacing, setCollisionSpacing] = useState(10)
    const [hoveredNode, setHoveredNode] = useState(null)

    // Constants for fixed world-space sizing
    const FIXED_FONT_SIZE = 4;
    const WRAP_CHARS = 20; // narrower wrap for world space

    // Process data to ensure valid structure
    const graphData = useMemo(() => {
        if (!data) return { nodes: [], edges: [] }

        // Clone to avoid mutation issues with force-graph
        const nodes = data.nodes.map(node => {
            // Estimate dimensions for collision
            const label = node.summary || '';
            const charWidth = FIXED_FONT_SIZE * 0.6;
            const lineVal = Math.min(label.length, WRAP_CHARS);
            const estWidth = lineVal * charWidth + (FIXED_FONT_SIZE * 2); // padding
            const numLines = Math.min(3, Math.ceil(label.length / WRAP_CHARS));
            const estHeight = (numLines * FIXED_FONT_SIZE * 1.2) + (FIXED_FONT_SIZE * 2);

            // Radius covering the box
            const radius = Math.hypot(estWidth / 2, estHeight / 2);

            return {
                ...node,
                val: node.connections?.length || 5, // Size
                radius: radius
            }
        })

        const links = data.edges.map(edge => ({
            source: edge.source_id,
            target: edge.target_id,
            reason: edge.reason
        }))

        return { nodes, links }
    }, [data])

    // Update forces when controls change
    useEffect(() => {
        if (fgRef.current) {
            // Charge
            fgRef.current.d3Force('charge').strength(chargeStrength)

            // Link
            fgRef.current.d3Force('link').distance(linkDistance)

            // Collision
            // basic radius + user spacing
            fgRef.current.d3Force('collide', d3.forceCollide().radius(n => n.radius + collisionSpacing).iterations(2))

            fgRef.current.d3ReheatSimulation()
        }
    }, [chargeStrength, linkDistance, collisionSpacing, graphData])

    const drawNode = useCallback((node, ctx, globalScale) => {
        const isHovered = hoveredNode?.id === node.id;
        const isSelected = selectedNode?.id === node.id;

        const label = node.summary || '';
        const fontSize = FIXED_FONT_SIZE; // Fixed world size
        const lineHeight = fontSize * 1.2;
        const padding = 4;

        // Expand width on hover
        const wrapChars = isHovered ? WRAP_CHARS * 1.5 : WRAP_CHARS;
        const maxWid = fontSize * 0.6 * wrapChars + (padding * 2);
        const borderRadius = 2;

        ctx.font = `${fontSize}px Sans-Serif`;

        // Wrap text logic
        const words = label.split(' ');
        let lines = [];
        let currentLine = words[0];

        for (let i = 1; i < words.length; i++) {
            const word = words[i];
            const width = ctx.measureText(currentLine + " " + word).width;
            if (width < maxWid - (padding * 2)) {
                currentLine += " " + word;
            } else {
                lines.push(currentLine);
                currentLine = word;
            }
        }
        lines.push(currentLine);

        // Truncate if too many lines AND not hovered
        const maxLines = isHovered ? Infinity : 3;
        if (lines.length > maxLines) {
            lines = lines.slice(0, maxLines);
            lines[maxLines - 1] += "...";
        }

        // Recalculate exact dimensions based on actual render
        // (Optimization: could store this back to node for next frame pointer area)
        const boxWidth = maxWid;
        const boxHeight = (lines.length * lineHeight) + (padding * 2);

        // Centering offset
        const x = node.x - (boxWidth / 2);
        const y = node.y - (boxHeight / 2);

        // Draw Box
        ctx.beginPath();
        ctx.moveTo(x + borderRadius, y);
        ctx.lineTo(x + boxWidth - borderRadius, y);
        ctx.quadraticCurveTo(x + boxWidth, y, x + boxWidth, y + borderRadius);
        ctx.lineTo(x + boxWidth, y + boxHeight - borderRadius);
        ctx.quadraticCurveTo(x + boxWidth, y + boxHeight, x + boxWidth - borderRadius, y + boxHeight);
        ctx.lineTo(x + borderRadius, y + boxHeight);
        ctx.quadraticCurveTo(x, y + boxHeight, x, y + boxHeight - borderRadius);
        ctx.lineTo(x, y + borderRadius);
        ctx.quadraticCurveTo(x, y, x + borderRadius, y);
        ctx.closePath();

        // Fill Style
        if (isSelected) {
            ctx.fillStyle = '#be185d'; // Pink-700
        } else if (isHovered) {
            ctx.fillStyle = '#1e293b'; // Slate-800 (slightly lighter than 900)
        } else {
            ctx.fillStyle = 'rgba(30, 41, 59, 0.95)'; // Slate-900 with opacity
        }

        // Shadow & Stroke
        if (isSelected || isHovered) {
            ctx.shadowColor = isSelected ? '#f472b6' : '#94a3b8'; // Pink or Slate
            ctx.shadowBlur = 15;
            ctx.strokeStyle = isSelected ? '#fbcfe8' : '#e2e8f0'; // Light Pink or Slate-200
            // Bring to front hack: render later?
            // We can't change order easily here, but shadow helps visibility.
        } else {
            ctx.shadowColor = 'transparent';
            ctx.shadowBlur = 0;
            ctx.strokeStyle = '#475569';
        }

        ctx.fill();
        ctx.lineWidth = 0.5; // Thinner line for world space
        ctx.stroke();

        // Reset shadow
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;

        // Draw Text
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillStyle = (isSelected || isHovered) ? '#ffffff' : '#e2e8f0';

        lines.forEach((line, i) => {
            ctx.fillText(line, x + padding, y + padding + (i * lineHeight));
        });

        // Store dimensions for pointer area
        node.__bckgDimensions = [boxWidth, boxHeight];
    }, [selectedNode, hoveredNode])

    return (
        <div className="relative w-full h-full">
            <ForceGraph2D
                ref={fgRef}
                width={width}
                height={height}
                graphData={graphData}
                nodeLabel={() => ''} // Disable default tooltip
                onNodeHover={setHoveredNode} // Track hover
                nodeCanvasObject={drawNode}
                nodePointerAreaPaint={(node, color, ctx) => {
                    const dims = node.__bckgDimensions || [20, 20];
                    const boxWidth = dims[0];
                    const boxHeight = dims[1];
                    const x = node.x - (boxWidth / 2);
                    const y = node.y - (boxHeight / 2);

                    ctx.fillStyle = color;
                    ctx.fillRect(x, y, boxWidth, boxHeight);
                }}
                linkLabel="reason"
                linkWidth={0.5}
                linkDirectionalParticles={2}
                linkDirectionalParticleSpeed={0.005}
                linkColor={() => 'rgba(148, 163, 184, 0.4)'} // Slate 400 with opacity
                onNodeClick={(node) => {
                    // Zoom to node?
                    fgRef.current.centerAt(node.x, node.y, 1000)
                    fgRef.current.zoom(8, 2000)
                    onNodeClick(node)
                }}
                onBackgroundClick={() => onNodeClick(null)}
                backgroundColor="#0f172a"
            />

            {/* Controls Overlay */}
            <div className="absolute bottom-6 left-6 bg-slate-900/90 backdrop-blur border border-slate-700 p-4 rounded-lg shadow-xl w-64 text-sm z-10">
                <h3 className="flex items-center gap-2 font-semibold text-slate-200 mb-4 border-b border-slate-700 pb-2">
                    <Settings2 size={16} /> Simulation
                </h3>

                <div className="space-y-4">
                    <div>
                        <div className="flex justify-between mb-1 text-xs text-slate-400">
                            <span>Repulsion</span>
                            <span>{chargeStrength}</span>
                        </div>
                        <input
                            type="range"
                            min="-1000"
                            max="-50"
                            value={chargeStrength}
                            onChange={(e) => setChargeStrength(Number(e.target.value))}
                            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                        />
                    </div>

                    <div>
                        <div className="flex justify-between mb-1 text-xs text-slate-400">
                            <span>Link Distance</span>
                            <span>{linkDistance}</span>
                        </div>
                        <input
                            type="range"
                            min="10"
                            max="200"
                            value={linkDistance}
                            onChange={(e) => setLinkDistance(Number(e.target.value))}
                            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                        />
                    </div>

                    <div>
                        <div className="flex justify-between mb-1 text-xs text-slate-400">
                            <span>Collision Spacing</span>
                            <span>{collisionSpacing}</span>
                        </div>
                        <input
                            type="range"
                            min="0"
                            max="50"
                            value={collisionSpacing}
                            onChange={(e) => setCollisionSpacing(Number(e.target.value))}
                            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                        />
                    </div>
                </div>
            </div>
        </div>
    )
}

export default GraphView
