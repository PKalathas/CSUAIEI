import { useRef, useState } from 'react';
import Modal from './Modal';

interface Props {
  onClose: () => void;
}

type Mode = 'write' | 'file';

export default function UploadAgentModal({ onClose }: Props) {
  const [mode, setMode] = useState<Mode>('write');
  const [instructions, setInstructions] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFiles(files: FileList | null) {
    if (files && files[0]) setFile(files[0]);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  const canSave = mode === 'write' ? instructions.trim().length > 0 : file !== null;

  return (
    <Modal title="Upload Agent Instructions" onClose={onClose} width={520}>
      <p className="modal-subtitle">
        Define how the AI agent should guide students during this lab.
      </p>

      <div className="modal-tab-switch">
        <button
          className={`modal-tab${mode === 'write' ? ' modal-tab-active' : ''}`}
          onClick={() => setMode('write')}
        >
          Write Instructions
        </button>
        <button
          className={`modal-tab${mode === 'file' ? ' modal-tab-active' : ''}`}
          onClick={() => setMode('file')}
        >
          Upload File
        </button>
      </div>

      {mode === 'write' ? (
        <textarea
          className="modal-textarea"
          placeholder={`e.g. "Only give progressive hints. Never reveal the full solution. If a student asks for the answer directly, redirect them with a guiding question. Focus hints on pointer manipulation and memory management."`}
          value={instructions}
          onChange={e => setInstructions(e.target.value)}
          rows={8}
        />
      ) : (
        <>
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
              accept=".txt,.md,.pdf"
              style={{ display: 'none' }}
              onChange={e => handleFiles(e.target.files)}
            />
            {file ? (
              <>
                <div className="dropzone-icon">📄</div>
                <div className="dropzone-filename">{file.name}</div>
              </>
            ) : (
              <>
                <div className="dropzone-icon">⬆</div>
                <div className="dropzone-cta">Drag &amp; drop your instructions file</div>
                <div className="dropzone-meta">or click to browse</div>
                <div className="dropzone-hint">TXT, MD, PDF · Max 5 MB</div>
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
        </>
      )}

      <div className="modal-footer">
        <button className="btn-outline" onClick={onClose}>Cancel</button>
        <button
          className="btn-primary"
          disabled={!canSave}
          onClick={onClose}
        >
          Save Instructions
        </button>
      </div>
    </Modal>
  );
}
