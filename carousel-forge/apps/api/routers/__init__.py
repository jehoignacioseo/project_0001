"""API 라우터.

섹션 8의 엔드포인트 표면을 M0에서 미리 선언해 둔다. 아직 구현되지 않은
엔드포인트는 조용히 빈 값을 돌려주는 대신 501을 낸다 — "완료"처럼 보이는
미구현이 가장 위험하다.
"""

from . import carousels, exports, library, styles, topics

__all__ = ["carousels", "exports", "library", "styles", "topics"]
