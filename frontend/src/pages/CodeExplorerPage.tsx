import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { FileCode, Folder, Play, Search } from 'lucide-react';
import { projectsApi } from '../api/projects';
import { searchApi } from '../api/search';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { CodeBlock } from '../components/common/CodeBlock';
import { EmptyState } from '../components/common/EmptyState';
import { Input } from '../components/common/Input';
import { Spinner } from '../components/common/Spinner';
import { useToast } from '../context/ToastContext';
import { Project } from '../types/projects';
import { SymbolMatchItem } from '../types/search';

export const CodeExplorerPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [extensions, setExtensions] = useState<Record<string, number>>({});
  const [totalFiles, setTotalFiles] = useState<number>(0);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [symbols, setSymbols] = useState<SymbolMatchItem[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolMatchItem | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    if (!projectId) return;
    setIsLoading(true);
    projectsApi
      .get(projectId)
      .then((proj) => {
        setProject(proj);
        return projectsApi.scan(projectId);
      })
      .then((scanRes) => {
        setExtensions(scanRes.extensions || {});
        setTotalFiles(scanRes.total_files || 0);
      })
      .catch((err) => {
        showToast(err.message || 'Failed to scan project files', 'error');
      })
      .finally(() => setIsLoading(false));
  }, [projectId]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbolQuery.trim() || !project) return;
    try {
      setIsSearching(true);
      const res = await searchApi.searchSymbol(symbolQuery.trim(), project.path);
      setSymbols(res.matches);
      if (res.matches.length > 0) {
        setSelectedSymbol(res.matches[0]);
      } else {
        setSelectedSymbol(null);
        showToast(`No symbols found matching "${symbolQuery}"`, 'info');
      }
    } catch (err: any) {
      showToast(err.message || 'Symbol search failed', 'error');
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Codebase Explorer</h2>
          <p className="page-subtitle">
            Explore indexed AST symbols, syntactic structures, and file metrics for {project?.name}.
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '1.5rem', minHeight: '650px' }}>
        {/* Left Sidebar: Scan Breakdown & Symbol Search */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <Card title="File Breakdown">
            {isLoading ? (
              <Spinner size="sm" label="Scanning files..." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                  <span>Total Files:</span>
                  <strong style={{ color: 'var(--text-primary)' }}>{totalFiles}</strong>
                </div>
                <hr style={{ border: 'none', borderTop: '1px solid var(--border-subtle)' }} />
                <div style={{ fontWeight: 600, color: 'var(--text-secondary)', fontSize: '0.75rem', textTransform: 'uppercase' }}>
                  Extensions
                </div>
                {Object.entries(extensions).map(([ext, count]) => (
                  <div
                    key={ext}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '0.2rem 0.4rem',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    }}
                  >
                    <code>{ext || '(no ext)'}</code>
                    <span style={{ fontSize: '0.75rem', color: 'var(--accent-blue)', fontWeight: 600 }}>
                      {count}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="AST Symbol Search">
            <form onSubmit={handleSearch} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <Input
                placeholder="e.g. GraphBuilder, run_scan..."
                value={symbolQuery}
                onChange={(e) => setSymbolQuery(e.target.value)}
                leftIcon={<Search size={14} />}
              />
              <Button
                variant="secondary"
                size="sm"
                type="submit"
                isLoading={isSearching}
                leftIcon={<Search size={13} />}
              >
                Search Symbol
              </Button>
            </form>

            <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.35rem', maxHeight: '280px', overflowY: 'auto' }}>
              {symbols.map((sym, idx) => (
                <button
                  key={idx}
                  onClick={() => setSelectedSymbol(sym)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    padding: '0.45rem 0.6rem',
                    borderRadius: 'var(--radius-sm)',
                    backgroundColor: selectedSymbol === sym ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                    border: `1px solid ${selectedSymbol === sym ? 'var(--accent-blue)' : 'var(--border-subtle)'}`,
                    textAlign: 'left',
                    width: '100%',
                  }}
                >
                  <span style={{ fontWeight: 600, fontSize: '0.825rem', color: 'var(--text-primary)' }}>
                    {sym.symbol_name}
                  </span>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    {sym.symbol_type} • {sym.file_path}
                  </span>
                </button>
              ))}
            </div>
          </Card>
        </div>

        {/* Right Panel: Code Inspection View */}
        <Card title={selectedSymbol ? selectedSymbol.symbol_name : 'Code Inspection View'}>
          {selectedSymbol ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div
                style={{
                  display: 'flex',
                  gap: '1rem',
                  padding: '0.6rem 0.85rem',
                  borderRadius: 'var(--radius-md)',
                  backgroundColor: 'rgba(0, 0, 0, 0.3)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.825rem',
                  color: 'var(--text-secondary)',
                  flexWrap: 'wrap',
                }}
              >
                <span><strong>File:</strong> <code>{selectedSymbol.file_path}</code></span>
                <span><strong>Type:</strong> {selectedSymbol.symbol_type || 'Unknown'}</span>
                {selectedSymbol.start_line && selectedSymbol.end_line && (
                  <span><strong>Lines:</strong> {selectedSymbol.start_line} - {selectedSymbol.end_line}</span>
                )}
                {selectedSymbol.parent_symbol && (
                  <span><strong>Parent:</strong> <code>{selectedSymbol.parent_symbol}</code></span>
                )}
              </div>

              {selectedSymbol.code ? (
                <CodeBlock code={selectedSymbol.code} language="python" maxHeight="500px" />
              ) : (
                <EmptyState
                  title="No Inlined Code Payload"
                  description="Symbol location extracted from AST. Inlined syntax code available via vector chunk index."
                />
              )}
            </div>
          ) : (
            <EmptyState
              title="No Symbol Selected"
              description="Use AST Symbol Search on the left to locate class, function, or method definitions."
            />
          )}
        </Card>
      </div>
    </div>
  );
};
