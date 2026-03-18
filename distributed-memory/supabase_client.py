#!/usr/bin/env python3
"""
Base Supabase Client with retry, deduplication, and error handling.
"""
import os
import sys
import time
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from memory_config import (
    REST_URL, HEADERS, NODE_ID, SESSION_ID,
    REQUEST_TIMEOUT, CONTENT_MAX_LENGTH,
    ENABLE_RETRY, RETRY_MAX_ATTEMPTS, RETRY_BACKOFF_BASE,
    DEBUG
)

logger = logging.getLogger(__name__)
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)


class SupabaseClient:
    """Base client for Supabase REST API with retry and idempotency."""

    def __init__(self, node_id: str = None):
        self.node_id = node_id or NODE_ID
        self.session_id = SESSION_ID
        self._last_response: Optional[requests.Response] = None

    def _content_hash(self, content: str) -> str:
        """Generate hash for content deduplication."""
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _make_hash_id(self, role: str, content: str, timestamp: str = None) -> str:
        """Generate idempotent message ID."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        raw = f"{self.node_id}:{self.session_id}:{role}:{content[:100]}:{ts}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json: dict = None,
        headers: dict = None,
        retry: bool = ENABLE_RETRY,
        retry_count: int = 0
    ) -> requests.Response:
        """Make HTTP request with optional retry."""
        url = f"{REST_URL}/{endpoint}"
        request_headers = {**HEADERS}
        if headers:
            request_headers.update(headers)

        try:
            response = requests.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers=request_headers,
                timeout=REQUEST_TIMEOUT
            )

            # Retry on transient errors
            if retry and retry_count < RETRY_MAX_ATTEMPTS:
                if response.status_code in (429, 500, 502, 503, 504):
                    wait_time = RETRY_BACKOFF_BASE * (2 ** retry_count)
                    logger.warning(f"Retry {retry_count + 1}/{RETRY_MAX_ATTEMPTS} after {wait_time}s")
                    time.sleep(wait_time)
                    return self._request(method, endpoint, params, json, headers, True, retry_count + 1)

            response.raise_for_status()
            return response

        except requests.exceptions.Timeout as e:
            if retry and retry_count < RETRY_MAX_ATTEMPTS:
                wait_time = RETRY_BACKOFF_BASE * (2 ** retry_count)
                logger.warning(f"Timeout, retry {retry_count + 1}/{RETRY_MAX_ATTEMPTS}")
                time.sleep(wait_time)
                return self._request(method, endpoint, params, json, headers, True, retry_count + 1)
            raise RuntimeError(f"Request timeout after {RETRY_MAX_ATTEMPTS} attempts: {e}")

        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Request failed: {e}")

    def get(
        self,
        table: str,
        select: str = "*",
        filters: dict = None,
        order: str = None,
        limit: int = None,
        single: bool = False
    ) -> Any:
        """GET request to table."""
        params = {'select': select}
        if filters:
            for key, value in filters.items():
                params[key] = value
        if order:
            params['order'] = order
        if limit:
            params['limit'] = limit

        headers = {'Prefer': 'return=representation'}
        if single:
            headers['Prefer'] = 'return=representation'

        response = self._request('GET', table, params=params, headers=headers)

        if single:
            return response.json()
        return response.json()

    def post(
        self,
        table: str,
        data: dict,
        upsert: bool = False,
        on_conflict: str = None
    ) -> bool:
        """POST request to table."""
        headers = {'Prefer': 'return=minimal'}
        if upsert and on_conflict:
            headers['Prefer'] = 'resolution=merge-duplicates'
            headers['Prefer'] = 'return=representation'

        # Truncate content fields
        processed = self._truncate_data(data)

        response = self._request('POST', table, json=processed, headers=headers)
        return response.status_code in (200, 201)

    def patch(
        self,
        table: str,
        data: dict,
        filters: dict
    ) -> bool:
        """PATCH request to table."""
        # Build filter query
        filter_parts = []
        for key, value in filters.items():
            if isinstance(value, tuple) and len(value) == 2:
                op, val = value
                filter_parts.append(f"{key}=eq.{val}")
            else:
                filter_parts.append(f"{key}=eq.{value}")

        endpoint = f"{table}?{'&'.join(filter_parts)}"

        # Truncate content fields
        processed = self._truncate_data(data)

        response = self._request('PATCH', endpoint, json=processed)
        return response.status_code in (200, 201, 204)

    def upsert_state(
        self,
        table: str,
        data: dict,
        key_field: str = 'node_id'
    ) -> bool:
        """Upsert with automatic conflict handling."""
        # Try patch first (update)
        filter_dict = {key_field: ('eq', data[key_field]) if isinstance(data[key_field], str) else data[key_field]}
        success = self.patch(table, data, filter_dict)

        if not success or self._last_response_status() == 200:
            # If no rows affected, try insert
            return self.post(table, data)

        return success

    def _last_response_status(self) -> int:
        """Get last response status code (for internal use)."""
        return getattr(self._last_response, 'status_code', 200)

    def _truncate_data(self, data: dict) -> dict:
        """Truncate large string fields."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str) and key in ('content', 'summary', 'last_user_message'):
                result[key] = value[:CONTENT_MAX_LENGTH]
            else:
                result[key] = value
        return result


# Singleton instance
_client: Optional[SupabaseClient] = None


def get_client() -> SupabaseClient:
    """Get or create Supabase client singleton."""
    global _client
    if _client is None:
        _client = SupabaseClient()
    return _client
