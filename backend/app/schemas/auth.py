"""Pydantic schemas for auth endpoints."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    authenticated: bool
    role: str


class SessionResponse(BaseModel):
    authenticated: bool
    role: str
