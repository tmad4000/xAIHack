#!/usr/bin/env python3
"""
Add topic clusters to the graph data.
1. Build graph from connections.json
2. Detect communities (Louvain or similar)
3. Use LLM to label each community
4. Save new JSON with topic info
"""

import json
import os
import sys
import networkx as nx
from pathlib import Path
from collections import Counter

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

def load_graph_data(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def detect_communities(data):
    """Detect communities using NetworkX."""
    G = nx.Graph()
    
    # Add nodes
    for node in data['nodes']:
        G.add_node(node['id'], **node)
        
    # Add edges
    for edge in data['edges']:
        G.add_edge(edge['source_id'], edge['target_id'])
        
    # Community detection (Greedy Modularity is standard in nx w/o extra libs)
    print("Detecting communities...")
    communities = nx.community.greedy_modularity_communities(G)
    
    # Sort communities by size
    communities = sorted(communities, key=len, reverse=True)
    
    print(f"Found {len(communities)} communities.")
    return communities

def label_community(nodes, client):
    """Generate a label for a list of node objects."""
    
    # Prepare prompt text
    items_text = "\n".join([f"- {n.get('summary', '')}" for n in nodes[:15]]) # Limit to 15 items for context
    
    prompt = f"""You are analyzing a cluster of urban planning suggestions.
Here are the suggestions in this cluster:
{items_text}

What is the single specific shared topic for these items? 
Examples: "Bike Infrastructure", "Housing Density", "School Safety", "Public Transit".
Return ONLY the label (max 3 words)."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514", # Using same model as related items
        max_tokens=50,
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.content[0].text.strip().replace('"', '')

def get_fallback_label(nodes):
    """Generate a naive label based on frequent words."""
    words = []
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'be', 'this', 'that', 'it', 'city', 'nyc', 'new', 'york'}
    
    for n in nodes:
        summary = n.get('summary', '').lower()
        # Simple tokenization
        for w in summary.replace('.', '').replace(',', '').split():
            if w not in stop_words and len(w) > 3:
                words.append(w.capitalize())
                
    counts = Counter(words)
    if not counts:
        return "Group"
    
    # Get top 2 words
    top = counts.most_common(2)
    return " & ".join([t[0] for t in top])

def process_topics(data, input_file):
    client = None
    if HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY"):
         client = anthropic.Anthropic()
    else:
         print("WARNING: No Anthropic API Key found. Using fallback keyword labeling.")

    communities = detect_communities(data)
    
    # Map node ID to full node data for lookup
    node_map = {n['id']: n for n in data['nodes']}
    
    # New topic data structure
    topics = []
    
    # Update nodes with topic_id
    for idx, comm in enumerate(communities):
        if len(comm) < 2: 
             label = "Miscellaneous"
             topic_id = "misc"
        else:
            comm_nodes = [node_map[nid] for nid in comm]
            print(f"Labeling Cluster {idx+1} ({len(comm)} items)...")
            
            if client:
                try:
                    label = label_community(comm_nodes, client)
                except Exception as e:
                    print(f"Labeling failed: {e}")
                    label = get_fallback_label(comm_nodes)
            else:
                label = get_fallback_label(comm_nodes)
                
            topic_id = f"topic_{idx}"
            print(f" -> {label}")
            
        topics.append({
            "id": topic_id,
            "label": label,
            "count": len(comm),
            "color": "" # Assigned by frontend
        })
        
        # Update nodes
        for nid in comm:
            for n in data['nodes']:
                if n['id'] == nid:
                    n['topic_id'] = topic_id
                    n['topic_label'] = label
                    break
                    
    # Save output
    output_path = Path(input_file).parent / "connections_with_topics.json"
    frontend_path = Path("frontend/src/data/connections_with_topics.json")
    
    # Add topics metadata to graph object
    data['topics'] = topics
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"Saved backend data to {output_path}")
    
    if frontend_path.parent.exists():
        with open(frontend_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"Saved frontend data to {frontend_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python add_topics.py <connections.json>")
        sys.exit(1)
        
    input_file = sys.argv[1]
    data = load_graph_data(input_file)
    process_topics(data, input_file)

if __name__ == "__main__":
    main()
