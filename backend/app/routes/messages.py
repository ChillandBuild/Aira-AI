"""
Message history routes.

This module will expose endpoints for retrieving conversation threads between
Anril and leads, supporting pagination and filtering by lead ID, date range,
and direction (inbound / outbound).
"""

from fastapi import APIRouter

router = APIRouter()
