import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';

export interface CodeBlockProps {
  code: string;
  language?: string;
  maxHeight?: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  language = 'text',
  maxHeight = '400px',
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      style={{
        position: 'relative',
        borderRadius: 'var(--radius-md)',
        backgroundColor: '#050811',
        border: '1px solid var(--border-subtle)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.4rem 0.75rem',
          backgroundColor: 'rgba(255, 255, 255, 0.02)',
          borderBottom: '1px solid var(--border-subtle)',
          fontSize: '0.75rem',
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          fontWeight: 600,
        }}
      >
        <span>{language}</span>
        <button
          onClick={handleCopy}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            color: copied ? 'var(--accent-emerald)' : 'var(--text-secondary)',
            fontSize: '0.75rem',
            padding: '0.2rem 0.4rem',
            borderRadius: 'var(--radius-sm)',
            transition: 'color 0.15s ease',
          }}
          aria-label="Copy code"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <pre
        style={{
          margin: 0,
          padding: '0.75rem 1rem',
          overflowX: 'auto',
          maxHeight,
          fontSize: '0.85rem',
          lineHeight: 1.5,
          color: '#e2e8f0',
        }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
};
