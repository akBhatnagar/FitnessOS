# FitnessOS Database Design

## Schema Overview

All tables use UUIDs, have `created_at` and `updated_at` timestamps, and use soft deletes where appropriate.

## Core Tables

### users
Primary identity table. Links Clerk auth to internal records.
```
id (uuid pk) | clerk_user_id | email | full_name | timezone | is_active | is_onboarded
```

### user_preferences
The permanent memory layer. Loaded on every AI request.
```
id | user_id (fk) | diet_type | allowed_foods[] | disallowed_foods[]
current_weight_kg | target_weight_kg | height_cm | date_of_birth
work_start_time | work_end_time | gym_preferred_time | swim_preferred_time
current_injuries[] | medical_conditions[] | motivation_triggers[]
```

## Training Tables

### exercises (global, shared)
```
id | name | slug | exercise_type | primary_muscle | secondary_muscles[]
equipment_needed[] | is_compound | instructions | met_value
```

### workout_plans
```
id | user_id | name | phase | duration_weeks | days_per_week
start_date | end_date | is_active | ai_generated | plan_metadata (jsonb)
```

### workout_sessions
```
id | plan_id | user_id | scheduled_date | session_name
muscle_groups_targeted[] | status | started_at | completed_at
effort_rating (1-10) | fatigue_rating (1-10) | mood_rating (1-10)
```

### workout_sets
```
id | session_id | exercise_id | set_number
planned_reps | planned_weight_kg | actual_reps | actual_weight_kg | rpe
```

### exercise_history
```
id | user_id | exercise_id | recorded_on
best_weight_kg | best_reps | estimated_1rm | total_volume_kg | is_personal_record
```

## Memory Tables

### memory_store
The AI's long-term personal memory.
```
id | user_id | memory_type (permanent/episodic/semantic/procedural)
category | content | embedding (vector) | importance_score
is_active | is_superseded | source_type | source_id
```

### conversation_history
```
id | user_id | session_id | role | content | agent_name
embedding (vector) | token_count | created_at
```

### embeddings
Generic embedding store for RAG.
```
id | source_type | source_id | user_id | content
embedding (vector) | embedding_model | chunk_index | chunk_metadata (jsonb)
```

## pgvector Indexes

```sql
-- Memory retrieval (most frequent query)
CREATE INDEX idx_memory_embedding ON memory_store 
  USING hnsw (embedding vector_cosine_ops);

-- Conversation search
CREATE INDEX idx_conversation_embedding ON conversation_history
  USING hnsw (embedding vector_cosine_ops);

-- Knowledge base RAG
CREATE INDEX idx_embedding ON embeddings
  USING hnsw (embedding vector_cosine_ops);
```

## Design Decisions

1. **UUIDs everywhere** — portable, no sequence collisions, safe for distributed systems
2. **Soft deletes** — `deleted_at` instead of hard deletes for audit trails
3. **JSONB for flexible data** — plan_metadata, ai_analysis, chunk_metadata
4. **Denormalized food_name in MealItem** — avoids join for common reads
5. **Computed properties not stored** — `days_remaining` in Event is a Python property, never a column
6. **pgvector HNSW** — faster than IVFFlat for small-to-medium datasets, no training required
