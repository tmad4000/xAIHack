import { useState, useEffect } from 'react'
import GraphView from './components/GraphView'
import SummaryPane from './components/SummaryPane'
import { AnimatePresence } from 'framer-motion'

// Import data directly from the sibling directory might be tricky with Vite's security.
// Best to symlink or copy the data into src/ or public/.
// I'll assume we can fetch it if it's in public/ or import it if I copy it.
// For now, let's assume we copy it to src/data/connections.json

import graphData from './data/connections_with_topics.json'

function App() {
  const [selectedNode, setSelectedNode] = useState(null)

  return (
    <div className="relative w-screen h-screen bg-slate-950 overflow-hidden text-slate-100 font-sans">
      <GraphView
        data={graphData}
        onNodeClick={setSelectedNode}
        selectedNode={selectedNode}
      />

      <AnimatePresence>
        {selectedNode && (
          <SummaryPane
            node={selectedNode}
            data={graphData}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </AnimatePresence>

      <div className="absolute top-4 left-4 pointer-events-none z-10">
        <h1 className="text-2xl font-bold bg-slate-900/80 backdrop-blur px-4 py-2 rounded-lg border border-slate-700/50 shadow-xl">
          City Suggestions <span className="text-blue-400">Graph</span>
        </h1>
      </div>
    </div>
  )
}

export default App
