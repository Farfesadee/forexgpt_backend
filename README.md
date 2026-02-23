# ForexGPT Backend

## Overview

ForexGPT Backend is a FastAPI-based REST API responsible for generating structured forex trading signals based on user input prompts.

This backend is part of a larger system where:

- Supabase handles authentication and database management.
- FastAPI handles business logic and signal generation.
- The frontend communicates with this backend via protected API endpoints.

The system follows a modular, service-layer architecture designed for scalability and maintainability.

---

## Architecture Overview

Client → Supabase Auth → FastAPI Backend → Signal Logic → Response

### Responsibilities

### FastAPI Backend (This Repository)
- Protected API endpoints
- Signal generation logic
- Token verification
- Structured request/response validation
- Logging

### Supabase (Handled by Collaborator)
- User signup
- User login
- JWT token generation
- User storage
- Signal history storage

---

## Project Structure

## Supabase Execution
--- Day 1:
- Supabase Setup 
- Created project
- Defined database schema (users, signals, backtests, strategies, conversations, activity_log) 
- Supabase DB schema 

--- Day 2: 
- Auth Integration 
- Integrate Supabase auth in backend (login, register, JWT) 
- Auth endpoints working