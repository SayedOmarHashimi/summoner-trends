"""Extraction layer for Summoner Trends.

Pulls match data from the official Riot Games API and lands it for dbt to
transform. Only documented endpoints are used.
"""

__all__ = ["config", "rate_limiter", "riot_client"]
