"""리서치·팩트체크 프로바이더 인터페이스 (web_search + web_fetch 병렬). M5."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Source:
    title: str
    url: str
    publisher: str | None = None
    snippet: str | None = None


class ResearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, *, limit: int = 10) -> list[Source]: ...

    @abstractmethod
    def fetch(self, url: str) -> str: ...
