# FitnessOS Memory System

## Design Principle

> The AI never forgets. Every interaction deepens its knowledge of you.

## 5-Layer Memory Architecture

### Layer 1: Permanent Memory
**Table**: `user_preferences` (+ `users`)
**Contents**: Rarely-changing facts
- Diet type and restrictions
- Height, weight, target weight
- Work schedule
- Gym and swim timing
- Current injuries
- Medical conditions
- Motivation triggers

**Loaded**: Every single request, before any AI processing.

---

### Layer 2: Episodic Memory
**Table**: `conversation_history`, `workout_sessions`, `swimming_sessions`, `meals`
**Contents**: What happened, when
- Full conversation transcripts
- Workout session logs
- Swimming session logs
- Meal logs
- Weekly reviews

**Loaded**: Recent episodes (last 7 days) + semantically relevant older ones.

---

### Layer 3: Semantic Memory
**Table**: `memory_store` (type=semantic)
**Contents**: Facts learned over time
- "Prefers evening gym over morning gym"
- "Dislikes tofu — mentioned 3 times"
- "Gets motivated when seeing visible abs progress"
- "Tends to skip gym on Mondays"
- "Paneer is primary protein source"

**Loaded**: Top-K most relevant to current query via vector similarity.

---

### Layer 4: Procedural Memory
**Table**: `memory_store` (type=procedural)
**Contents**: What coaching strategies work
- "Calorie cycling works better than fixed deficit"
- "Progressive overload on compound lifts drives motivation"
- "Needs direct feedback numbers, not vague encouragement"
- "Responds well to event-based deadlines"

**Loaded**: Retrieved when generating new plans or strategies.

---

### Layer 5: Vector Memory
**Table**: `embeddings` + `memory_store.embedding` + `conversation_history.embedding`
**Contents**: Embeddings of all content for similarity search
- Every conversation message
- Every memory store entry
- Knowledge base chunks

**Used for**: Semantic retrieval using pgvector cosine similarity.

---

## Memory Retrieval (per request)

```python
async def retrieve_context(user_id, query):
    permanent = await load_permanent_memory(user_id)      # always
    goals = await load_active_goals(user_id)              # always
    events = await load_upcoming_events(user_id)          # always
    relevant = await vector_search(user_id, query, k=10)  # semantic search
    recent = await load_recent_sessions(user_id, days=7)  # last week
    return AgentContext(permanent, goals, events, relevant, recent)
```

## Memory Storage (post-response)

After every conversation:
1. LLM extracts memorable facts from the exchange
2. Facts are categorized (diet, exercise, lifestyle, etc.)
3. Embeddings generated for each fact
4. Stored in `memory_store` with source tracking
5. Old conflicting memories marked `is_superseded=True`

## Vector Index Configuration

```sql
-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX ON memory_store USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX ON conversation_history USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

## Memory Importance Scoring

Each memory has an `importance_score` (0.0 - 1.0):
- **1.0**: Medical conditions, injuries, hard dietary restrictions
- **0.9**: Primary goals, event dates
- **0.7**: Strong preferences ("hates tofu")
- **0.5**: General habits and routines
- **0.3**: One-time observations

Importance affects retrieval ranking when scores are tied.
