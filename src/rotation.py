import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class RotationItem:
    value: str
    last_error: Optional[str] = None


class RotationPool:
    def __init__(self, items: List[str], blacklist_ttl: int = 300, name: str = ""):
        self.items = [RotationItem(value=item) for item in items if item]
        self.blacklist_ttl = max(0, int(blacklist_ttl))
        self.name = name or "rotation"
        self._blacklist: Dict[str, float] = {}

    def _cleanup_blacklist(self) -> None:
        now = time.time()
        expired = [key for key, ts in self._blacklist.items() if ts <= now]
        for key in expired:
            self._blacklist.pop(key, None)

    def available_items(self) -> List[RotationItem]:
        self._cleanup_blacklist()
        return [item for item in self.items if item.value not in self._blacklist]

    def pick_random(self) -> Optional[RotationItem]:
        candidates = self.available_items()
        if not candidates:
            return None
        return random.choice(candidates)

    def mark_bad(
        self,
        item: Optional[RotationItem],
        reason: str = "",
        ttl: Optional[int] = None,
    ) -> None:
        """把一个条目拉黑。

        ttl 不传时用池级默认 blacklist_ttl；风控等需要更长冷却的场景
        可以显式传入更长的 ttl（秒）。
        """
        if not item:
            return
        item.last_error = reason
        effective_ttl = self.blacklist_ttl if ttl is None else max(0, int(ttl))
        if effective_ttl <= 0:
            return
        self._blacklist[item.value] = time.time() + effective_ttl


def parse_proxy_pool(value: Optional[str]) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [entry.strip() for entry in str(value).split(",") if entry.strip()]


def load_state_files(state_dir: str) -> List[str]:
    if not state_dir:
        return []
    if not os.path.isdir(state_dir):
        return []
    files = []
    for name in os.listdir(state_dir):
        if name.endswith(".json"):
            files.append(os.path.join(state_dir, name))
    return sorted(files)
