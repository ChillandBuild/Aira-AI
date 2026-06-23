# Todos API

> 8 nodes · cohesion 0.32

## Key Concepts

- **todos.py** (7 connections) — `backend/app/routes/todos.py`
- **update_todo()** (6 connections) — `backend/app/routes/todos.py`
- **UUID** (6 connections) — `backend/app/routes/todos.py`
- **get_todos()** (4 connections) — `backend/app/routes/todos.py`
- **create_or_update_todo()** (4 connections) — `backend/app/routes/todos.py`
- **delete_todo()** (4 connections) — `backend/app/routes/todos.py`
- **Fetch todos for the current user, optionally filtered by date range.** (1 connections) — `backend/app/routes/todos.py`
- **Update a specific todo.** (1 connections) — `backend/app/routes/todos.py`

## Relationships

- [[Leads API]] (7 shared connections)
- [[Operator Console & Audit]] (7 shared connections)
- [[App Entry & Schedulers]] (1 shared connections)

## Source Files

- `backend/app/routes/todos.py`

## Audit Trail

- EXTRACTED: 23 (70%)
- INFERRED: 10 (30%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*