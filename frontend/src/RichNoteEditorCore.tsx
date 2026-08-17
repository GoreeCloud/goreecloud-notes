import { useEffect, useState } from "react";
import { Node } from "@tiptap/core";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";

import {
  attachmentPreviewUrl,
  isAttachmentPreviewable,
  listAttachments,
  type Attachment,
} from "./api";
import {
  goreeToTiptap,
  tiptapToGoree,
  type NoteDocument,
  type TiptapNode,
} from "./document";
import { NOTE_TEMPLATES, noteTemplateById } from "./noteTemplates";

const AttachmentImage = Node.create({
  name: "attachmentImage",
  group: "block",
  atom: true,
  draggable: true,
  selectable: true,

  addAttributes() {
    return {
      attachmentId: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-attachment-id") ?? "",
      },
      alt: {
        default: "",
        parseHTML: (element) => element.getAttribute("alt") ?? "",
      },
    };
  },

  parseHTML() {
    return [{ tag: "img[data-goree-attachment-image]" }];
  },

  renderHTML({ HTMLAttributes }) {
    const attachmentId = typeof HTMLAttributes.attachmentId === "string"
      ? HTMLAttributes.attachmentId
      : "";
    const alt = typeof HTMLAttributes.alt === "string" ? HTMLAttributes.alt : "";
    return [
      "img",
      {
        "data-goree-attachment-image": "true",
        "data-attachment-id": attachmentId,
        src: attachmentPreviewUrl(attachmentId),
        alt,
        loading: "lazy",
        referrerpolicy: "no-referrer",
      },
    ];
  },
});

type RichNoteEditorProps = {
  noteId: string;
  value: NoteDocument;
  disabled?: boolean;
  onChange: (document: NoteDocument) => void;
};

type ToolbarButtonProps = {
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
};

