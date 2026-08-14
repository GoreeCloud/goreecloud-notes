export type GoreeMarkType = "bold" | "italic" | "strike" | "code";

export type GoreeMark = {
  type: GoreeMarkType;
};

export type GoreeNodeType =
  | "paragraph"
  | "heading"
  | "bulletList"
  | "orderedList"
  | "listItem"
  | "blockquote"
  | "codeBlock"
  | "horizontalRule"
  | "text"
  | "hardBreak";

export type GoreeNode = {
  type: GoreeNodeType;
  text?: string;
  level?: 1 | 2 | 3;
  marks?: GoreeMark[];
  content?: GoreeNode[];
};

export type NoteDocument = {
  format: "goreecloud.blocks";
  version: 1;
  blocks: GoreeNode[];
};

export type TiptapNode = {
  type: string;
  text?: string;
  attrs?: Record<string, unknown>;
  marks?: Array<{ type: string; attrs?: Record<string, unknown> }>;
  content?: TiptapNode[];
};

const supportedMarks = new Set<GoreeMarkType>(["bold", "italic", "strike", "code"]);
const supportedNodes = new Set<GoreeNodeType>([
  "paragraph",
  "heading",
  "bulletList",
  "orderedList",
  "listItem",
  "blockquote",
  "codeBlock",
  "horizontalRule",
  "text",
  "hardBreak",
]);

export function emptyDocument(): NoteDocument {
  return {
    format: "goreecloud.blocks",
    version: 1,
    blocks: [],
  };
}

function sanitizeMarks(marks: unknown): GoreeMark[] | undefined {
  if (!Array.isArray(marks)) {
    return undefined;
  }

  const clean = marks
    .map((mark) => {
      if (typeof mark !== "object" || mark === null || !("type" in mark)) {
        return null;
      }
      const type = String(mark.type) as GoreeMarkType;
      return supportedMarks.has(type) ? { type } : null;
    })
    .filter((mark): mark is GoreeMark => mark !== null);

  return clean.length > 0 ? clean : undefined;
}

function sanitizeGoreeNode(value: unknown): GoreeNode | null {
  if (typeof value !== "object" || value === null || !("type" in value)) {
    return null;
  }

  const raw = value as Record<string, unknown>;
  const type = String(raw.type) as GoreeNodeType;
  if (!supportedNodes.has(type)) {
    return null;
  }

  if (type === "text") {
    return {
      type,
      text: typeof raw.text === "string" ? raw.text : "",
      marks: sanitizeMarks(raw.marks),
    };
  }

  if (type === "hardBreak" || type === "horizontalRule") {
    return { type };
  }

  // Compatibility with the original Milestone 0 paragraph envelope, which used
  // { type: "paragraph", text: "..." } before rich editing was introduced.
  const legacyText = typeof raw.text === "string" && raw.text.length > 0
    ? [{ type: "text" as const, text: raw.text }]
    : [];
  const children = Array.isArray(raw.content)
    ? raw.content.map(sanitizeGoreeNode).filter((node): node is GoreeNode => node !== null)
    : legacyText;

  if (type === "heading") {
    const rawLevel = Number(raw.level);
    const level: 1 | 2 | 3 = rawLevel === 2 || rawLevel === 3 ? rawLevel : 1;
    return { type, level, content: children };
  }

  return { type, content: children };
}

export function sanitizeDocument(value: unknown): NoteDocument {
  if (typeof value !== "object" || value === null) {
    return emptyDocument();
  }

  const raw = value as Record<string, unknown>;
  if (raw.format !== "goreecloud.blocks" || raw.version !== 1 || !Array.isArray(raw.blocks)) {
    return emptyDocument();
  }

  return {
    format: "goreecloud.blocks",
    version: 1,
    blocks: raw.blocks.map(sanitizeGoreeNode).filter((node): node is GoreeNode => node !== null),
  };
}

function goreeNodeToTiptap(node: GoreeNode): TiptapNode | null {
  if (node.type === "text") {
    return {
      type: "text",
      text: node.text ?? "",
      marks: node.marks?.map((mark) => ({ type: mark.type })),
    };
  }

  if (node.type === "hardBreak" || node.type === "horizontalRule") {
    return { type: node.type };
  }

  return {
    type: node.type,
    attrs: node.type === "heading" ? { level: node.level ?? 1 } : undefined,
    content: node.content?.map(goreeNodeToTiptap).filter((item): item is TiptapNode => item !== null),
  };
}

export function goreeToTiptap(document: NoteDocument): TiptapNode {
  const clean = sanitizeDocument(document);
  return {
    type: "doc",
    content: clean.blocks.length > 0
      ? clean.blocks.map(goreeNodeToTiptap).filter((node): node is TiptapNode => node !== null)
      : [{ type: "paragraph" }],
  };
}

function tiptapNodeToGoree(node: TiptapNode): GoreeNode | null {
  const type = node.type as GoreeNodeType;
  if (!supportedNodes.has(type)) {
    return null;
  }

  if (type === "text") {
    return {
      type,
      text: typeof node.text === "string" ? node.text : "",
      marks: sanitizeMarks(node.marks),
    };
  }

  if (type === "hardBreak" || type === "horizontalRule") {
    return { type };
  }

  const children = node.content
    ?.map(tiptapNodeToGoree)
    .filter((child): child is GoreeNode => child !== null);

  if (type === "heading") {
    const rawLevel = Number(node.attrs?.level);
    const level: 1 | 2 | 3 = rawLevel === 2 || rawLevel === 3 ? rawLevel : 1;
    return { type, level, content: children };
  }

  return { type, content: children };
}

export function tiptapToGoree(root: TiptapNode): NoteDocument {
  const blocks = Array.isArray(root.content)
    ? root.content.map(tiptapNodeToGoree).filter((node): node is GoreeNode => node !== null)
    : [];
  return { format: "goreecloud.blocks", version: 1, blocks };
}

function nodePlainText(node: GoreeNode): string {
  if (node.type === "text") {
    return node.text ?? "";
  }
  if (node.type === "hardBreak") {
    return "\n";
  }
  if (node.type === "horizontalRule") {
    return "\n—\n";
  }

  const childText = (node.content ?? []).map(nodePlainText).join("");
  if (node.type === "listItem") {
    return `• ${childText}\n`;
  }
  if (node.type === "paragraph" || node.type === "heading" || node.type === "codeBlock" || node.type === "blockquote") {
    return `${childText}\n`;
  }
  return childText;
}

export function documentToPlainText(document: NoteDocument): string {
  return sanitizeDocument(document).blocks.map(nodePlainText).join("").trim();
}

export function documentsEqual(left: NoteDocument, right: NoteDocument): boolean {
  return JSON.stringify(sanitizeDocument(left)) === JSON.stringify(sanitizeDocument(right));
}
