import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Filter,
  Layers,
  RefreshCw,
  Search,
  Zap,
} from 'lucide-react';
import { graphApi } from '../api/graph';
import { projectsApi } from '../api/projects';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { Input } from '../components/common/Input';
import { Spinner } from '../components/common/Spinner';
import { Tabs } from '../components/common/Tabs';
import { useToast } from '../context/ToastContext';
import {
  GraphCalleesResponse,
  GraphCallersResponse,
  GraphDependenciesResponse,
  GraphDependentsResponse,
  GraphImpactResponse,
  GraphInfoResponse,
} from '../types/graph';
import { Project } from '../types/projects';

export const DependencyGraphPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [graphInfo, setGraphInfo] = useState<GraphInfoResponse | null>(null);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [activeTab, setActiveTab] = useState('callers');
  const [depth, setDepth] = useState(2);

  // Query Results
  const [callersData, setCallersData] = useState<GraphCallersResponse | null>(null);
  const [calleesData, setCalleesData] = useState<GraphCalleesResponse | null>(null);
  const [dependenciesData, setDependenciesData] = useState<GraphDependenciesResponse | null>(null);
  const [dependentsData, setDependentsData] = useState<GraphDependentsResponse | null>(null);
  const [impactData, setImpactData] = useState<GraphImpactResponse | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isQuerying, setIsQuerying] = useState(false);
  const [isBuilding, setIsBuilding] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    if (!projectId) return;
    setIsLoading(true);
    projectsApi
      .get(projectId)
      .then((proj) => {
        setProject(proj);
        return graphApi.getInfo(proj.path);
      })
      .then((info) => setGraphInfo(info))
      .catch((err) => {
        showToast(err.message || 'Failed to fetch graph info', 'error');
      })
      .finally(() => setIsLoading(false));
  }, [projectId]);

  const handleBuildGraph = async () => {
    if (!project) return;
    try {
      setIsBuilding(true);
      const res = await projectsApi.buildGraph(project.project_id);
      setGraphInfo({
        total_nodes: res.total_nodes,
        total_edges: res.total_edges,
        files: res.files,
        classes: res.classes,
        functions: res.functions,
        methods: 0,
        calls: 0,
      });
      showToast('Graph built successfully', 'success');
    } catch (err: any) {
      showToast(err.message || 'Failed to build graph', 'error');
    } finally {
      setIsBuilding(false);
    }
  };

  const runQueryForTab = async (tab: string, sym: string, curDepth: number) => {
    if (!sym.trim() || !project) return;
    try {
      setIsQuerying(true);
      const s = sym.trim();
      const pPath = project.path;

      if (tab === 'callers') {
        const res = await graphApi.getCallers(s, pPath);
        setCallersData(res);
      } else if (tab === 'callees') {
        const res = await graphApi.getCallees(s, pPath);
        setCalleesData(res);
      } else if (tab === 'dependencies') {
        const res = await graphApi.getDependencies(s, curDepth, pPath);
        setDependenciesData(res);
      } else if (tab === 'dependents') {
        const res = await graphApi.getDependents(s, curDepth, pPath);
        setDependentsData(res);
      } else if (tab === 'impact') {
        const res = await graphApi.getImpact(s, curDepth, pPath);
        setImpactData(res);
      }
    } catch (err: any) {
      showToast(err.message || 'Symbol analysis failed', 'error');
    } finally {
      setIsQuerying(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    runQueryForTab(activeTab, symbolQuery, depth);
  };

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    if (symbolQuery.trim()) {
      runQueryForTab(tab, symbolQuery, depth);
    }
  };

  const handleDepthChange = (newDepth: number) => {
    setDepth(newDepth);
    if (symbolQuery.trim() && (activeTab === 'dependencies' || activeTab === 'dependents' || activeTab === 'impact')) {
      runQueryForTab(activeTab, symbolQuery, newDepth);
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Dependency & Relationship Graph</h2>
          <p className="page-subtitle">
            Static code analysis, caller/callee trees, and recursive blast-radius impact analysis.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={handleBuildGraph}
          isLoading={isBuilding}
          leftIcon={<RefreshCw size={14} />}
        >
          Rebuild Graph
        </Button>
      </div>

      {/* Metrics Header */}
      <div className="grid-cards" style={{ marginBottom: '1.5rem' }}>
        <Card title="Total Nodes">
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {graphInfo?.total_nodes ?? (isLoading ? <Spinner size="sm" /> : 0)}
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Files: {graphInfo?.files ?? 0} | Classes: {graphInfo?.classes ?? 0} | Functions: {graphInfo?.functions ?? 0}
          </span>
        </Card>

        <Card title="Total Relationships">
          <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent-blue)' }}>
            {graphInfo?.total_edges ?? (isLoading ? <Spinner size="sm" /> : 0)}
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Static CALLS, IMPORTS, and CONTAINS edges
          </span>
        </Card>
      </div>

      {/* Search and Analysis Panel */}
      <Card padding="md">
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center', marginBottom: '1rem' }}>
          <div style={{ flex: 1, minWidth: '240px' }}>
            <Input
              placeholder="Enter symbol name (e.g. GraphBuilder.build, hash_password)..."
              value={symbolQuery}
              onChange={(e) => setSymbolQuery(e.target.value)}
              leftIcon={<Search size={16} />}
              required
            />
          </div>

          {(activeTab === 'dependencies' || activeTab === 'dependents' || activeTab === 'impact') && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <span style={{ fontSize: '0.825rem', color: 'var(--text-secondary)' }}>Depth:</span>
              <select
                value={depth}
                onChange={(e) => handleDepthChange(Number(e.target.value))}
                style={{
                  backgroundColor: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  padding: '0.45rem 0.6rem',
                  color: 'var(--text-primary)',
                  fontSize: '0.85rem',
                }}
              >
                <option value={1}>1 level</option>
                <option value={2}>2 levels</option>
                <option value={3}>3 levels</option>
                <option value={4}>4 levels</option>
              </select>
            </div>
          )}

          <Button variant="primary" type="submit" isLoading={isQuerying} leftIcon={<Zap size={15} />}>
            Inspect Symbol
          </Button>
        </form>

        <Tabs
          tabs={[
            { id: 'callers', label: 'Callers', icon: <ArrowDownRight size={15} /> },
            { id: 'callees', label: 'Callees', icon: <ArrowUpRight size={15} /> },
            { id: 'dependencies', label: 'Dependencies', icon: <Layers size={15} /> },
            { id: 'dependents', label: 'Dependents', icon: <Filter size={15} /> },
            { id: 'impact', label: 'Blast Radius Impact', icon: <Activity size={15} /> },
          ]}
          activeTab={activeTab}
          onChange={handleTabChange}
        />

        {/* Tab Result Views */}
        <div style={{ marginTop: '1.25rem' }}>
          {isQuerying ? (
            <Spinner label="Analyzing static graph..." />
          ) : activeTab === 'callers' ? (
            callersData ? (
              <div>
                <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600 }}>Callers of <code>{callersData.symbol}</code>:</span>
                  <Badge variant="primary">{callersData.total_callers} callers</Badge>
                </div>
                {callersData.callers.length === 0 ? (
                  <EmptyState title="No Inbound Callers" description="This symbol has no static callers within the project." />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    {callersData.callers.map((c, idx) => {
                      const callerName = c.name || c.caller_name || c.qualified_name || 'Unknown';
                      const callerLine = c.call_line ?? c.caller_line ?? c.start_line;
                      const callerFile = c.file_path || c.caller_file;
                      return (
                        <div key={idx} style={{ padding: '0.6rem 0.8rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <code style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{callerName}</code>
                            {callerLine !== undefined && (
                              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>line {callerLine}</span>
                            )}
                          </div>
                          {callerFile && <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{callerFile}</span>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <EmptyState title="Enter a symbol to find callers" description="Discovers all functions and methods calling the target." />
            )
          ) : activeTab === 'callees' ? (
            calleesData ? (
              <div>
                <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600 }}>Callees invoked by <code>{calleesData.symbol}</code>:</span>
                  <Badge variant="primary">{calleesData.total_callees} callees</Badge>
                </div>
                {calleesData.callees.length === 0 ? (
                  <EmptyState title="No Outbound Calls" description="This symbol does not invoke other static project symbols." />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    {calleesData.callees.map((c, idx) => {
                      const calleeName = c.name || c.callee_name || c.qualified_name || 'Unknown';
                      const calleeFile = c.file_path || c.callee_file;
                      return (
                        <div key={idx} style={{ padding: '0.6rem 0.8rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <code style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{calleeName}</code>
                          {calleeFile && <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{calleeFile}</span>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <EmptyState title="Enter a symbol to inspect callees" description="Discovers what functions the symbol invokes." />
            )
          ) : activeTab === 'dependencies' ? (
            dependenciesData ? (
              <div>
                <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600 }}>Dependencies for <code>{dependenciesData.symbol}</code>:</span>
                  <Badge variant="primary">{dependenciesData.total_dependencies} dependencies</Badge>
                </div>
                {dependenciesData.dependencies.length === 0 ? (
                  <EmptyState title="No Dependencies" description="No outbound dependencies found at this depth." />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    {dependenciesData.dependencies.map((d, idx) => {
                      const depName = d.name || d.target || d.qualified_name || 'Unknown';
                      return (
                        <div key={idx} style={{ padding: '0.6rem 0.8rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <code>{depName}</code>
                            {d.call_path && <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>{d.call_path}</span>}
                          </div>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>depth {d.depth}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <EmptyState title="Inspect Dependencies" description="Discovers downstream symbols and modules needed by this symbol." />
            )
          ) : activeTab === 'dependents' ? (
            dependentsData ? (
              <div>
                <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600 }}>Dependents for <code>{dependentsData.symbol}</code>:</span>
                  <Badge variant="primary">{dependentsData.total_dependents} dependents</Badge>
                </div>
                {dependentsData.dependents.length === 0 ? (
                  <EmptyState title="No Dependents" description="No upstream dependents found at this depth." />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                    {dependentsData.dependents.map((d, idx) => {
                      const depName = d.name || d.source || 'Unknown';
                      return (
                        <div key={idx} style={{ padding: '0.6rem 0.8rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div>
                            <code>{depName}</code>
                            {d.dependent_path && <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '0.5rem' }}>{d.dependent_path}</span>}
                          </div>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>depth {d.depth}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <EmptyState title="Inspect Dependents" description="Discovers upstream callers and symbols that depend on this symbol." />
            )
          ) : activeTab === 'impact' ? (
            impactData ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600 }}>Blast Radius for <code>{impactData.symbol}</code>:</span>
                  <Badge variant="danger">{impactData.total_impacted} Total Impacted Symbols</Badge>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <Card title={`Direct Callers (${impactData.direct_callers.length})`}>
                    {impactData.direct_callers.length === 0 ? (
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>None</span>
                    ) : (
                      impactData.direct_callers.map((s, idx) => {
                        const name = typeof s === 'string' ? s : s.name || s.id || 'Unknown';
                        const file = typeof s !== 'string' ? s.file_path : undefined;
                        return (
                          <div key={idx} style={{ fontSize: '0.825rem', marginBottom: '0.35rem', display: 'flex', justifyContent: 'space-between' }}>
                            <code>{name}</code>
                            {file && <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{file}</span>}
                          </div>
                        );
                      })
                    )}
                  </Card>
                  <Card title={`Indirect Affected (${impactData.indirect_callers.length})`}>
                    {impactData.indirect_callers.length === 0 ? (
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>None</span>
                    ) : (
                      impactData.indirect_callers.map((s, idx) => {
                        const name = typeof s === 'string' ? s : s.name || s.id || 'Unknown';
                        const file = typeof s !== 'string' ? s.file_path : undefined;
                        return (
                          <div key={idx} style={{ fontSize: '0.825rem', marginBottom: '0.35rem', display: 'flex', justifyContent: 'space-between' }}>
                            <code>{name}</code>
                            {file && <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{file}</span>}
                          </div>
                        );
                      })
                    )}
                  </Card>
                </div>

                {impactData.impacted_files && impactData.impacted_files.length > 0 && (
                  <Card title={`Impacted Files (${impactData.impacted_files.length})`}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                      {impactData.impacted_files.map((file, idx) => (
                        <Badge key={idx} variant="primary"><code>{file}</code></Badge>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            ) : (
              <EmptyState title="Run Blast Radius Analysis" description="Computes direct and recursive upstream callers affected if this symbol is modified." />
            )
          ) : null}
        </div>
      </Card>
    </div>
  );
};
