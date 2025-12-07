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
- `connections.json` - Full graph with nodes and edges (for visualization)

**Options:**
- `--provider anthropic` (default) - Use Claude
- `--provider openai` - Use GPT-4o-mini (requires `pip install openai` and `OPENAI_API_KEY`)

---

## Workflow

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Input CSV      │────>│ find_related_items.py│────>│ connections.csv │
│  (tweets/ideas) │     │                      │     │ connections.json│
└─────────────────┘     └──────────────────────┘     └─────────────────┘
```

**Order of operations:**
1. Prepare your input CSV with suggestions/issues
2. Run `find_related_items.py` to generate the connection graph
3. Use output files for visualization or further analysis

## Data Format

Input CSV should have these columns:
```
Date,Username,Summary/Quote,Link
2025-12-05,@NYCPlanning,ADUs are a proven way to create housing...,https://x.com/...
```

## Context Window Threshold

- **≤100 items**: Uses full context window (current approach)
- **>100 items**: Should use embeddings for efficiency (see `PLAN_EMBEDDINGS.md`)
