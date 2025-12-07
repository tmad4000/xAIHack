# Plan: Improved Clustering & Synthesized Actionable Ideas

## Current State

### What We Have
1. **Connection Discovery** - AI finds top 3-5 related items per tweet based on topic, complementary solutions, geographic focus
2. **Topic-Based Clustering** - Keywords classify tweets into topics (Housing, Transit, Sidewalks, etc.)
3. **Connectivity Sub-Clustering** - Within topics, connected nodes get grouped
4. **Basic AI Summaries** - Cluster names, summaries, generic "Review and prioritize" actions

### Gaps vs Original Vision
- Not identifying **identical demands** (semantically same idea from different people)
- Not **deduplicating** into consolidated demands with voice counts
- Actions are generic ("Review these suggestions") not **synthesized policy proposals**
- No **consensus ranking** of demands by support level

---

## Phase 1: Semantic Demand Extraction

### Goal
Extract discrete **demands** (concrete suggestions) from tweets, not just topics.

### Approach
1. For each cluster, ask AI to identify the **distinct actionable demands** present
2. Each demand gets:
   - A normalized description (e.g., "Implement car-free school streets")
   - List of supporting tweets/voices
   - Voice count

### Example Output
```json
{
  "demands": [
    {
      "description": "Implement car-free school streets during drop-off/pick-up",
      "voices": ["@BrentToderian", "@BrentToderian", "@SomeParent"],
      "count": 3,
      "tweets": [15, 16, 22]
    },
    {
      "description": "Set minimum sidewalk width of 8 feet",
      "voices": ["@TransAlt"],
      "count": 1,
      "tweets": [14]
    }
  ]
}
```

### Implementation
- Add `extract_demands()` function to `enhance_clusters.py`
- Prompt AI to dedupe semantically identical suggestions
- Store demands in `enhanced_clusters.json`

---

## Phase 2: Synthesized Actionable Ideas

### Goal
Generate **novel, concrete policy proposals** that synthesize multiple voices into implementable actions.

### Approach
For each cluster (or high-consensus demand), ask AI to:
1. Synthesize a **specific, implementable policy** combining best elements
2. Include concrete details: numbers, timelines, mechanisms, pilot programs
3. Generate 1-3 synthesized actions per cluster depending on demand diversity

### Example Prompt
```
Given these citizen demands about sidewalks:
- 3 people want car-free school streets
- 2 people want wider sidewalks (8ft minimum)
- 1 person wants better crosswalks

Synthesize 1-2 concrete, implementable policy proposals that a city council could vote on.
Include specific numbers, timelines, and implementation mechanisms.
```

### Example Output
```json
{
  "synthesized_actions": [
    {
      "title": "School Streets Pilot Program",
      "proposal": "Launch a 'School Streets' pilot program making blocks adjacent to 10 schools car-free during drop-off (7:30-8:30am) and pick-up (2:30-3:30pm). Start Fall 2025 with schools in high-traffic areas. Evaluate safety metrics and parent satisfaction after 6 months before citywide expansion.",
      "supporting_demands": ["car-free school streets"],
      "voices_represented": 3
    },
    {
      "title": "Sidewalk Width Standards",
      "proposal": "Amend zoning code to require minimum 8-foot sidewalk width for all new developments and major renovations. Establish a $25M Sidewalk Expansion Fund to widen substandard sidewalks in school zones and transit corridors over 3 years.",
      "supporting_demands": ["8ft minimum sidewalk", "wider sidewalks"],
      "voices_represented": 2
    }
  ]
}
```

### Implementation
- Add `synthesize_actions()` function to `enhance_clusters.py`
- Store in `enhanced_clusters.json` under each cluster
- Display in "Actionable" tab with expandable details

---

## Phase 3: Consensus Ranking & Dashboard

### Goal
Surface the highest-consensus demands prominently.

### Features
1. **Demand Leaderboard** - Top demands ranked by voice count
2. **Consensus Indicators** - Visual badges (High/Medium/Low)
3. **Cross-Cluster Demands** - Same demand appearing in multiple clusters gets combined count
4. **Export** - Generate a "Top 10 Citizen Demands" report for officials

---

## Implementation Priority

1. **Phase 1** (High Impact) - Demand extraction & deduplication
2. **Phase 2** (High Impact) - Synthesized actionable proposals
3. **Phase 3** (Medium Impact) - Ranking dashboard & export

---

## Files to Modify

- `enhance_clusters.py` - Add demand extraction & synthesis functions
- `visualization/index.html` - Update Actionable tab to show synthesized proposals
- `data/enhanced_clusters.json` - Extended schema with demands & synthesized actions
