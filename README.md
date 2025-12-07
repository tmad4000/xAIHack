# xAI Hack - Related Issues Graph

Find related suggestions/issues from locality-based tweet collections using AI.

## Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install anthropic

# Set API key
export ANTHROPIC_API_KEY="your-key-here"
```

## Scripts

### 1. `find_related_items.py` - Find Related Items

**Purpose:** Analyzes a CSV of suggestions/issues and uses AI to find semantically related items, outputting a connection graph.

**Usage:**
```bash
python find_related_items.py <input.csv> [--provider anthropic|openai]
```

**Example:**
```bash
python find_related_items.py data/geodatanyc.csv
```

**Input:** CSV with columns: `Date`, `Username`, `Summary/Quote`, `Link`

**Output:**
- `connections.csv` - Edge list with `source_id`, `target_id`, `reason`
- `connections.json` - Full graph with nodes and edges

**Options:**
- `--provider anthropic` (default) - Use Claude
- `--provider openai` - Use GPT-4o-mini (requires `pip install openai` and `OPENAI_API_KEY`)

---

### 2. `add_topics.py` - Add Topic Clusters

**Purpose:** Detects communities in the connection graph using NetworkX, then uses AI to label each cluster with a topic name.

**Usage:**
```bash
pip install networkx  # Required dependency
python add_topics.py <connections.json>
```

**Example:**
```bash
python add_topics.py data/connections.json
```

**Input:** `connections.json` from step 1

**Output:**
- `connections_with_topics.json` - Graph data with `topic_id` and `topic_label` added to each node
- Also copies to `frontend/src/data/` if frontend exists

**Notes:**
- Uses Greedy Modularity community detection
- Falls back to keyword-based labeling if no API key is set

---

## Frontend

A React + Vite frontend for visualizing the graph.

```bash
cd frontend
npm install
npm run dev
```

---

## Workflow

```
┌─────────────┐    ┌──────────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐
│  Input CSV  │───>│ find_related_items.py│───>│ connections.json│───>│     add_topics.py       │
│  (tweets)   │    │                      │    │                 │    │                         │
└─────────────┘    └──────────────────────┘    └─────────────────┘    └───────────┬─────────────┘
                                                                                   │
                                                                                   v
                                                                      ┌───────────────────────────┐
                                                                      │ connections_with_topics.json│
                                                                      └───────────┬───────────────┘
                                                                                   │
                                                                                   v
                                                                      ┌───────────────────────────┐
                                                                      │    Frontend (React)       │
                                                                      └───────────────────────────┘
```

**Order of operations:**
1. Prepare your input CSV with suggestions/issues
2. Run `find_related_items.py` to generate the connection graph
3. Run `add_topics.py` to detect and label topic clusters
4. Run the frontend to visualize the graph

## Data Format

Input CSV should have these columns:
```
Date,Username,Summary/Quote,Link
2025-12-05,@NYCPlanning,ADUs are a proven way to create housing...,https://x.com/...
```

## Context Window Threshold

- **≤100 items**: Uses full context window (current approach)
- **>100 items**: Should use embeddings for efficiency (see `PLAN_EMBEDDINGS.md`)
