#!/usr/bin/env python3
"""
Find related items in a CSV of suggestions/issues using AI.

For small datasets (≤100 items): Uses full context window approach
For large datasets (>100 items): See PLAN_EMBEDDINGS.md for future approach

Usage:
    python find_related_items.py data/geodatanyc.csv

Output:
    - data/connections.csv: CSV with source_id, target_id, relationship_reason
    - data/connections.json: Full graph data with items and edges
"""

import csv
import json
import os
import re
import sys
from pathlib import Path

# Try to import AI libraries
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

CONTEXT_WINDOW_THRESHOLD = 100  # Switch to embeddings above this

STOPWORDS = {
    'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'was', 'were', 'have', 'has',
    'had', 'but', 'not', 'you', 'your', 'our', 'their', 'they', 'them', 'his', 'her', 'its',
    'into', 'onto', 'about', 'after', 'before', 'over', 'under', 'between', 'across', 'into',
    'more', 'less', 'than', 'then', 'also', 'will', 'would', 'could', 'should', 'can', 'may',
    'might', 'just', 'like', 'time', 'year', 'month', 'city', 'new', 'york', 'san', 'francisco',
    'make', 'need', 'want', 'much', 'many', 'some', 'most', 'other', 'same', 'very', 'really'
}


def load_csv(filepath: str) -> list[dict]:
    """Load CSV file and return list of dicts with id added.

    Handles CSV files where Summary/Quote field contains commas but isn't quoted.
    Uses the URL pattern (https://) to properly detect the Link column.
    """
    items = []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if not lines:
        return items

    # Parse header
    header = lines[0].strip().split(',')

    for i, line in enumerate(lines[1:], start=1):
        line = line.strip()
        if not line:
            continue

        # Find the URL (Link column) - it starts with https://
        url_match_pos = line.find('https://')
        if url_match_pos == -1:
            url_match_pos = line.find('http://')

        if url_match_pos != -1:
            # Everything before the URL (minus the comma) is the first 3 columns
            before_url = line[:url_match_pos].rstrip(',')
            url = line[url_match_pos:]

            # Split the part before URL - we expect: Date,Username,Summary/Quote
            # Find first two commas to separate Date and Username
            first_comma = before_url.find(',')
            if first_comma != -1:
                date = before_url[:first_comma]
                rest = before_url[first_comma + 1:]
                second_comma = rest.find(',')
                if second_comma != -1:
                    username = rest[:second_comma]
                    summary = rest[second_comma + 1:]
                else:
                    username = rest
                    summary = ""
            else:
                date = before_url
                username = ""
                summary = ""

            items.append({
                'id': i,
                'Date': date.strip(),
                'Username': username.strip(),
                'Summary/Quote': summary.strip(),
                'Link': url.strip()
            })
        else:
            # No URL found, fall back to simple split (might be incomplete data)
            parts = line.split(',')
            items.append({
                'id': i,
                'Date': parts[0] if len(parts) > 0 else '',
                'Username': parts[1] if len(parts) > 1 else '',
                'Summary/Quote': ','.join(parts[2:-1]) if len(parts) > 3 else (parts[2] if len(parts) > 2 else ''),
                'Link': parts[-1] if len(parts) > 3 else ''
            })

    return items


def format_items_for_prompt(items: list[dict]) -> str:
    """Format items as numbered list for AI prompt."""
    lines = []
    for item in items:
        lines.append(f"[{item['id']}] @{item['Username']}: {item['Summary/Quote']}")
    return "\n".join(lines)


def find_relations_anthropic(items: list[dict], target_item: dict) -> list[dict]:
    """Use Anthropic Claude to find related items."""
    client = anthropic.Anthropic()

    items_text = format_items_for_prompt(items)

    prompt = f"""You are analyzing urban planning suggestions/issues from Twitter.

Here are all the items:
{items_text}

For item [{target_item['id']}] "@{target_item['Username']}: {target_item['Summary/Quote']}"

Find the TOP 3-5 most related items from the list. Items are related if they:
- Address the same topic (housing, transit, sidewalks, safety, etc.)
- Propose complementary or conflicting solutions
- Could be combined into a larger initiative
- Share geographic focus

Respond in JSON format only:
{{
  "related": [
    {{"id": <number>, "reason": "<brief reason for relation>"}},
    ...
  ]
}}

Only include items that have meaningful connections. If fewer than 3 items are related, that's fine."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse JSON from response
    text = response.content[0].text
    # Handle potential markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    result = json.loads(text.strip())
    return result.get("related", [])


def find_relations_openai(items: list[dict], target_item: dict) -> list[dict]:
    """Use OpenAI to find related items."""
    client = openai.OpenAI()

    items_text = format_items_for_prompt(items)

    prompt = f"""You are analyzing urban planning suggestions/issues from Twitter.

