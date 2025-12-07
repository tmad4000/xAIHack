# Future Plan: Embeddings-Based Similarity for Large Datasets

## Current Approach (≤100 items)
For small datasets, we use the full context window approach:
- Load all items into the AI context
- Ask the AI to identify top related items for each entry
- O(n) API calls (one per item, with all items in context)

## Future Approach (>100 items)
For larger datasets, we'll use embeddings for initial filtering:

### Phase 1: Generate Embeddings
1. Use OpenAI's `text-embedding-3-small` or similar
2. Generate embedding vector for each item's summary text
3. Cache embeddings to avoid regeneration

### Phase 2: Initial Candidate Selection
1. For each item, compute cosine similarity with all other items
2. Select top-K candidates (e.g., K=20) based on embedding similarity
3. This is fast: O(n²) but just vector math, no API calls

### Phase 3: AI Refinement
1. For each item, send only the top-K candidates to AI
2. AI ranks/filters to find truly related items
3. This reduces context size from n items to K items per call

### Benefits
- Cost: ~95% reduction in tokens for large datasets
- Speed: Embedding similarity is nearly instant
- Quality: AI still makes final relevance decisions

### Implementation Notes
- Store embeddings in `data/embeddings_cache.json`
- Use `numpy` or `scikit-learn` for cosine similarity
- Threshold: Switch to embeddings approach when items > 100

### Libraries Needed
```
pip install openai numpy scikit-learn
```
