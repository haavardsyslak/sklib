import atexit
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_REQUESTS = 1000


@dataclass
class CoverageTracker:
    total_requests: int = 0
    total_products: int = 0
    field_hits: dict[str, int] = field(default_factory=dict)
    field_misses: dict[str, int] = field(default_factory=dict)
    alias_stats: dict[str, int] = field(default_factory=dict)
    request_details: list[dict] = field(default_factory=list)
    _pending_flush: bool = field(default=False, repr=False)

    def record_hit(self, field_name: str, alias_used: str | None):
        self.field_hits[field_name] = self.field_hits.get(field_name, 0) + 1
        if alias_used:
            self.alias_stats[alias_used] = self.alias_stats.get(alias_used, 0) + 1

    def record_miss(self, field_name: str):
        self.field_misses[field_name] = self.field_misses.get(field_name, 0) + 1

    def record_product(
        self, mpn: str, component_type: str, fields: dict[str, str | None]
    ):
        self.request_details.append(
            {
                "mpn": mpn,
                "component_type": component_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "fields": fields,
            }
        )
        if len(self.request_details) > MAX_REQUESTS:
            self.request_details = self.request_details[-MAX_REQUESTS:]

    def record_request(self, num_products: int):
        self.total_requests += 1
        self.total_products += num_products
        self._pending_flush = True
        if self.total_requests % 5 == 0:
            self.flush()

    def to_dict(self) -> dict[str, Any]:
        all_fields = set(self.field_hits) | set(self.field_misses)
        field_stats = {
            f: {
                "hits": self.field_hits.get(f, 0),
                "misses": self.field_misses.get(f, 0),
            }
            for f in sorted(all_fields)
        }
        return {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_requests": self.total_requests,
            "total_products": self.total_products,
            "field_stats": field_stats,
            "alias_stats": dict(sorted(self.alias_stats.items())),
        }

    def flush(self):
        if not self._pending_flush:
            return
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)

        stats_path = log_dir / "coverage_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

        requests_path = log_dir / "coverage_requests.json"
        with open(requests_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "requests": self.request_details,
                },
                f,
                indent=2,
            )

        self._pending_flush = False


_tracker: CoverageTracker | None = None


def get_tracker() -> CoverageTracker:
    global _tracker
    if _tracker is None:
        _tracker = CoverageTracker()
        atexit.register(_tracker.flush)
    return _tracker