Here are all the items:
{items_text}

For item [{target_item['id']}] "@{target_item['Username']}: {target_item['Summary/Quote']}"

Find the TOP 3-5 most related items from the list. Items are related if they:
- Address the same topic (housing, transit, sidewalks, safety, etc.)
- Propose complementary or conflicting solutions
- Could be combined into a larger initiative
- Share geographic focus

Respond in JSON format only:
{{
  "related": [
    {{"id": <number>, "reason": "<brief reason for relation>"}},
    ...
  ]
}}

Only include items that have meaningful connections. If fewer than 3 items are related, that's fine."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    return result.get("related", [])


def tokenize_summary(text: str) -> set[str]:
    """Tokenize summary text into meaningful keywords."""
    tokens = re.findall(r"[a-z0-9']+", (text or "").lower())
    keywords = {
        token.strip("'")
        for token in tokens
        if len(token.strip("'")) >= 3 and token not in STOPWORDS
    }
    return keywords


def find_relations_keyword(items: list[dict], target_item: dict) -> list[dict]:
    """Fallback relation finder using keyword overlap (no external API)."""
    target_tokens = tokenize_summary(target_item.get('Summary/Quote', ''))
    if not target_tokens:
        return []

    similarities = []
    for item in items:
        if item['id'] == target_item['id']:
            continue
        candidate_tokens = tokenize_summary(item.get('Summary/Quote', ''))
        if not candidate_tokens:
            continue
        overlap = target_tokens & candidate_tokens
        if not overlap:
            continue
        score = len(overlap) / min(len(target_tokens), len(candidate_tokens))
        similarities.append((score, overlap, item))

    similarities.sort(key=lambda x: x[0], reverse=True)
    top_matches = similarities[:5]

    relations = []
    for score, overlap, item in top_matches:
        reason_keywords = ", ".join(sorted(overlap))
        relations.append({
            "id": item['id'],
            "reason": f"Shares keywords: {reason_keywords}"
        })

    return relations


def find_all_relations(items: list[dict], provider: str = "anthropic") -> list[dict]:
    """Find relations for all items."""
    if len(items) > CONTEXT_WINDOW_THRESHOLD:
        print(f"WARNING: {len(items)} items exceeds threshold of {CONTEXT_WINDOW_THRESHOLD}.")
        print("Consider implementing embeddings approach (see PLAN_EMBEDDINGS.md)")

    if provider == "anthropic":
        find_fn = find_relations_anthropic
    elif provider == "openai":
        find_fn = find_relations_openai
    elif provider == "keyword":
        find_fn = find_relations_keyword
    else:
        raise ValueError(f"Unsupported provider '{provider}'. Expected anthropic, openai, or keyword.")

    all_connections = []

    for i, item in enumerate(items):
        pct = int((i / len(items)) * 100)
        print(f"[{pct:3d}%] Processing item {i+1}/{len(items)}: @{item['Username']}...")
        sys.stdout.flush()

        try:
            relations = find_fn(items, item)
            for rel in relations:
                all_connections.append({
                    "source_id": item['id'],
                    "target_id": rel['id'],
                    "reason": rel['reason']
                })
        except Exception as e:
            print(f"  Error: {e}")
            continue

    return all_connections


def save_connections_csv(connections: list[dict], filepath: str):
    """Save connections to CSV file."""
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['source_id', 'target_id', 'reason'])
        writer.writeheader()
        writer.writerows(connections)
    print(f"Saved {len(connections)} connections to {filepath}")


