import {
  sanitizeDocument,
  type GoreeNode,
  type NoteDocument,
} from "./document";

export type NoteTemplate = {
  id: string;
  label: string;
  description: string;
  document: NoteDocument;
};

function text(value: string): GoreeNode {
  return { type: "text", text: value };
}

function paragraph(value = ""): GoreeNode {
  return {
    type: "paragraph",
    content: value ? [text(value)] : [],
  };
}

function heading(level: 1 | 2 | 3, value: string): GoreeNode {
  return {
    type: "heading",
    level,
    content: [text(value)],
  };
}

function bulletList(items: string[]): GoreeNode {
  return {
    type: "bulletList",
    content: items.map((item) => ({
      type: "listItem",
      content: [paragraph(item)],
    })),
  };
}

function template(blocks: GoreeNode[]): NoteDocument {
  return sanitizeDocument({
    format: "goreecloud.blocks",
    version: 1,
    blocks,
  });
}

export const NOTE_TEMPLATES: readonly NoteTemplate[] = [
  {
    id: "meeting-notes",
    label: "Meeting notes",
    description: "Agenda, discussion, decisions, and action items.",
    document: template([
      paragraph("Date: "),
      paragraph("Attendees: "),
      heading(2, "Agenda"),
      bulletList(["Topic 1", "Topic 2"]),
      heading(2, "Notes"),
      paragraph(),
      heading(2, "Decisions"),
      paragraph(),
      heading(2, "Action items"),
      bulletList(["Owner — action — due date"]),
    ]),
  },
  {
    id: "project-brief",
    label: "Project brief",
    description: "Outcome, scope, milestones, risks, and next step.",
    document: template([
      paragraph("Owner: "),
      paragraph("Status: Planning"),
      heading(2, "Outcome"),
      paragraph(),
      heading(2, "Scope"),
      bulletList(["In scope — ", "Out of scope — "]),
      heading(2, "Milestones"),
      bulletList(["Milestone — target date"]),
      heading(2, "Risks"),
      bulletList(["Risk — mitigation"]),
      heading(2, "Next step"),
      paragraph(),
    ]),
  },
  {
    id: "research-note",
    label: "Research note",
    description: "Question, sources, findings, evidence, and open questions.",
    document: template([
      paragraph("Research question: "),
      heading(2, "Sources"),
      bulletList(["Source — URL or citation — access date"]),
      heading(2, "Findings"),
      bulletList(["Finding — supporting source"]),
      heading(2, "Evidence"),
      {
        type: "blockquote",
        content: [paragraph("Summarize or quote the supporting evidence here.")],
      },
      heading(2, "Open questions"),
      bulletList(["Question to verify"]),
    ]),
  },
  {
    id: "decision-record",
    label: "Decision record",
    description: "Context, decision, alternatives, consequences, and review trigger.",
    document: template([
      paragraph("Date: "),
      paragraph("Status: Proposed"),
      heading(2, "Context"),
      paragraph(),
      heading(2, "Decision"),
      paragraph(),
      heading(2, "Alternatives considered"),
      bulletList(["Alternative — reason not selected"]),
      heading(2, "Consequences"),
      bulletList(["Positive — ", "Tradeoff — "]),
      heading(2, "Review trigger"),
      paragraph(),
    ]),
  },
  {
    id: "daily-journal",
    label: "Daily journal",
    description: "Highlights, notes, learning, and tomorrow's focus.",
    document: template([
      paragraph("Date: "),
      heading(2, "Highlights"),
      bulletList(["Highlight"]),
      heading(2, "Notes"),
      paragraph(),
      heading(2, "What I learned"),
      bulletList(["Learning"]),
      heading(2, "Tomorrow"),
      bulletList(["Priority"]),
    ]),
  },
] as const;

export function noteTemplateById(templateId: string): NoteTemplate | null {
  return NOTE_TEMPLATES.find((item) => item.id === templateId) ?? null;
}
