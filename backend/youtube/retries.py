"""Shared request retry budget for the YouTube Data and Analytics API clients."""

# Total attempts per request: _analytics_query()'s HttpError loop and the Google client's
# connection retries (execute(num_retries=...)) both use it.
MAX_ATTEMPTS = 5
NUM_RETRIES = MAX_ATTEMPTS - 1
