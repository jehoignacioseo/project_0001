/**
 * 테스트용 가짜 Figma API.
 *
 * Figma 안에서만 돌 수 있는 코드를 "돌려는 봤다"로 남겨 두지 않기 위한 것이다.
 * 진짜 Figma를 흉내 내려는 게 아니라, **우리가 부르는 것만** 받아 적는다 —
 * 어떤 노드를 만들었고, 폰트를 언제 불렀고, 속성을 어떤 순서로 설정했는지.
 *
 * 실제 Figma에서 눈으로 확인하는 일을 대신하지는 못한다. 다만 "텍스트가
 * 벡터로 들어갔다" 같은 실패는 여기서 먼저 잡힌다.
 */

export interface FakeNode {
  type: string;
  name: string;
  [key: string]: unknown;
}

export interface FakeText extends FakeNode {
  type: "TEXT";
  characters: string;
  fontName: { family: string; style: string };
  /** 속성이 설정된 순서. 폰트보다 글자가 먼저 들어갔는지 확인한다. */
  order: string[];
  rangeFills: { start: number; end: number; fills: unknown[] }[];
}

export interface FakeFrame extends FakeNode {
  type: "FRAME";
  children: FakeNode[];
}

export class FakeFigma {
  loadedFonts: string[] = [];
  missingFonts = new Set<string>();
  created: FakeNode[] = [];
  messages: unknown[] = [];
  images: Uint8Array[] = [];
  selection: FakeNode[] = [];
  viewportCalls = 0;

  currentPage = { children: [] as FakeNode[] };

  /** 이 폰트는 설치돼 있지 않은 것으로 둔다. */
  markMissing(family: string, style: string): void {
    this.missingFonts.add(`${family} ${style}`);
  }

  async loadFontAsync(font: { family: string; style: string }): Promise<void> {
    const key = `${font.family} ${font.style}`;
    if (this.missingFonts.has(key)) {
      throw new Error(`font not found: ${key}`);
    }
    this.loadedFonts.push(key);
  }

  createFrame(): FakeFrame {
    const node: FakeFrame = {
      type: "FRAME",
      name: "",
      children: [],
      fills: [],
      resize(this: Record<string, unknown>, w: number, h: number) {
        this.width = w;
        this.height = h;
      },
      appendChild(this: FakeFrame, child: FakeNode) {
        this.children.push(child);
      },
    } as unknown as FakeFrame;
    this.created.push(node);
    return node;
  }

  createRectangle(): FakeNode {
    const node = {
      type: "RECTANGLE",
      name: "",
      fills: [],
      locked: false,
      resize(this: Record<string, unknown>, w: number, h: number) {
        this.width = w;
        this.height = h;
      },
    } as unknown as FakeNode;
    this.created.push(node);
    return node;
  }

  createText(): FakeText {
    const self = this;
    const order: string[] = [];
    let characters = "";
    let fontName: unknown = null;

    const node = {
      type: "TEXT",
      name: "",
      order,
      rangeFills: [] as FakeText["rangeFills"],
      height: 40,
      get characters(): string {
        return characters;
      },
      set characters(value: string) {
        order.push("characters");
        characters = value;
      },
      get fontName(): unknown {
        return fontName;
      },
      set fontName(value: unknown) {
        order.push("fontName");
        const font = value as { family: string; style: string };
        // 진짜 Figma는 loadFontAsync 없이 폰트를 지정하면 던진다. 그 규칙을 흉내 낸다.
        if (!self.loadedFonts.includes(`${font.family} ${font.style}`)) {
          throw new Error(
            `font not loaded: ${font.family} ${font.style} — loadFontAsync를 먼저 불러야 한다`,
          );
        }
        fontName = value;
      },
      resize(this: Record<string, unknown>, w: number, h: number) {
        this.width = w;
        this.height = h;
      },
      setRangeFills(this: FakeText, start: number, end: number, fills: unknown[]) {
        this.rangeFills.push({ start, end, fills });
      },
    } as unknown as FakeText;
    this.created.push(node);
    return node;
  }

  createImage(bytes: Uint8Array): { hash: string } {
    this.images.push(bytes);
    return { hash: `image-${this.images.length}` };
  }

  group(nodes: FakeNode[], _page: unknown): FakeNode {
    const node = { type: "GROUP", name: "", children: nodes } as unknown as FakeNode;
    this.created.push(node);
    return node;
  }

  viewport = {
    scrollAndZoomIntoView: (_nodes: unknown[]) => {
      this.viewportCalls += 1;
    },
  };

  ui = {
    postMessage: (message: unknown) => {
      this.messages.push(message);
    },
  };

  closePlugin(): void {}
  showUI(_html: string, _options?: unknown): void {}

  /** 만들어진 텍스트 노드만 골라낸다. */
  texts(): FakeText[] {
    return this.created.filter((n): n is FakeText => n.type === "TEXT");
  }

  frames(): FakeFrame[] {
    return this.created.filter((n): n is FakeFrame => n.type === "FRAME");
  }
}

/** 전역에 심는다. `nodes.ts`가 `figma`를 전역으로 쓰기 때문이다. */
export function installFakeFigma(): FakeFigma {
  const fake = new FakeFigma();
  (globalThis as { figma?: unknown }).figma = fake;
  return fake;
}
