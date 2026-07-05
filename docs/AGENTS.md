# FitnessOS Agent Specifications

## Agent Communication

All agents communicate exclusively through **AgentState** — a TypedDict passed through the LangGraph graph. Agents never call each other directly. This ensures:
- Clear data flow
- Easy debugging (inspect state at any point)
- Modular testing (each agent testable in isolation)

## Agent Catalog

### 1. Coach Agent (Orchestrator)
**File**: `app/agents/coach/agent.py`

The primary user-facing agent. Runs twice per request:
- **First pass**: Understands the request, decides routing
- **Second pass**: Synthesizes all specialist outputs into a final response

**System Prompt**: Elite personal trainer with years of relationship with the user.

---

### 2. Memory Agent
**File**: `app/agents/memory/agent.py`

Runs at the START (load) and END (store) of every request.

**Load responsibilities**:
- Permanent memory (user profile, preferences)
- Semantically relevant memories (pgvector similarity)
- Active goals
- Upcoming events
- Recent progress

**Store responsibilities**:
- Extract facts from conversation using LLM
- Generate embeddings for new memories
- Mark superseded memories

---

### 3. Knowledge Agent (RAG)
**File**: `app/agents/knowledge/agent.py`

Maintains the application's domain knowledge — NOT user-specific data.

**Knowledge domains**:
- Exercise science and biomechanics
- Sports nutrition and vegetarian protein sources
- Swimming technique and progression
- Recovery and sleep science
- Fat loss and body recomposition research

Uses pgvector for semantic search over indexed knowledge documents.

---

### 4. Workout Agent
**File**: `app/agents/workout/agent.py`

**Responsibilities**:
- Generate PPL / Upper-Lower / Bro Split programs
- Apply double progression for progressive overload
- Modify workouts for injuries
- Plan deload and peak weeks
- Track exercise PRs

**Key Logic**: Epley formula for 1RM estimation. Double progression: increase reps → increase weight.

---

### 5. Nutrition Agent
**File**: `app/agents/nutrition/agent.py`

**Specializations**:
- Indian vegetarian high-protein diet
- Calorie cycling (higher training days, lower rest days)
- Mifflin-St Jeor TDEE calculation
- Restaurant meal optimization
- Travel and festival nutrition

**Hard constraints**: No tofu, no soya chunks, no creatine. Eggs only post-gym (evening).

---

### 6. Swimming Agent
**File**: `app/agents/swimming/agent.py`

**Progression framework**: Confidence → Breathing → Technique → Endurance

**Tracking**: Breathing comfort (1-10), confidence (1-10), technique (1-10), total meters.

---

### 7. Analytics Agent
**File**: `app/agents/analytics/agent.py`

**Key calculations**:
- Linear regression on weight trend
- Predicted weight on event dates (always from `date.today()`)
- Adherence percentages (gym, swim, nutrition, sleep)
- Plateau detection

---

### 8. Scheduler Agent
**File**: `app/agents/scheduler/agent.py`

**Rescheduling rules** (when session is missed):
- Never punish — always redistribute
- Never stack 3+ consecutive heavy sessions
- Account for: office 10:30-8PM, swim 8AM, gym 9PM
- Weekends = recovery priority

---

### 9. Event Agent
**File**: `app/agents/event/agent.py`

**Phase recommendations** based on days to next event:
| Days | Phase |
|------|-------|
| >120 | hypertrophy |
| 90-120 | hypertrophy_with_cut |
| 60-90 | moderate_cutting |
| 30-60 | aggressive_cutting |
| 14-30 | maintenance_and_polish |
| 7-14 | deload_and_peak_prep |
| ≤7 | peak_week |

---

### 10. Reflection Agent
**File**: `app/agents/reflection/agent.py`

Runs every Sunday (via Celery beat). Generates:
1. Performance score (0-100)
2. Top 3 wins
3. Top 3 bottlenecks
4. Root cause analysis
5. Next week adjustments
6. Motivational message (calibrated to actual performance)

Results are stored back into the memory system for long-term coaching intelligence.
