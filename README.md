# CityVoice - AI-Powered Citizen Suggestion Clustering

**xAI Hackathon 2025**

CityVoice discovers and clusters citizen suggestions from social media, helping city officials understand what residents want and identify actionable improvements.

## Features

- **AI-Powered Connection Discovery**: Finds related ideas using Claude/GPT
- **Interactive Graph Visualization**: Force-directed graph with D3.js
- **Automatic Clustering**: Groups similar suggestions by topic and idea
- **Actionable Summary**: Prioritized list of citizen demands with consensus levels
- **Export Reports**: Generate markdown reports for stakeholders

## Quick Start - Visualization

```bash
# Start the visualization server
python3 server.py

# Opens browser to http://localhost:7847
```

The visualization includes:
- **Left Panel**: Interactive force-directed graph with zoom/pan
- **Right Panel**: Clusters, actionable items, and node details
- **Legend**: Topic-based color coding with counts
- **Search**: Filter nodes by keyword
- **Export**: Download consolidated markdown report

## Generate Connection Data

```bash
# Install dependencies
pip install anthropic

# Set API key
export ANTHROPIC_API_KEY="your-key-here"

# Run the analysis script
python find_related_items.py data/geodatanyc.csv

# Enhance clusters with AI-generated summaries (optional)
python enhance_clusters.py
```

## Output Files

The script generates two output files in the same directory as the input:

- **`connections.csv`** - Simple edge list with columns:
  - `source_id`: ID of the source item
  - `target_id`: ID of the related item
  - `reason`: AI-generated explanation of the relationship

- **`connections.json`** - Full graph data with:
  - `nodes`: Array of all items with metadata
  - `edges`: Array of all connections with reasons

## Usage Options

```bash
# Use Anthropic (default)
python find_related_items.py data/geodatanyc.csv

# Use OpenAI instead
pip install openai
export OPENAI_API_KEY="your-key-here"
python find_related_items.py data/geodatanyc.csv --provider openai

# Lightweight keyword matching fallback (no API keys required)
python find_related_items.py data/geodatanyc.csv --provider keyword
```

## How It Works

1. Loads CSV with columns: Date, Username, Summary/Quote, Link
2. For each item, asks AI to find the top 3-5 most related items
3. AI considers: topic overlap, complementary/conflicting solutions, geographic focus
4. Outputs connection data for graph visualization

## Context Window Threshold

- **≤100 items**: Uses full context window (current approach)
- **>100 items**: Should use embeddings for efficiency (see `PLAN_EMBEDDINGS.md`)

## Data Format

Input CSV should have these columns:
```
Date,Username,Summary/Quote,Link
2025-12-05,@NYCPlanning,ADUs are a proven way to create housing...,https://x.com/...
```

If neither Anthropic nor OpenAI credentials are available, the relation finder automatically falls back to a keyword-overlap heuristic so clustering can still run (albeit with simpler reasoning).

## Gather Fresh Posts with Grok X Search

Use `grok_x_search.py` (requires `pip install "xai-sdk>=1.3.1"`) to have Grok search X with the official `x_search` tool and dump detailed CSV rows that match the `Date,Username,Summary/Quote,Link` format.

```bash
# Set your xAI key (or store it in .env)
export XAI_API_KEY=sk-...

python grok_x_search.py \
  --location "San Francisco transit" \
  --count 12 \
  --from-date 2024-06-01 \
  --csv-out data/grok_sf_transit.csv \
  --json-out data/grok_sf_transit.json
```

- `--csv-out` writes exactly what Grok streams (header + rows) so you can drop it into the visualization pipeline.
- `--json-out` stores the assistant response, citations, and token usage for auditing.
- Extra flags allow handle whitelists (`--allowed-handles`), exclusions, or date filters to match civic research needs.
