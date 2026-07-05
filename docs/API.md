# FitnessOS REST API Reference

Base URL: `http://localhost:8000/api/v1`

All endpoints require Clerk JWT in the Authorization header:
```
Authorization: Bearer <clerk_session_token>
```

---

## Chat

### POST /chat/message
Send a message and receive a coaching response.

**Request**:
```json
{
  "message": "What should I eat before my evening gym session?",
  "session_id": "optional-uuid-to-continue-conversation",
  "stream": false
}
```

**Response**:
```json
{
  "response": "Great question! Since you gym at 9 PM...",
  "session_id": "uuid",
  "agent_trace": ["memory_agent: loaded 12 memories", "..."],
  "follow_up_suggestions": ["..."],
  "confidence_score": 0.92,
  "request_id": "uuid"
}
```

### GET /chat/history/{session_id}
Get conversation history for a session.

---

## Dashboard

### GET /dashboard/summary
Returns all dashboard data in one call.

**Response**:
```json
{
  "user": { "name": "...", "is_onboarded": true },
  "metrics": {
    "current_weight_kg": 100,
    "target_weight_kg": 85,
    "weight_to_lose_kg": 15
  },
  "weekly_progress": {
    "gym_sessions_completed": 3,
    "gym_sessions_scheduled": 4,
    "adherence_pct": 75
  },
  "weight_history": [{ "date": "...", "weight_kg": 100 }],
  "countdowns": {
    "pre_wedding": { "title": "Pre-Wedding Shoot", "days_remaining": 111 },
    "wedding": { "title": "Wedding", "days_remaining": 213 }
  },
  "today": "2026-07-01"
}
```

---

## Users

### GET /users/me
Get current user profile.

### POST /users/me/preferences
Update user preferences (permanent memory layer).

### POST /users/onboard
Complete user onboarding with full profile.

---

## Workouts

### GET /workouts/sessions/today
Get today's scheduled workout sessions.

### POST /workouts/sessions/{id}/log
Log a completed workout with performance data.

### GET /workouts/exercises?query=&muscle_group=
Search the exercise library.

### GET /workouts/plans/active
Get the user's currently active workout plan.

---

## Measurements

### POST /measurements/
Log a body measurement snapshot.

### GET /measurements/
Get measurement history (most recent first).

### GET /measurements/latest
Get the most recent measurement.

---

## Health

### GET /health
Health check endpoint.
```json
{ "status": "healthy", "version": "1.0.0", "env": "production" }
```
