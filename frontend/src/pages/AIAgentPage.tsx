import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Activity,
  Bot,
  CheckCircle2,
  FileCode,
  RotateCcw,
  Send,
  Sparkles,
  Terminal,
  User,
} from 'lucide-react';
import { projectsApi } from '../api/projects';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { CodeBlock } from '../components/common/CodeBlock';
import { Input } from '../components/common/Input';
import { Spinner } from '../components/common/Spinner';
import { useToast } from '../context/ToastContext';

interface ChatMessage {
  id: string;
  sender: 'user' | 'agent';
  text: string;
  toolCalls?: any[];
  sources?: string[];
  iterations?: number;
  timestamp: Date;
}

export const AIAgentPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'agent',
      text: 'Hello! I am DevPilot AI Agent. I can reason across your codebase AST symbols, semantic code embeddings, Git history, and static dependency graph. Ask me anything!',
      timestamp: new Date(),
    },
  ]);
  const [inputQuery, setInputQuery] = useState('');
  const [provider, setProvider] = useState<string>('groq');
  const [model, setModel] = useState<string>('openai/gpt-oss-120b');
  const [isAsking, setIsAsking] = useState(false);
  const { showToast } = useToast();

  const availableModels = [
    { value: 'openai/gpt-oss-120b', label: 'openai/gpt-oss-120b (Recommended)' },
    { value: 'openai/gpt-oss-20b', label: 'openai/gpt-oss-20b (Fast)' },
    { value: 'qwen/qwen3.6-27b', label: 'qwen/qwen3.6-27b' },
    { value: 'qwen/qwen3.8-27b', label: 'qwen/qwen3.8-27b' },
  ];

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputQuery.trim() || !projectId || isAsking) return;

    const userMessage: ChatMessage = {
      id: Math.random().toString(36).substring(2, 9),
      sender: 'user',
      text: inputQuery.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputQuery('');
    setIsAsking(true);

    try {
      const res = await projectsApi.askAgent(projectId, {
        question: userMessage.text,
        provider: provider || undefined,
        model: model || undefined,
      });

      const agentMessage: ChatMessage = {
        id: Math.random().toString(36).substring(2, 9),
        sender: 'agent',
        text: res.answer,
        toolCalls: res.tool_calls,
        iterations: res.iterations,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, agentMessage]);
    } catch (err: any) {
      showToast(err.message || 'Agent error', 'error');
      const errorMessage: ChatMessage = {
        id: Math.random().toString(36).substring(2, 9),
        sender: 'agent',
        text: `Error communicating with DevPilot Agent: ${err.message || 'Unknown error'}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsAsking(false);
    }
  };

  const handleClearHistory = () => {
    setMessages([
      {
        id: 'welcome',
        sender: 'agent',
        text: 'Hello! I am DevPilot AI Agent. I can reason across your codebase AST symbols, semantic code embeddings, Git history, and static dependency graph. Ask me anything!',
        timestamp: new Date(),
      },
    ]);
    showToast('Conversation cleared', 'info');
  };

  const samplePrompts = [
    'What functions call hash_password and what could break if I change it?',
    'What are the key dependencies of auth.py?',
    'Find functions related to database connections or storage',
  ];

  return (
    <div className="page-wrapper" style={{ maxWidth: '1000px' }}>
      <div className="page-header">
        <div>
          <h2 className="page-title">AI Codebase Agent</h2>
          <p className="page-subtitle">
            Autonomous multi-turn reasoning with validated tool use and verified source citations.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Model:</span>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              style={{
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '0.35rem 0.6rem',
                color: 'var(--text-primary)',
                fontSize: '0.8rem',
              }}
            >
              {availableModels.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClearHistory}
            leftIcon={<RotateCcw size={14} />}
          >
            Clear Chat
          </Button>
        </div>
      </div>

      {/* Suggested prompts */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', overflowX: 'auto', paddingBottom: '0.25rem' }}>
        {samplePrompts.map((prompt, idx) => (
          <button
            key={idx}
            onClick={() => setInputQuery(prompt)}
            style={{
              padding: '0.35rem 0.75rem',
              borderRadius: 'var(--radius-full)',
              backgroundColor: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.25)',
              color: '#93c5fd',
              fontSize: '0.775rem',
              whiteSpace: 'nowrap',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              cursor: 'pointer',
            }}
          >
            <Sparkles size={13} />
            <span>{prompt}</span>
          </button>
        ))}
      </div>

      {/* Chat Messages Container */}
      <Card padding="md" style={{ minHeight: '520px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1.25rem', padding: '0.5rem' }}>
          {messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                display: 'flex',
                gap: '0.85rem',
                alignItems: 'flex-start',
                alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '90%',
              }}
            >
              <div
                style={{
                  width: '30px',
                  height: '30px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: msg.sender === 'user' ? 'var(--bg-tertiary)' : 'var(--accent-blue-subtle)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: msg.sender === 'user' ? 'var(--text-primary)' : 'var(--accent-blue)',
                  flexShrink: 0,
                  marginTop: '2px',
                }}
              >
                {msg.sender === 'user' ? <User size={15} /> : <Bot size={15} />}
              </div>

              <div
                style={{
                  padding: '0.75rem 1rem',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: msg.sender === 'user' ? 'var(--bg-tertiary)' : 'var(--bg-surface)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-primary)',
                  fontSize: '0.875rem',
                  lineHeight: 1.55,
                  whiteSpace: 'pre-wrap',
                }}
              >
                {msg.text}

                {/* Tool calls activity breakdown */}
                {msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div style={{ marginTop: '0.75rem', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.5rem' }}>
                    <div style={{ fontSize: '0.725rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.35rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <Terminal size={12} />
                      <span>Tools Executed ({msg.toolCalls.length}):</span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                      {msg.toolCalls.map((tc, tidx) => (
                        <span
                          key={tidx}
                          style={{
                            fontSize: '0.725rem',
                            padding: '0.15rem 0.5rem',
                            borderRadius: 'var(--radius-sm)',
                            backgroundColor: 'var(--bg-input)',
                            border: '1px solid var(--border-subtle)',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          {typeof tc === 'string' ? tc : tc.tool || tc.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {isAsking && (
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', color: 'var(--text-secondary)' }}>
              <Spinner size="sm" />
              <span style={{ fontSize: '0.85rem' }}>DevPilot Agent is reasoning and executing tools...</span>
            </div>
          )}
        </div>

        {/* Input box */}
        <form onSubmit={handleSend} style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
          <Input
            placeholder="Ask anything about the codebase architecture, callers, impact, or commits..."
            value={inputQuery}
            onChange={(e) => setInputQuery(e.target.value)}
            disabled={isAsking}
          />
          <Button
            variant="primary"
            type="submit"
            isLoading={isAsking}
            disabled={!inputQuery.trim()}
            leftIcon={<Send size={16} />}
          >
            Send
          </Button>
        </form>
      </Card>
    </div>
  );
};
