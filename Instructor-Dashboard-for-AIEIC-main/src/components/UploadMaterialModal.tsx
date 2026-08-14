import { useRef, useState } from 'react';
import Modal from './Modal';

interface Props {
  onClose: () => void;
}

export default function UploadMaterialModal({ onClose }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    if (files && files[0]) setFile(files[0]);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  function formatSize(bytes: number) {
    return bytes < 1024 * 1024
      ? `${(bytes / 1024).toFixed(1)} KB`
      : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  return (
    <Modal title="Upload Lab Material" onClose={onClose}>
      <p className="modal-subtitle">
        Attach the lab specification or supporting files for this session.
      </p>

      <div
        className={`dropzone${dragging ? ' dropzone-active' : ''}${file ? ' dropzone-filled' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.doc,.docx,.txt"
          style={{ display: 'none' }}
          onChange={e => handleFiles(e.target.files)}
        />
        {file ? (
          <>
            <div className="dropzone-icon">📄</div>
            <div className="dropzone-filename">{file.name}</div>
            <div className="dropzone-meta">{formatSize(file.size)}</div>
          </>
        ) : (
          <>
            <div className="dropzone-icon">⬆</div>
            <div className="dropzone-cta">Drag &amp; drop your file here</div>
            <div className="dropzone-meta">or click to browse</div>
            <div className="dropzone-hint">PDF, DOCX, TXT · Max 25 MB</div>
          </>
        )}
      </div>

      {file && (
        <button
          className="dropzone-clear"
          onClick={e => { e.stopPropagation(); setFile(null); }}
        >
          Remove file
        </button>
      )}

      <div className="modal-footer">
        <button className="btn-outline" onClick={onClose}>Cancel</button>
        <button
          className="btn-primary"
          disabled={!file}
          onClick={onClose}
        >
          Upload
        </button>
      </div>
    </Modal>
  );
}
