#!/usr/bin/env python3
"""
Enhance Cluster Analysis with AI

This script uses AI to generate better cluster labels, summaries,
and actionable recommendations for each cluster of urban ideas.

Usage:
    python enhance_clusters.py
"""

import json
import os
from pathlib import Path
from collections import defaultdict

# Check for Anthropic API
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Check for OpenAI API
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


def load_data():
    """Load the graph data."""
    data_path = Path(__file__).parent / 'data' / 'connections.json'
    with open(data_path, 'r') as f:
        return json.load(f)


def detect_clusters(data):
    """
    Detect clusters using a simple community detection approach.
    Returns dict mapping cluster_id -> list of nodes.
    """
    nodes = data['nodes']
    edges = data['edges']

    # Build adjacency map
    adjacency = defaultdict(set)
    for edge in edges:
        adjacency[edge['source_id']].add(edge['target_id'])
        adjacency[edge['target_id']].add(edge['source_id'])

    # Topic keywords for initial classification
    topic_keywords = {
        'Housing': ['housing', 'home', 'apartment', 'adu', 'dwelling', 'zoning', 'residential', 'units', 'building', 'dense', 'homes'],
        'Transit': ['bus', 'subway', 'transit', 'rail', 'train', 'metro', 'transport', 'commute', 'lane'],
        'Sidewalks': ['sidewalk', 'pedestrian', 'street', 'walk', 'crosswalk', 'curb', 'wider'],
        'Safety': ['safety', 'safe', 'police', 'officer', 'crime', 'security', 'enforcement', 'cops'],
        'Green Space': ['green', 'tree', 'park', 'garden', 'nature', 'permeable', 'flood'],
        'Schools': ['school', 'student', 'children', 'kids']
    }

    # Classify each node
    def classify_node(node):
        text = (node.get('summary', '') or '').lower()
        for topic, keywords in topic_keywords.items():
            if any(kw in text for kw in keywords):
                return topic
        return 'Other'

    # Group by topic
    topic_groups = defaultdict(list)
    for node in nodes:
        node['topic'] = classify_node(node)
        topic_groups[node['topic']].append(node)

    # Subdivide topics by connectivity
    clusters = []
    cluster_id = 0

    for topic, topic_nodes in topic_groups.items():
        if len(topic_nodes) <= 2:
            clusters.append({
                'id': cluster_id,
                'topic': topic,
                'nodes': topic_nodes
            })
            cluster_id += 1
            continue

        # Find connected subgroups within topic
        visited = set()
        for node in topic_nodes:
            if node['id'] in visited:
                continue

            cluster = [node]
            visited.add(node['id'])

            # BFS to find connected nodes in same topic
            queue = [node]
            while queue:
                current = queue.pop(0)
                for neighbor_id in adjacency[current['id']]:
                    if neighbor_id in visited:
                        continue
                    neighbor = next((n for n in topic_nodes if n['id'] == neighbor_id), None)
                    if neighbor:
                        cluster.append(neighbor)
                        visited.add(neighbor_id)
                        queue.append(neighbor)

            if cluster:
                clusters.append({
                    'id': cluster_id,
                    'topic': topic,
                    'nodes': cluster
                })
                cluster_id += 1

    return clusters


