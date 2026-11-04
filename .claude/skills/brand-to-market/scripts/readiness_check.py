#!/usr/bin/env python3
"""brand-launch-kit/99-readiness.json 을 읽어 '구매 가능' 여부와 막힌 게이트를 출력한다.

사용: python3 readiness_check.py path/to/99-readiness.json
값: true / false / "in_progress". 모든 게이트가 true 여야 '구매 가능'.
"""
import json
import sys

GATES = [
    ("g1_one_sentence_sku", "1 리서치: 히어로 SKU가 한 문장으로 설명된다"),
    ("g2_claims_within_matrix", "2 브랜드 코어: 핵심 소구가 클레임 매트릭스 안에 있다"),
    ("g3_visual_consistency", "3 비주얼: 마스터 세트·레퍼런스 보드로 일관성이 고정됐다"),
    ("g4_positive_contribution_margin", "4 원가: 채널 수수료·광고비 반영 후 기여이익이 양수다"),
    ("g5_legal_registration", "5 인프라: 판매에 필요한 법적 등록이 완료됐다"),
    ("g5_two_channels_live", "5 인프라: 채널 2개가 실제로 열려 있다"),
    ("g5_payment_test_order", "5 인프라: 결제 테스트 주문이 성공했다"),
    ("g6_pdp_trust_blocks", "6 상세: PDP가 클레임을 지키고 신뢰 블록을 갖췄다"),
    ("g7_creator_to_checkout_path", "7 콘텐츠: 크리에이터→결제 경로가 30일 계획에 있다"),
]


def main(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    gates = data.get("gates", {})
    notes = data.get("notes", {})
    blocked, pending, missing = [], [], []
    for key, label in GATES:
        v = gates.get(key)
        if v is True:
            continue
        if v is None:
            missing.append((key, label))
        elif v == "in_progress":
            pending.append((key, label))
        else:
            blocked.append((key, label))

    print(f"브랜드: {data.get('brand', '?')} / 히어로 SKU: {data.get('hero_sku', '?')} / 시장: {', '.join(data.get('markets', []))}")
    total = len(GATES)
    passed = total - len(blocked) - len(pending) - len(missing)
    print(f"게이트 통과: {passed}/{total}")
    if not (blocked or pending or missing):
        print("상태: 구매 가능 (모든 게이트 통과)")
        return 0
    print("상태: 아직 구매 불가")
    for title, items in (("막힘", blocked), ("진행 중", pending), ("미기재", missing)):
        for key, label in items:
            note = notes.get(key)
            print(f"  [{title}] {label}" + (f"  — {note}" if note else ""))
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
