import {
  attachmentDownloadUrl,
  attachmentPreviewUrl,
  isAttachmentPreviewable,
  type Attachment,
} from "./api";

type AttachmentItemProps = {
  attachment: Attachment;
  disabled: boolean;
  onRemove: (attachment: Attachment) => void;
};

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function AttachmentItem({ attachment, disabled, onRemove }: AttachmentItemProps) {
  const previewable = isAttachmentPreviewable(attachment);
  const downloadUrl = attachmentDownloadUrl(attachment.id);

  return (
    <div className={`attachment-row${previewable ? " previewable" : ""}`}>
      {previewable ? (
        <a
          className="attachment-preview"
          href={downloadUrl}
          aria-label={`Open ${attachment.filename}`}
        >
          <img
            src={attachmentPreviewUrl(attachment.id)}
            alt={`Preview of ${attachment.filename}`}
            loading="lazy"
          />
        </a>
      ) : null}
      <div className="attachment-details">
        <a href={downloadUrl}>{attachment.filename}</a>
        <span>{formatBytes(attachment.size_bytes)} · {attachment.media_type}</span>
        {previewable ? <span>Private raster-image preview</span> : null}
      </div>
      <button type="button" onClick={() => onRemove(attachment)} disabled={disabled}>Remove</button>
    </div>
  );
}
