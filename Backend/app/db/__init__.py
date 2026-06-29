"""Normalized enterprise persistence layer (SQLAlchemy 2.0).

This layer is additive — it persists each
run into normalized, queryable tables alongside the existing run store. Enable
with DB_PERSISTENCE_ENABLED=true (and DATABASE_URL for Postgres/Supabase; the
default sqlite URL works for local dev).
"""
