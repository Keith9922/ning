from __future__ import annotations

from typing import Any

# Holds runtime singletons (e.g., redis client) to avoid circular imports.
redis_client: Any | None = None


