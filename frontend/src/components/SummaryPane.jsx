import { motion } from 'framer-motion'
import { X, ExternalLink, MessageSquare, MapPin } from 'lucide-react'

// Helper to find related nodes
const getRelatedNodes = (node, allData) => {
    if (!node || !allData) return []

    const relatedEdges = allData.edges.filter(
        e => e.source_id === node.id || e.target_id === node.id
    )

    return relatedEdges.map(edge => {
        const isSource = edge.source_id === node.id
        const otherId = isSource ? edge.target_id : edge.source_id
        const otherNode = allData.nodes.find(n => n.id === otherId)
        return {
            ...otherNode,
            reason: edge.reason,
            relationDirection: isSource ? 'outgoing' : 'incoming'
        }
    })
}

const SummaryPane = ({ node, data, onClose }) => {
    if (!node) return null

    const related = getRelatedNodes(node, data)

    return (
        <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="absolute top-0 right-0 h-full w-96 bg-slate-900/95 backdrop-blur-md border-l border-slate-700 shadow-2xl overflow-y-auto z-20"
        >
            <div className="p-6 space-y-6">
                {/* Header */}
                <div className="flex justify-between items-start">
                    <div>
                        <h2 className="text-xl font-bold text-white flex items-center gap-2">
                            {node.username}
                        </h2>
                        <span className="text-sm text-slate-400">{node.date}</span>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1 hover:bg-slate-800 rounded-full transition-colors"
                    >
                        <X size={20} className="text-slate-400" />
                    </button>
                </div>

                {/* Content */}
                <div className="bg-slate-800/50 p-4 rounded-lg border border-slate-700">
                    <p className="text-slate-200 leading-relaxed italic">
                        "{node.summary}"
                    </p>
                    {node.link && (
                        <a
                            href={node.link}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-3 text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1 inline-flex"
                        >
                            View Tweet <ExternalLink size={14} />
                        </a>
                    )}
                </div>

                <div className="h-px bg-slate-700/50 my-4" />

                {/* Related Suggestions */}
                <div>
                    <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                        <MessageSquare size={16} /> Related Suggestions
                    </h3>

                    <div className="space-y-4">
                        {related.length === 0 ? (
                            <p className="text-slate-500 text-sm">No direct connections found.</p>
                        ) : (
                            related.map((item, idx) => (
                                <div key={idx} className="group relative pl-4 border-l-2 border-slate-700 hover:border-blue-500 transition-colors">
                                    <div className="absolute -left-[5px] top-0 w-2 h-2 rounded-full bg-slate-700 group-hover:bg-blue-500 transition-colors" />

                                    <p className="text-xs font-semibold text-slate-300 mb-1">
                                        {item.reason}
                                    </p>

                                    <div className="bg-slate-800/30 p-3 rounded hover:bg-slate-800/60 transition-colors">
                                        <div className="flex justify-between items-center mb-1">
                                            <span className="text-blue-400 text-sm font-medium">{item.username}</span>
                                        </div>
                                        <p className="text-sm text-slate-400 line-clamp-3">
                                            {item.summary}
                                        </p>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>
            </div>
        </motion.div>
    )
}

export default SummaryPane
