import { lazy, Suspense } from "react";

import type { NoteDocument } from "./document";

export type RichNoteEditorProps = {
  noteId: string;
  value: NoteDocument;
  disabled?: boolean;
  navigationDisabled?: boolean;
  onChange: (document: NoteDocument) => void;
  onOpenNote: (noteId: string) => void;
};

const LazyRichNoteEditor = lazy(async () => {
  const module = await import("./RichNoteEditorCore");
  return { default: module.RichNoteEditor };
});

export function RichNoteEditor(props: RichNoteEditorProps) {
  return (
    <Suspense fallback={<div className="rich-editor-loading" role="status">Preparing editor…</div>}>
      <LazyRichNoteEditor {...props} />
    </Suspense>
  );
}