def generate_cluster_analysis_anthropic(cluster, client):
    """Use Claude to analyze a cluster and generate summary."""
    ideas = [f"- @{n['username']}: {n.get('summary', 'No summary')}" for n in cluster['nodes']]
    ideas_text = "\n".join(ideas)

    prompt = f"""Analyze this cluster of urban improvement ideas from NYC residents.

Topic Category: {cluster['topic']}

Ideas in this cluster:
{ideas_text}

Please provide:
1. A concise cluster name (3-5 words) that captures the core theme
2. A one-sentence summary of what these people are advocating for
3. The key actionable recommendation for city officials (1-2 sentences)
4. The level of consensus (High/Medium/Low) - are people saying the same thing or related but different things?

Format your response as JSON:
{{
    "name": "...",
    "summary": "...",
    "action": "...",
    "consensus": "..."
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        # Extract JSON from response
        text = response.content[0].text
        # Find JSON in response
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except:
        pass

    return {
        "name": cluster['topic'],
        "summary": f"Multiple ideas related to {cluster['topic'].lower()}",
        "action": "Review and consolidate these citizen suggestions",
        "consensus": "Medium"
    }


def generate_cluster_analysis_simple(cluster):
    """Generate basic cluster analysis without AI."""
    nodes = cluster['nodes']
    summaries = [n.get('summary', '') for n in nodes if n.get('summary')]

    # Extract common words
    all_text = ' '.join(summaries).lower()
    words = all_text.split()

    # Simple name generation based on topic
    topic_names = {
        'Housing': 'Housing Development',
        'Transit': 'Transit Improvements',
        'Sidewalks': 'Pedestrian Infrastructure',
        'Safety': 'Public Safety',
        'Green Space': 'Green Infrastructure',
        'Schools': 'School Safety',
        'Other': 'Urban Improvements'
    }

    # Add specificity if possible
    name = topic_names.get(cluster['topic'], 'Urban Ideas')

    if 'staten island' in all_text:
        name = f"Staten Island {cluster['topic']}"
    elif 'bus lane' in all_text:
        name = "Bus Lane Expansion"
    elif 'wider sidewalk' in all_text or 'sidewalk width' in all_text:
        name = "Sidewalk Width Reform"
    elif 'dense' in all_text or 'density' in all_text:
        name = "Dense Development Advocacy"

    return {
        "name": name,
        "summary": f"{len(nodes)} citizens advocating for {cluster['topic'].lower()} improvements",
        "action": f"Review and prioritize these {cluster['topic'].lower()}-related suggestions",
        "consensus": "High" if len(nodes) >= 3 else "Medium"
    }


def enhance_clusters(use_ai=True):
    """Main function to enhance cluster analysis."""
    print("Loading data...")
    data = load_data()

    print("Detecting clusters...")
    clusters = detect_clusters(data)

    print(f"Found {len(clusters)} clusters")

    # Initialize AI client if available
    client = None
    if use_ai and HAS_ANTHROPIC and os.environ.get('ANTHROPIC_API_KEY'):
        client = anthropic.Anthropic()
        print("Using Claude for cluster analysis...")
    elif use_ai and HAS_OPENAI and os.environ.get('OPENAI_API_KEY'):
        print("OpenAI not implemented yet, using simple analysis...")
    else:
        print("Using simple rule-based analysis...")

    enhanced_clusters = []

    for i, cluster in enumerate(clusters):
        print(f"Analyzing cluster {i+1}/{len(clusters)}: {cluster['topic']} ({len(cluster['nodes'])} nodes)")

        if client:
            analysis = generate_cluster_analysis_anthropic(cluster, client)
        else:
            analysis = generate_cluster_analysis_simple(cluster)

        enhanced_clusters.append({
            'id': cluster['id'],
            'topic': cluster['topic'],
            'name': analysis['name'],
            'summary': analysis['summary'],
            'action': analysis['action'],
            'consensus': analysis['consensus'],
            'node_count': len(cluster['nodes']),
            'nodes': [{
                'id': n['id'],
                'username': n['username'],
                'summary': n.get('summary', ''),
                'date': n.get('date', ''),
                'link': n.get('link', '')
            } for n in cluster['nodes']]
        })

    # Save enhanced clusters
    output_path = Path(__file__).parent / 'data' / 'enhanced_clusters.json'
    with open(output_path, 'w') as f:
        json.dump({
            'total_ideas': len(data['nodes']),
            'total_clusters': len(enhanced_clusters),
            'clusters': enhanced_clusters
        }, f, indent=2)

    print(f"\nEnhanced clusters saved to {output_path}")

    # Print summary
    print("\n" + "="*60)
    print("CLUSTER SUMMARY")
    print("="*60)

    for cluster in sorted(enhanced_clusters, key=lambda x: -x['node_count']):
        print(f"\n{cluster['name']} ({cluster['node_count']} supporters)")
        print(f"  Topic: {cluster['topic']}")
        print(f"  Summary: {cluster['summary']}")
        print(f"  Action: {cluster['action']}")
        print(f"  Consensus: {cluster['consensus']}")

    return enhanced_clusters


if __name__ == "__main__":
    enhance_clusters()
