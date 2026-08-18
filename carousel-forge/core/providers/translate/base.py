"""현지화 프로바이더 인터페이스. 직역이 아니라 현지화다 (A10). M7."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LocalizeProvider(ABC):
    @abstractmethod
    def localize(self, text: str, *, source_lang: str, target_lang: str, register: str) -> str: ...
