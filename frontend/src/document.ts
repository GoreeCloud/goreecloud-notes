export type GoreeMarkType = "bold" | "italic" | "strike" | "code" | "noteLink";

export type GoreeMark = {
  type: GoreeMarkType;
  note_id?: string;
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
  | "attachmentImage"
  | "text"
  | "hardBreak";

export type GoreeNode = {
  type: GoreeNodeType;
  text?: string;
  level?: 1 | 2 | 3;
  marks?: GoreeMark[];
  content?: GoreeNode[];
  attachment_id?: string;
  alt?: string;
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

const supportedMarks = new Set<GoreeMarkType>(["bold", "italic", "strike", "code", "noteLink"]);
const supportedNodes = new Set<GoreeNodeType>([
  "paragraph",
  "heading",
  "bulletList",
  "orderedList",
  "listItem",
  "blockquote",
  "codeBlock",
  "horizontalRule",
  "attachmentImage",
  "text",
  "hardBreak",
]);
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export class DocumentContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DocumentContractError";
  }
}

export function emptyDocument(): NoteDocument {
  return {
    format: "goreecloud.blocks",
    version: 1,
    blocks: [],
  };
}

function sanitizeMarks(marks: unknown): GoreeMark[] | undefined {
  if (marks === undefined) return undefined;
  if (!Array.isArray(marks)) {
    throw new DocumentContractError("Note text marks are not compatible with this GoreeCloud Notes version.");
  }

  const clean: GoreeMark[] = [];
  const seen = new Set<string>();
  for (const mark of marks) {
    if (typeof mark !== "object" || mark === null || !("type" in mark)) {
      throw new DocumentContractError("Note text contains an invalid formatting mark.");
    }
    const raw = mark as Record<string, unknown>;
    const type = String(raw.type) as GoreeMarkType;
    if (!supportedMarks.has(type)) {
      throw new DocumentContractError(`Unsupported GoreeCloud Notes text mark: ${type}`);
    }

    if (type === "noteLink") {
      const rawNoteId = typeof raw.note_id === "string"
        ? raw.note_id
        : typeof raw.attrs === "object" && raw.attrs !== null && typeof (raw.attrs as Record<string, unknown>).noteId === "string"
          ? String((raw.attrs as Record<string, unknown>).noteId)
          : "";
      const noteId = rawNoteId.toLowerCase();
      if (!uuidPattern.test(noteId)) {
        throw new DocumentContractError("Internal note link contains an invalid note reference.");
      }
      const key = `${type}:${noteId}`;
      if (!seen.has(key)) {
        clean.push({ type, note_id: noteId });
        seen.add(key);
      }
      continue;
    }

    if (!seen.has(type)) {
      clean.push({ type });
      seen.add(type);
    }
  }

  return clean.length > 0 ? clean : undefined;
}

function sanitizeGoreeNode(value: unknown): GoreeNode {
  if (typeof value !== "object" || value === null || !("type" in value)) {
    throw new DocumentContractError("Note content contains an invalid document node.");
  }

  const raw = value as Record<string, unknown>;
  const type = String(raw.type) as GoreeNodeType;
  if (!supportedNodes.has(type)) {
    throw new DocumentContractError(`Unsupported GoreeCloud Notes document node: ${String(raw.type)}`);
  }

  if (type === "text") {
    if (raw.text !== undefined && typeof raw.text !== "string") {
      throw new DocumentContractError("Note text content is invalid.");
    }
    return {
      type,
      text: typeof raw.text === "string" ? raw.text : "",
      marks: sanitizeMarks(raw.marks),
    };
  }

  if (type === "hardBreak" || type === "horizontalRule") {
    return { type };
  }

  if (type === "attachmentImage") {
    const attachmentId = typeof raw.attachment_id === "string" ? raw.attachment_id.toLowerCase() : "";
    if (!uuidPattern.test(attachmentId)) {
      throw new DocumentContractError("Inline image contains an invalid attachment reference.");
    }
    if (raw.alt !== undefined && typeof raw.alt !== "string") {
      throw new DocumentContractError("Inline image alt text is invalid.");
    }
    return {
      type,
      attachment_id: attachmentId,
      alt: typeof raw.alt === "string" ? raw.alt : "",
    };
  }

  // Compatibility with the original Milestone 0 paragraph envelope, which used
  // { type: "paragraph", text: "..." } before rich editing was introduced.
  const legacyText = typeof raw.text === "string" && raw.text.length > 0
    ? [{ type: "text" as const, text: raw.text }]
    : [];
  if (raw.content !== undefined && !Array.isArray(raw.content)) {
    throw new DocumentContractError("Note node content is invalid.");
  }
  const children = Array.isArray(raw.content)
    ? raw.content.map(sanitizeGoreeNode)
    : legacyText;

  if (type === "heading") {
    const rawLevel = Number(raw.level);
    if (rawLevel !== 1 && rawLevel !== 2 && rawLevel !== 3) {
      throw new DocumentContractError("Heading level is not compatible with this GoreeCloud Notes version.");
    }
    return { type, level: rawLevel, content: children };
  }

  return { type, content: children };
}

