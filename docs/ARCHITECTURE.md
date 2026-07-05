# FitnessOS Architecture

## Overview

FitnessOS follows **Clean Architecture** principles with four distinct layers:

```
┌─────────────────────────────────────────┐
│            Presentation Layer           │
│  Next.js · React · TypeScript · Tailwind│
├─────────────────────────────────────────┤
│            Application Layer            │
│  FastAPI · Agent Orchestrator · Celery  │
├─────────────────────────────────────────┤
│              Domain Layer               │
│  SQLAlchemy Models · Business Rules     │
├─────────────────────────────────────────┤
│           Infrastructure Layer          │
│  PostgreSQL · pgvector · Redis · Supabase│
└─────────────────────────────────────────┘
```

## Agent Orchestration Graph

```
START
  │
  ▼
Memory Agent (load_context)
  │ loads: permanent_memory, goals, events, relevant_memories
  │
  ▼
Knowledge Agent (knowledge_retrieve)
  │ retrieves: exercise science, nutrition facts via RAG
  │
  ▼
Coach Agent (coach_route)
  │ decides: which specialist agents to invoke
  │
  ├──[needs_workout]──► Workout Agent ──┐
  ├──[needs_nutrition]─► Nutrition Agent ├──► Coach Agent (synthesize)
  ├──[needs_swimming]──► Swimming Agent ─┤       │
  ├──[needs_analytics]─► Analytics Agent ┤       │
  ├──[needs_scheduler]─► Scheduler Agent ┤       │
  └──[needs_event]─────► Event Agent ───┘       │
                                                  │
                                                  ▼
                                          Memory Agent (store)
                                                  │
                                                 END
```

## Model-Agnostic LLM Design

The `app/services/llm/provider.py` module is the **single point of contact** with LLM providers.

```python
# Change this one env var to switch providers:
DEFAULT_LLM_PROVIDER=anthropic

# No application code changes required.
```

Supported providers: OpenAI, Anthropic, Google, OpenRouter, Ollama.

## Security Architecture

- **Authentication**: Clerk-issued JWTs, verified via JWKS
- **Authorization**: Role-based access via `require_role()` dependency
- **Rate Limiting**: Redis sliding window, per-user per-endpoint
- **Secrets**: Always from environment variables, never hardcoded
- **Audit Trail**: Immutable append-only AuditLog table

## Plugin Architecture for Future Modules

FitnessOS is designed for expansion. Adding a new life module (Finance, Career, etc.):

1. Create `app/agents/<module>/agent.py` inheriting from `BaseAgent`
2. Add routing flag to `AgentState`: `needs_<module>_agent`
3. Register the node in `app/agents/graph.py`
4. Add a frontend page under `src/app/<module>/`

The shared memory system works across all modules automatically.
