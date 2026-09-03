import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { FileCode, Filter, Layers, Search, Sparkles } from 'lucide-react';
import { projectsApi } from '../api/projects';
import { searchApi } from '../api/search';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { CodeBlock } from '../components/common/CodeBlock';
import { EmptyState } from '../components/common/EmptyState';
import { Input } from '../components/common/Input';
import { Spinner } from '../components/common/Spinner';
import { Tabs } from '../components/common/Tabs';
import { useToast } from '../context/ToastContext';
import { Project } from '../types/projects';
import { SemanticSearchResultItem, SymbolMatchItem } from '../types/search';

export const CodeExplorerPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [extensions, setExtensions] = useState<Record<string, number>>({});
  const [totalFiles, setTotalFiles] = useState<number>(0);
  const [searchMode, setSearchMode] = useState<'symbol' | 'semantic'>('symbol');

  // AST Symbol Search State
  const [symbolQuery, setSymbolQuery] = useState('');
  const [symbols, setSymbols] = useState<SymbolMatchItem[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolMatchItem | null>(null);

  // Semantic Search State
  const [semanticQuery, setSemanticQuery] = useState('');
  const [semanticResults, setSemanticResults] = useState<SemanticSearchResultItem[]>([]);
  const [selectedSemantic, setSelectedSemantic] = useState<SemanticSearchResultItem | null>(null);

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

  const handleSymbolSearch = async (e: React.FormEvent) => {
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

  const handleSemanticSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!semanticQuery.trim() || !project) return;
    try {
      setIsSearching(true);
      const res = await searchApi.semanticSearch(semanticQuery.trim(), 8, project.path);
      setSemanticResults(res.results);
      if (res.results.length > 0) {
        setSelectedSemantic(res.results[0]);
      } else {
        setSelectedSemantic(null);
        showToast(`No semantic code matches found for "${semanticQuery}"`, 'info');
      }
    } catch (err: any) {
      showToast(err.message || 'Semantic search failed', 'error');
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
            Explore indexed AST symbols, semantic code embeddings, and file structures for {project?.name}.
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: '1.5rem', minHeight: '650px' }}>
        {/* Left Sidebar: Breakdown & Search Modes */}
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
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                  {Object.entries(extensions).map(([ext, count]) => (
                    <div
                      key={ext}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.4rem',
                        padding: '0.2rem 0.5rem',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'rgba(255, 255, 255, 0.03)',
                        border: '1px solid var(--border-subtle)',
                        fontSize: '0.775rem',
                      }}
                    >
                      <code>{ext || '(no ext)'}</code>
                      <span style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>
                        {count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>

          <Card title="Code Search Engine">
            <div style={{ marginBottom: '0.75rem' }}>
              <Tabs
                tabs={[
                  { id: 'symbol', label: 'AST Symbol', icon: <Search size={14} /> },
                  { id: 'semantic', label: 'Semantic AI', icon: <Sparkles size={14} /> },
                ]}
                activeTab={searchMode}
                onChange={(tab) => setSearchMode(tab as 'symbol' | 'semantic')}
              />
            </div>

            {searchMode === 'symbol' ? (
              <div>
                <form onSubmit={handleSymbolSearch} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <Input
                    placeholder="e.g. GraphBuilder, scan_project..."
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
                    Find AST Symbol
                  </Button>
                </form>

                <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.35rem', maxHeight: '280px', overflowY: 'auto' }}>
                  {symbols.map((sym, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setSelectedSymbol(sym);
                        setSelectedSemantic(null);
                      }}
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
              </div>
            ) : (
              <div>
                <form onSubmit={handleSemanticSearch} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                  <Input
                    placeholder="e.g. JWT token verification, database connection..."
                    value={semanticQuery}
                    onChange={(e) => setSemanticQuery(e.target.value)}
                    leftIcon={<Sparkles size={14} />}
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    type="submit"
                    isLoading={isSearching}
                    leftIcon={<Sparkles size={13} />}
                  >
                    Semantic Code Search
                  </Button>
                </form>

                <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.35rem', maxHeight: '280px', overflowY: 'auto' }}>
                  {semanticResults.map((item, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setSelectedSemantic(item);
                        setSelectedSymbol(null);
                      }}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'flex-start',
                        padding: '0.45rem 0.6rem',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: selectedSemantic === item ? 'rgba(6, 182, 212, 0.15)' : 'transparent',
                        border: `1px solid ${selectedSemantic === item ? 'var(--accent-cyan)' : 'var(--border-subtle)'}`,
                        textAlign: 'left',
                        width: '100%',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600, fontSize: '0.825rem', color: 'var(--text-primary)' }}>
                          {item.symbol || 'Code Snippet'}
                        </span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
                          {(item.score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        {item.file} (L{item.start_line}-{item.end_line})
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* Right Panel: Code Inspection View */}
        <Card
          title={
            selectedSymbol
              ? selectedSymbol.symbol_name
              : selectedSemantic
              ? selectedSemantic.symbol || selectedSemantic.file
              : 'Code Inspection View'
          }
        >
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
                  title="Symbol Location Extracted"
                  description={`Symbol defined at ${selectedSymbol.file_path}:${selectedSymbol.start_line || 1}`}
                />
              )}
            </div>
          ) : selectedSemantic ? (
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
                <span><strong>File:</strong> <code>{selectedSemantic.file}</code></span>
                {selectedSemantic.symbol && (
                  <span><strong>Symbol:</strong> <code>{selectedSemantic.symbol}</code></span>
                )}
                <span><strong>Lines:</strong> {selectedSemantic.start_line} - {selectedSemantic.end_line}</span>
                <span><strong>Match Score:</strong> {(selectedSemantic.score * 100).toFixed(1)}%</span>
              </div>

              {selectedSemantic.reason ? (
                <div style={{ padding: '0.85rem', backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem' }}>
                  <strong>Relevance Reason:</strong> {selectedSemantic.reason}
                </div>
              ) : (
                <EmptyState
                  title="Semantic Result Selected"
                  description={`Found relevant match for symbol ${selectedSemantic.symbol || 'code'} in ${selectedSemantic.file} (Lines ${selectedSemantic.start_line}-${selectedSemantic.end_line})`}
                />
              )}
            </div>
          ) : (
            <EmptyState
              title="No Symbol or Code Snippet Selected"
              description="Use AST Symbol Search or Semantic AI Search on the left to locate codebase definitions and implementations."
            />
          )}
        </Card>
      </div>
    </div>
  );
};
