# Notifications API

> 12 nodes · cohesion 0.17

## Key Concepts

- **list_pool_items()** (6 connections) — `backend/app/routes/notifications.py`
- **mark_notification_read()** (5 connections) — `backend/app/routes/notifications.py`
- **list_notifications()** (4 connections) — `backend/app/routes/notifications.py`
- **str** (4 connections) — `backend/app/routes/notifications.py`
- **mark_all_notifications_read()** (4 connections) — `backend/app/routes/notifications.py`
- **Fetch unread notifications for the current user.** (1 connections) — `backend/app/routes/notifications.py`
- **Mark all unread notifications as read for the current user.** (1 connections) — `backend/app/routes/notifications.py`
- **Mark a specific notification as read.** (1 connections) — `backend/app/routes/notifications.py`
- **Currently-actionable shared-pool items for the claim banner.      Reflects live** (1 connections) — `backend/app/routes/notifications.py`
- **Mark a specific notification as read.** (1 connections) — `backend/app/routes/notifications.py`
- **Currently-actionable shared-pool items for the claim banner.      Reflects live** (1 connections) — `backend/app/routes/notifications.py`
- **Currently-actionable shared-pool items for the claim banner.      Reflects live** (1 connections) — `backend/app/routes/notifications.py`

## Relationships

- [[Calls API (TeleCMI dialer)]] (4 shared connections)
- [[Leaddetailpanel Component]] (4 shared connections)

## Source Files

- `backend/app/routes/notifications.py`

## Audit Trail

- EXTRACTED: 26 (87%)
- INFERRED: 4 (13%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*