def save_full_graph(items: list[dict], connections: list[dict], filepath: str):
    """Save full graph data as JSON."""
    graph = {
        "nodes": [
            {
                "id": item['id'],
                "username": item['Username'],
                "summary": item['Summary/Quote'],
                "date": item['Date'],
                "link": item['Link']
            }
            for item in items
        ],
        "edges": connections
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2)
    print(f"Saved full graph to {filepath}")


def load_from_connections_json(filepath: str) -> list[dict]:
    """Load items from an existing connections.json file.

    Converts from connections.json format (lowercase keys) to CSV format
    (capitalized keys) for compatibility with the rest of the codebase.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Convert to CSV-style format expected by the rest of the code
    items = []
    for node in data.get('nodes', []):
        items.append({
            'id': node.get('id'),
            'Username': node.get('username', ''),
            'Summary/Quote': node.get('summary', ''),
            'Date': node.get('date', ''),
            'Link': node.get('link', '')
        })
    return items


def update_connections_json(filepath: str, connections: list[dict]):
    """Update an existing connections.json file with new edges.

    Only updates if connections were found - prevents wiping existing edges on failure.
    """
    if not connections:
        print("Warning: No connections found, preserving existing edges")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Convert connections to edges format
    edges = []
    for conn in connections:
        edges.append({
            'source_id': conn['source_id'],
            'target_id': conn['target_id'],
            'reason': conn['reason']
        })

    data['edges'] = edges

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    print(f"Updated {filepath} with {len(edges)} edges")


def main():
    # Check for CITYVOICE_DATA_PATH environment variable (for project support)
    data_path = os.environ.get('CITYVOICE_DATA_PATH')

    # Parse provider argument
    provider = "anthropic"
    if "--provider" in sys.argv:
        idx = sys.argv.index("--provider")
        if idx + 1 < len(sys.argv):
            provider = sys.argv[idx + 1]

    # Auto provider selection if requested
    provider = os.environ.get('CITYVOICE_RELATION_PROVIDER', provider)

    # Check API availability and fall back to keyword matching if necessary
    if provider == "anthropic":
        if not HAS_ANTHROPIC:
            print("Warning: anthropic library not installed. Falling back to keyword matching.")
            provider = "keyword"
        elif not os.environ.get("ANTHROPIC_API_KEY"):
            print("Warning: ANTHROPIC_API_KEY not set. Falling back to keyword matching.")
            provider = "keyword"
    elif provider == "openai":
        if not HAS_OPENAI:
            print("Warning: openai library not installed. Falling back to keyword matching.")
            provider = "keyword"
        elif not os.environ.get("OPENAI_API_KEY"):
            print("Warning: OPENAI_API_KEY not set. Falling back to keyword matching.")
            provider = "keyword"

    if provider not in {"anthropic", "openai", "keyword"}:
        print(f"Warning: Unknown provider '{provider}', using keyword fallback.")
        provider = "keyword"

    if data_path:
        # Project mode: read from connections.json
        connections_file = Path(data_path) / "connections.json"
        print(f"Loading from project: {connections_file}...")
        items = load_from_connections_json(str(connections_file))
        print(f"Loaded {len(items)} items")

        if len(items) < 2:
            print("Need at least 2 items to find connections")
            sys.exit(0)

        print(f"\nFinding relations using {provider}...")
        connections = find_all_relations(items, provider)

        # Update the connections.json with edges
        update_connections_json(str(connections_file), connections)
        print(f"\nDone! Found {len(connections)} connections.")
    else:
        # Legacy mode: read from CSV file
        if len(sys.argv) < 2:
            print("Usage: python find_related_items.py <input.csv> [--provider anthropic|openai]")
            print("Or set CITYVOICE_DATA_PATH environment variable for project mode")
            sys.exit(1)

        input_file = sys.argv[1]
        print(f"Loading {input_file}...")
        items = load_csv(input_file)
        print(f"Loaded {len(items)} items")

        print(f"\nFinding relations using {provider}...")
        connections = find_all_relations(items, provider)

        # Determine output paths
        input_path = Path(input_file)
        output_dir = input_path.parent

        csv_output = output_dir / "connections.csv"
        json_output = output_dir / "connections.json"

        save_connections_csv(connections, str(csv_output))
        save_full_graph(items, connections, str(json_output))

        print(f"\nDone! Found {len(connections)} connections.")


if __name__ == "__main__":
    main()