export function sanitizeDocument(value: unknown): NoteDocument {
  if (typeof value !== "object" || value === null) {
    throw new DocumentContractError("Note document is unavailable or invalid.");
  }

  const raw = value as Record<string, unknown>;
  if (raw.format !== "goreecloud.blocks" || raw.version !== 1 || !Array.isArray(raw.blocks)) {
    throw new DocumentContractError(
      "This note uses a document format that this GoreeCloud Notes version cannot safely edit.",
    );
  }

  return {
    format: "goreecloud.blocks",
    version: 1,
    blocks: raw.blocks.map(sanitizeGoreeNode),
  };
}

function goreeNodeToTiptap(node: GoreeNode): TiptapNode {
  if (node.type === "text") {
    return {
      type: "text",
      text: node.text ?? "",
      marks: node.marks?.map((mark) => ({
        type: mark.type,
        attrs: mark.type === "noteLink" ? { noteId: mark.note_id ?? "" } : undefined,
      })),
    };
  }

  if (node.type === "hardBreak" || node.type === "horizontalRule") {
    return { type: node.type };
  }

  if (node.type === "attachmentImage") {
    return {
      type: "attachmentImage",
      attrs: {
        attachmentId: node.attachment_id ?? "",
        alt: node.alt ?? "",
      },
    };
  }

  return {
    type: node.type,
    attrs: node.type === "heading" ? { level: node.level ?? 1 } : undefined,
    content: node.content?.map(goreeNodeToTiptap),
  };
}

export function goreeToTiptap(document: NoteDocument): TiptapNode {
  const clean = sanitizeDocument(document);
  return {
    type: "doc",
    content: clean.blocks.length > 0
      ? clean.blocks.map(goreeNodeToTiptap)
      : [{ type: "paragraph" }],
  };
}

function tiptapNodeToGoree(node: TiptapNode): GoreeNode {
  const type = node.type as GoreeNodeType;
  if (!supportedNodes.has(type)) {
    throw new DocumentContractError(`Editor produced an unsupported document node: ${node.type}`);
  }

  if (type === "text") {
    const rawMarks = node.marks?.map((mark) => mark.type === "noteLink"
      ? { type: mark.type, note_id: typeof mark.attrs?.noteId === "string" ? mark.attrs.noteId : "" }
      : { type: mark.type });
    return {
      type,
      text: typeof node.text === "string" ? node.text : "",
      marks: sanitizeMarks(rawMarks),
    };
  }

  if (type === "hardBreak" || type === "horizontalRule") {
    return { type };
  }

  if (type === "attachmentImage") {
    const attachmentId = typeof node.attrs?.attachmentId === "string"
      ? node.attrs.attachmentId.toLowerCase()
      : "";
    if (!uuidPattern.test(attachmentId)) {
      throw new DocumentContractError("Editor produced an invalid inline image attachment reference.");
    }
    return {
      type,
      attachment_id: attachmentId,
      alt: typeof node.attrs?.alt === "string" ? node.attrs.alt : "",
    };
  }

  const children = node.content?.map(tiptapNodeToGoree);

  if (type === "heading") {
    const rawLevel = Number(node.attrs?.level);
    if (rawLevel !== 1 && rawLevel !== 2 && rawLevel !== 3) {
      throw new DocumentContractError("Editor produced an unsupported heading level.");
    }
    return { type, level: rawLevel, content: children };
  }

  return { type, content: children };
}

export function tiptapToGoree(root: TiptapNode): NoteDocument {
  const blocks = Array.isArray(root.content)
    ? root.content.map(tiptapNodeToGoree)
    : [];
  return sanitizeDocument({ format: "goreecloud.blocks", version: 1, blocks });
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
  if (node.type === "attachmentImage") {
    return node.alt ? `[Image: ${node.alt}]\n` : "[Image]\n";
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