function ToolbarButton({ label, active = false, disabled = false, onClick }: ToolbarButtonProps) {
  return (
    <button
      className={`rich-toolbar-button${active ? " active" : ""}`}
      type="button"
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

export function RichNoteEditor({ noteId, value, disabled = false, onChange }: RichNoteEditorProps) {
  const [imageAttachments, setImageAttachments] = useState<Attachment[]>([]);
  const [selectedImageId, setSelectedImageId] = useState("");
  const [attachmentStatus, setAttachmentStatus] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState(NOTE_TEMPLATES[0]?.id ?? "");
  const [templateStatus, setTemplateStatus] = useState("");

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
      }),
      AttachmentImage,
    ],
    content: goreeToTiptap(value),
    immediatelyRender: false,
    editable: !disabled,
    editorProps: {
      attributes: {
        class: "rich-editor-content",
        spellcheck: "true",
        "aria-label": "Note body",
      },
    },
    onUpdate: ({ editor: activeEditor }) => {
      onChange(tiptapToGoree(activeEditor.getJSON() as TiptapNode));
    },
  });

  async function refreshImageAttachments() {
    try {
      const attachments = (await listAttachments(noteId)).filter(isAttachmentPreviewable);
      setImageAttachments(attachments);
      setSelectedImageId((current) => attachments.some((item) => item.id === current) ? current : "");
      setAttachmentStatus("");
    } catch (error) {
      setImageAttachments([]);
      setSelectedImageId("");
      setAttachmentStatus(error instanceof Error ? error.message : "Unable to refresh image attachments.");
    }
  }

  useEffect(() => {
    let cancelled = false;
    setTemplateStatus("");
    void listAttachments(noteId)
      .then((attachments) => {
        if (cancelled) return;
        const images = attachments.filter(isAttachmentPreviewable);
        setImageAttachments(images);
        setSelectedImageId("");
        setAttachmentStatus("");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setImageAttachments([]);
        setSelectedImageId("");
        setAttachmentStatus(error instanceof Error ? error.message : "Unable to load image attachments.");
      });
    return () => {
      cancelled = true;
    };
  }, [noteId]);

  useEffect(() => {
    if (!editor) {
      return;
    }
    editor.setEditable(!disabled);
  }, [disabled, editor]);

  useEffect(() => {
    if (!editor) {
      return;
    }

    const next = goreeToTiptap(value);
    const current = editor.getJSON() as TiptapNode;
    if (JSON.stringify(current) !== JSON.stringify(next)) {
      editor.commands.setContent(next, { emitUpdate: false });
    }
  }, [editor, noteId, value]);

  if (!editor) {
    return <div className="rich-editor-loading">Preparing editor…</div>;
  }

  const selectedImage = imageAttachments.find((attachment) => attachment.id === selectedImageId) ?? null;
  const selectedTemplate = noteTemplateById(selectedTemplateId);

  function insertSelectedImage() {
    if (!selectedImage || disabled || !editor) return;
    editor
      .chain()
      .focus()
      .insertContent([
        {
          type: "attachmentImage",
          attrs: {
            attachmentId: selectedImage.id,
            alt: selectedImage.filename,
          },
        },
        { type: "paragraph" },
      ])
      .run();
  }

  function insertSelectedTemplate() {
    if (!selectedTemplate || disabled || !editor) return;

    const templateRoot = goreeToTiptap(selectedTemplate.document);
    const blocks = templateRoot.content ?? [];
    const inserted = editor.isEmpty
      ? editor.commands.setContent(templateRoot)
      : editor
        .chain()
        .focus()
        .insertContent([
          { type: "horizontalRule" },
          ...blocks,
        ])
        .run();

    setTemplateStatus(
      inserted
        ? `Inserted ${selectedTemplate.label}.`
        : `Could not insert ${selectedTemplate.label}.`,
    );
  }

  return (
    <div className="rich-editor-shell">
      <div className="rich-toolbar" role="toolbar" aria-label="Rich text formatting">
        <ToolbarButton
          label="B"
          active={editor.isActive("bold")}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleBold().run()}
        />
        <ToolbarButton
          label="I"
          active={editor.isActive("italic")}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        />
        <ToolbarButton
          label="S"
          active={editor.isActive("strike")}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleStrike().run()}
        />
        <ToolbarButton
          label="Code"
          active={editor.isActive("code")}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleCode().run()}
        />
        <span className="rich-toolbar-separator" aria-hidden="true" />
        {[1, 2, 3].map((level) => (
          <ToolbarButton
            key={level}
            label={`H${level}`}
            active={editor.isActive("heading", { level })}
            disabled={disabled}
            onClick={() => editor.chain().focus().toggleHeading({ level: level as 1 | 2 | 3 }).run()}
          />
        ))}
        <span className="rich-toolbar-separator" aria-hidden="true" />
        <ToolbarButton
          label="Bullets"
          active={editor.isActive("bulletList")}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        />
        <ToolbarButton
          label="Numbers"
          active={editor.isActive("orderedList")}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        />
        <ToolbarButton
          label="Quote"
          active={editor.isActive("blockquote")}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
        />
        <ToolbarButton
          label="Block code"
          active={editor.isActive("codeBlock")}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        />
        <ToolbarButton
          label="Rule"
          disabled={disabled}
          onClick={() => editor.chain().focus().setHorizontalRule().run()}
        />
        <span className="rich-toolbar-separator" aria-hidden="true" />
        <select
          className="rich-toolbar-select"
          aria-label="Note template"
          value={selectedTemplateId}
          disabled={disabled || NOTE_TEMPLATES.length === 0}
          onChange={(event) => {
            setSelectedTemplateId(event.target.value);
            setTemplateStatus("");
          }}
        >
          {NOTE_TEMPLATES.map((template) => (
            <option value={template.id} key={template.id}>{template.label}</option>
          ))}
        </select>
        <ToolbarButton
          label="Insert template"
          disabled={disabled || selectedTemplate === null}
          onClick={insertSelectedTemplate}
        />
        <span className="rich-toolbar-separator" aria-hidden="true" />
        <select
          className="rich-toolbar-select"
          aria-label="Inline image attachment"
          value={selectedImageId}
          disabled={disabled || imageAttachments.length === 0}
          onFocus={() => void refreshImageAttachments()}
          onChange={(event) => setSelectedImageId(event.target.value)}
        >
          <option value="">{imageAttachments.length === 0 ? "No image attachments" : "Choose image"}</option>
          {imageAttachments.map((attachment) => (
            <option value={attachment.id} key={attachment.id}>{attachment.filename}</option>
          ))}
        </select>
        <ToolbarButton
          label="Insert image"
          disabled={disabled || selectedImage === null}
          onClick={insertSelectedImage}
        />
        <span className="rich-toolbar-separator" aria-hidden="true" />
        <ToolbarButton
          label="Undo"
          disabled={disabled || !editor.can().chain().focus().undo().run()}
          onClick={() => editor.chain().focus().undo().run()}
        />
        <ToolbarButton
          label="Redo"
          disabled={disabled || !editor.can().chain().focus().redo().run()}
          onClick={() => editor.chain().focus().redo().run()}
        />
      </div>
      {selectedTemplate ? (
        <div className="rich-toolbar-status" aria-live="polite">
          {templateStatus || selectedTemplate.description}
        </div>
      ) : null}
      {attachmentStatus ? <div className="rich-toolbar-status" role="status">{attachmentStatus}</div> : null}
      <EditorContent editor={editor} />
    </div>
  );
}
