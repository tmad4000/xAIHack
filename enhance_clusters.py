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

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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


def get_data_path():
    """Get the path to the data directory."""
    env_path = os.environ.get('CITYVOICE_DATA_PATH')
    if env_path:
        return Path(env_path)
    return Path(__file__).parent / 'data'


def load_data():
    """Load the graph data."""
    data_path = get_data_path() / 'connections.json'
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


def extract_demands_anthropic(cluster, client):
    """
    Phase 1: Extract discrete demands from cluster and deduplicate.
    Returns list of demands with voice counts.
    """
    ideas = [f"[{n['id']}] @{n['username']}: {n.get('summary', 'No summary')}" for n in cluster['nodes']]
    ideas_text = "\n".join(ideas)

    prompt = f"""Analyze these urban improvement suggestions from NYC residents and extract the DISTINCT actionable demands.

Ideas:
{ideas_text}

Your task:
1. Identify each DISTINCT demand/suggestion (not topics, but specific asks)
2. Group semantically identical suggestions together (same demand, different words)
3. Normalize each demand to a clear, actionable description

For example:
- "wider sidewalks" and "make sidewalks bigger" = same demand
- "car-free school streets" from multiple people = one demand with multiple voices

Return JSON:
{{
    "demands": [
        {{
            "description": "Clear, normalized description of the demand",
            "tweet_ids": [1, 2, 3],
            "voices": ["@user1", "@user2"],
            "count": 2
        }}
    ]
}}

Only include actual actionable demands. Merge similar ones."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end]).get('demands', [])
    except:
        pass

    return []


def synthesize_actions_anthropic(cluster, demands, client):
    """
    Phase 2: Generate synthesized, implementable policy proposals.
    """
    if not demands:
        return []

    demands_text = "\n".join([
        f"- {d['description']} ({d['count']} voice{'s' if d['count'] > 1 else ''})"
        for d in demands
    ])

    prompt = f"""Given these citizen demands about {cluster['topic']}:

{demands_text}

Synthesize 1-3 CONCRETE, IMPLEMENTABLE policy proposals that a city council could actually vote on.

Requirements:
- Be specific: include numbers, timelines, pilot programs
- Combine related demands into unified proposals where sensible
- Make them actionable, not vague recommendations
- Include implementation mechanisms

Example good proposal:
"Launch a 'School Streets' pilot program making blocks adjacent to 10 schools car-free during drop-off (7:30-8:30am) and pick-up (2:30-3:30pm). Start Fall 2025. Evaluate safety metrics after 6 months before citywide expansion."

Example bad proposal:
"Consider making streets safer for children" (too vague)

Return JSON:
{{
    "synthesized_actions": [
        {{
            "title": "Short title (3-6 words)",
            "proposal": "Detailed implementable proposal with specifics",
            "supporting_demands": ["demand1", "demand2"],
            "voices_represented": 5
        }}
    ]
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    try:
        text = response.content[0].text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end]).get('synthesized_actions', [])
    except:
        pass

    return []


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

            # Phase 1: Extract discrete demands
            print(f"  Extracting demands...")
            demands = extract_demands_anthropic(cluster, client)

            # Phase 2: Synthesize actionable proposals
            print(f"  Synthesizing policy proposals...")
            synthesized_actions = synthesize_actions_anthropic(cluster, demands, client)
        else:
            analysis = generate_cluster_analysis_simple(cluster)
            demands = []
            synthesized_actions = []

        enhanced_clusters.append({
            'id': cluster['id'],
            'topic': cluster['topic'],
            'name': analysis['name'],
            'summary': analysis['summary'],
            'action': analysis['action'],
            'consensus': analysis['consensus'],
            'node_count': len(cluster['nodes']),
            'demands': demands,
            'synthesized_actions': synthesized_actions,
            'nodes': [{
                'id': n['id'],
                'username': n['username'],
                'summary': n.get('summary', ''),
                'date': n.get('date', ''),
                'link': n.get('link', '')
            } for n in cluster['nodes']]
        })

    # Save enhanced clusters
    output_path = get_data_path() / 'enhanced_clusters.json'
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
        print(f"  Consensus: {cluster['consensus']}")

        if cluster.get('demands'):
            print(f"  Demands ({len(cluster['demands'])}):")
            for d in cluster['demands']:
                print(f"    - {d['description']} ({d['count']} voices)")

        if cluster.get('synthesized_actions'):
            print(f"  Policy Proposals ({len(cluster['synthesized_actions'])}):")
            for action in cluster['synthesized_actions']:
                print(f"    ★ {action['title']}")
                print(f"      {action['proposal'][:100]}...")

    return enhanced_clusters


if __name__ == "__main__":
    enhance_clusters()
