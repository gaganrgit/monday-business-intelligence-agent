"""Pydantic models describing API request/response payloads."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Founder's natural language question")


class ChatResponse(BaseModel):
    answer: str


class HealthResponse(BaseModel):
    status: str
    monday_configured: bool
    fireworks_configured: bool
