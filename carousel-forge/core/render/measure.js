/*
 * 렌더된 페이지 안에서 텍스트 기하를 실측한다.
 *
 * manifest.json과 SVG의 모든 좌표는 여기서 나온 값이다. 추정값은 쓰지 않는다
 * (절대 규칙 #3). PNG·SVG·Figma 결과물이 픽셀 단위로 일치하는 이유가 이것이다.
 *
 * 측정 단위는 "run" — 한 줄 안에서 스타일이 동일하게 이어지는 조각이다.
 * 강조 구간(<span class="em">)은 별도 텍스트 노드라 자연히 별도 run으로 잡히고,
 * 줄바꿈이 일어나면 같은 텍스트 노드도 여러 run으로 쪼개진다.
 */
(() => {
  const slide = document.getElementById("slide");
  const origin = slide.getBoundingClientRect();

  const rel = (r) => ({
    x: r.left - origin.left,
    y: r.top - origin.top,
    width: r.width,
    height: r.height,
  });

  /* text-transform이 걸린 글자는 DOM 값과 화면에 보이는 글자가 다르다.
   * SVG와 manifest에는 화면에 보이는 쪽을 실어야 PNG와 어긋나지 않는다. */
  function applyTransform(text, transform) {
    if (transform === "uppercase") return text.toUpperCase();
    if (transform === "lowercase") return text.toLowerCase();
    if (transform === "capitalize") return text.replace(/(^|\s)(\S)/g, (m, a, b) => a + b.toUpperCase());
    return text;
  }

  /* 문자 사각형의 top에서 베이스라인까지의 거리.
   *
   * ascent를 폰트 메트릭에서 읽어 half-leading을 손으로 계산하면 브라우저가
   * 실제로 쓰는 값과 1px 가까이 어긋난다. 그래서 계산하지 않고 잰다.
   *
   * 높이 0짜리 inline-block은 아래 모서리가 베이스라인에 정확히 놓인다.
   * 그 요소의 top과, 같은 줄에 있는 문자의 Range 사각형 top의 차이를 재면
   * 그게 곧 우리가 필요한 거리다. 본문에서 쓰는 기준(문자 사각형 top)과
   * 똑같은 기준으로 재기 때문에, Range 사각형이 줄 상자와 몇 px 어긋나든
   * 그 차이가 상쇄된다. */
  const baselineCache = new Map();
  function baselineOffset(cs) {
    const key = [cs.fontStyle, cs.fontWeight, cs.fontSize, cs.lineHeight,
                 cs.letterSpacing, cs.fontFamily].join("|");
    if (baselineCache.has(key)) return baselineCache.get(key);

    const probe = document.createElement("div");
    probe.style.cssText = "position:absolute;left:-99999px;top:0;visibility:hidden;white-space:pre;";
    probe.style.fontStyle = cs.fontStyle;
    probe.style.fontWeight = cs.fontWeight;
    probe.style.fontSize = cs.fontSize;
    probe.style.fontFamily = cs.fontFamily;
    probe.style.lineHeight = cs.lineHeight;
    probe.style.letterSpacing = cs.letterSpacing;

    const text = document.createTextNode("가Ag");
    const marker = document.createElement("span");
    marker.style.cssText = "display:inline-block;width:0;height:0;";
    probe.append(text, marker);
    document.body.append(probe);

    const range = document.createRange();
    range.setStart(text, 0);
    range.setEnd(text, 1);
    const charTop = range.getClientRects()[0].top;
    const offset = marker.getBoundingClientRect().top - charTop;
    probe.remove();

    baselineCache.set(key, offset);
    return offset;
  }

  /* 텍스트 노드를 줄 단위 조각으로 쪼갠다. 문자마다 Range 사각형을 재서
   * top이 바뀌는 지점을 줄바꿈으로 본다. 브라우저가 실제로 어디서 줄을
   * 넘겼는지를 그대로 읽는 방식이라 줄바꿈 규칙을 다시 구현할 필요가 없다.
   *
   * 줄 경계의 공백(줄바꿈에 소비된 스페이스, 명시적 \n)은 상자에서 뺀다.
   * white-space: pre-wrap에서는 그 공백이 컨테이너 밖으로 흘러나가므로,
   * 그대로 재면 있지도 않은 안전영역 침범이 잡힌다. */
  function splitTextNode(node) {
    const text = node.nodeValue;
    const range = document.createRange();
    const chars = [];

    for (let i = 0; i < text.length; i += 1) {
      range.setStart(node, i);
      range.setEnd(node, i + 1);
      const rects = Array.from(range.getClientRects()).filter((r) => r.width > 0 || r.height > 0);
      if (rects.length === 0) continue;          // 줄 끝에서 접힌 공백 등
      const r = rects[rects.length - 1];
      chars.push({ index: i, rect: r, space: /\s/.test(text[i]) });
    }

    /* top이 바뀌면 새 줄 */
    const lines = [];
    for (const ch of chars) {
      const last = lines[lines.length - 1];
      if (last && Math.abs(ch.rect.top - last[0].rect.top) <= 0.5) last.push(ch);
      else lines.push([ch]);
    }

    const pieces = [];
    lines.forEach((line, lineIdx) => {
      let start = 0;
      let end = line.length;
      while (end > start && line[end - 1].space) end -= 1;         // 줄 끝 공백 제거
      if (lineIdx > 0) while (start < end && line[start].space) start += 1;  // 줄바꿈에 쓰인 공백
      if (start >= end) return;                                    // 공백만 있는 줄

      const kept = line.slice(start, end);
      const box = {
        top: kept[0].rect.top,
        bottom: kept[0].rect.bottom,
        left: kept[0].rect.left,
        right: kept[0].rect.right,
      };
      for (const ch of kept) {
        box.left = Math.min(box.left, ch.rect.left);
        box.right = Math.max(box.right, ch.rect.right);
        box.bottom = Math.max(box.bottom, ch.rect.bottom);
      }
      pieces.push({
        text: text.slice(kept[0].index, kept[kept.length - 1].index + 1),
        box,
      });
    });
    return pieces;
  }

  function runsFor(blockEl) {
    const walker = document.createTreeWalker(blockEl, NodeFilter.SHOW_TEXT);
    const runs = [];
    let node;
    while ((node = walker.nextNode())) {
      if (!node.nodeValue || !node.nodeValue.trim()) continue;
      const parent = node.parentElement;
      const cs = getComputedStyle(parent);
      const lineHeight = parseFloat(cs.lineHeight);
      const toBaseline = baselineOffset(cs);
      const isEmphasis = parent.classList.contains("em");

      for (const piece of splitTextNode(node)) {
        const box = piece.box;
        /* 문자 상자(top~bottom)가 아니라 줄 상자 기준으로 베이스라인을 잡는다.
         * 문자 상자의 높이는 line-height와 같으므로 top이 곧 줄 상자 top이다. */
        const lineTop = box.top - origin.top;
        runs.push({
          text: applyTransform(piece.text, cs.textTransform),
          emphasis: isEmphasis,
          x: box.left - origin.left,
          y: lineTop,
          width: box.right - box.left,
          height: box.bottom - box.top,
          baseline: lineTop + toBaseline,
          color: cs.color,
          font_family: cs.fontFamily,
          font_weight: parseInt(cs.fontWeight, 10),
          font_size: parseFloat(cs.fontSize),
          letter_spacing: cs.letterSpacing === "normal" ? 0 : parseFloat(cs.letterSpacing),
          line_height: lineHeight,
        });
      }
    }
    return runs;
  }

  const blocks = Array.from(document.querySelectorAll("[data-copy-block]")).map((el) => {
    const cs = getComputedStyle(el);
    return {
      id: el.id,
      role: el.dataset.role,
      text: applyTransform(el.textContent, cs.textTransform),
      box: rel(el.getBoundingClientRect()),
      align: cs.textAlign === "start" ? "left" : cs.textAlign,
      color: cs.color,
      font_family: cs.fontFamily,
      font_weight: parseInt(cs.fontWeight, 10),
      font_size: parseFloat(cs.fontSize),
      letter_spacing: cs.letterSpacing === "normal" ? 0 : parseFloat(cs.letterSpacing),
      line_height: parseFloat(cs.lineHeight),
      runs: runsFor(el),
    };
  });

  const bg = document.querySelector("#bg-layer img");
  const safeEl = document.getElementById("text-layer");

  return {
    canvas: { width: origin.width, height: origin.height },
    safe_area: rel(safeEl.getBoundingClientRect()),
    background: bg ? { src: bg.getAttribute("src"), box: rel(bg.getBoundingClientRect()) } : null,
    blocks,
  };
})();
