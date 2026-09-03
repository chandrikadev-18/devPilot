import React, { useState, useEffect } from 'react';
import { tasksApi, EngineeringTask } from '../api/tasks';
import { useToast } from '../context/ToastContext';

export const TaskWorkspacePage: React.FC = () => {
  const [tasks, setTasks] = useState<EngineeringTask[]>([]);
  const [selectedTask, setSelectedTask] = useState<EngineeringTask | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [activeFilter, setActiveFilter] = useState<string>('ALL');

  // New task form state
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>('');
  const [newDesc, setNewDesc] = useState<string>('');
  const [newType, setNewType] = useState<string>('bug');
  const [newPriority, setNewPriority] = useState<string>('MEDIUM');

  const { showToast } = useToast();

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const res = await tasksApi.listTasks();
      if (res && res.tasks) {
        setTasks(res.tasks);
        if (!selectedTask && res.tasks.length > 0) {
          setSelectedTask(res.tasks[0]);
        } else if (selectedTask) {
          const updated = res.tasks.find((t: EngineeringTask) => t.task_id === selectedTask.task_id);
          if (updated) setSelectedTask(updated);
        }
      }
    } catch (err: any) {
      showToast(err.message || 'Failed to fetch tasks', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setActionLoading(true);
    try {
      const res = await tasksApi.createTask(newTitle, newDesc, newType, newPriority);
      showToast('Engineering task created', 'success');
      setShowCreateModal(false);
      setNewTitle('');
      setNewDesc('');
      await fetchTasks();
      if (res && res.task) setSelectedTask(res.task);
    } catch (err: any) {
      showToast(err.message || 'Failed to create task', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleAnalyze = async (taskId: string) => {
    setActionLoading(true);
    try {
      const res = await tasksApi.analyzeTask(taskId);
      showToast('Root cause analysis completed', 'success');
      if (res && res.task) setSelectedTask(res.task);
      fetchTasks();
    } catch (err: any) {
      showToast(err.message || 'Analysis failed', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handlePlan = async (taskId: string) => {
    setActionLoading(true);
    try {
      const res = await tasksApi.planTask(taskId);
      showToast('Implementation plan and patch proposal generated', 'success');
      if (res && res.task) setSelectedTask(res.task);
      fetchTasks();
    } catch (err: any) {
      showToast(err.message || 'Planning failed', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async (taskId: string) => {
    setActionLoading(true);
    try {
      const res = await tasksApi.approveTask(taskId, 'Approved via Task Workspace');
      showToast('Task approved successfully', 'success');
      if (res && res.task) setSelectedTask(res.task);
      fetchTasks();
    } catch (err: any) {
      showToast(err.message || 'Approval failed', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (taskId: string) => {
    setActionLoading(true);
    try {
      const res = await tasksApi.rejectTask(taskId, 'Rejected by reviewer');
      showToast('Task rejected', 'info');
      if (res && res.task) setSelectedTask(res.task);
      fetchTasks();
    } catch (err: any) {
      showToast(err.message || 'Rejection failed', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleExecute = async (taskId: string) => {
    setActionLoading(true);
    try {
      const res = await tasksApi.executeTask(taskId, true);
      showToast('Task execution and test verification complete', 'success');
      if (res && res.task) setSelectedTask(res.task);
      fetchTasks();
    } catch (err: any) {
      showToast(err.message || 'Execution failed', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRollback = async (taskId: string) => {
    setActionLoading(true);
    try {
      const res = await tasksApi.rollbackTask(taskId);
      showToast('Task rolled back to checkpoint', 'info');
      if (res && res.task) setSelectedTask(res.task);
      fetchTasks();
    } catch (err: any) {
      showToast(err.message || 'Rollback failed', 'error');
    } finally {
      setActionLoading(false);
    }
  };

  const filteredTasks = tasks.filter((t) => {
    if (activeFilter === 'ALL') return true;
    if (activeFilter === 'WAITING_APPROVAL') return t.status === 'WAITING_APPROVAL';
    if (activeFilter === 'COMPLETED') return t.status === 'COMPLETED';
    if (activeFilter === 'FAILED') return t.status === 'FAILED' || t.status === 'ROLLED_BACK';
    return true;
  });

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'WAITING_APPROVAL':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      case 'APPROVED':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'IMPLEMENTING':
      case 'TESTING':
      case 'ANALYZING':
        return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20';
      case 'FAILED':
      case 'ROLLED_BACK':
      case 'REJECTED':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/20';
      default:
        return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/50 border border-slate-800 p-5 rounded-2xl">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <span className="p-2 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-xl">⚡</span>
            Issue-to-PR Task Workspace
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Autonomous software engineering agent with root-cause analysis, safe patch proposals, and PR readiness.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-sm font-medium transition shadow-lg shadow-indigo-500/20 flex items-center gap-2"
          >
            <span>+</span> New Engineering Task
          </button>
          <button
            onClick={fetchTasks}
            disabled={loading}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-sm transition"
          >
            {loading ? 'Refreshing...' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {/* Main Grid: Left Task List & Right Task Details */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Tasks List */}
        <div className="lg:col-span-4 space-y-4">
          {/* Filters */}
          <div className="flex gap-1 bg-slate-900 border border-slate-800 p-1 rounded-xl text-xs">
            {['ALL', 'WAITING_APPROVAL', 'COMPLETED', 'FAILED'].map((f) => (
              <button
                key={f}
                onClick={() => setActiveFilter(f)}
                className={`flex-1 py-1.5 rounded-lg font-medium transition ${
                  activeFilter === f
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {f.replace('_', ' ')}
              </button>
            ))}
          </div>

          {/* List */}
          <div className="space-y-2 max-h-[750px] overflow-y-auto pr-1">
            {filteredTasks.length === 0 ? (
              <div className="text-center py-12 bg-slate-900/30 border border-slate-800/80 rounded-2xl text-slate-500 text-sm">
                No engineering tasks found.
              </div>
            ) : (
              filteredTasks.map((t) => (
                <div
                  key={t.task_id}
                  onClick={() => setSelectedTask(t)}
                  className={`p-4 rounded-xl border transition cursor-pointer ${
                    selectedTask?.task_id === t.task_id
                      ? 'bg-indigo-950/30 border-indigo-500/50 shadow-md shadow-indigo-500/5'
                      : 'bg-slate-900/40 border-slate-800 hover:border-slate-700 hover:bg-slate-800/40'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-sm font-semibold text-white line-clamp-1">{t.title}</h3>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-md border font-mono font-medium ${getStatusColor(
                        t.status
                      )}`}
                    >
                      {t.status}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                    {t.description || t.root_cause?.summary || 'No description provided.'}
                  </p>
                  <div className="flex items-center gap-2 mt-3 text-[11px] text-slate-500">
                    <span className="capitalize font-mono px-1.5 py-0.5 bg-slate-800 rounded">
                      {t.task_type}
                    </span>
                    <span>•</span>
                    <span className="font-mono text-slate-400">{t.priority}</span>
                    <span>•</span>
                    <span>{new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Column: Selected Task Workspace */}
        <div className="lg:col-span-8 space-y-6">
          {selectedTask ? (
            <div className="space-y-6">
              {/* Task Header Card */}
              <div className="bg-slate-900/60 border border-slate-800 p-6 rounded-2xl space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <span className="text-xs font-mono text-indigo-400">{selectedTask.task_id}</span>
                    <h2 className="text-xl font-bold text-white mt-1">{selectedTask.title}</h2>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-3 py-1 rounded-lg border font-mono font-medium ${getStatusColor(
                        selectedTask.status
                      )}`}
                    >
                      {selectedTask.status}
                    </span>
                    <span className="text-xs px-3 py-1 rounded-lg border border-slate-700 bg-slate-800 text-slate-300 font-mono">
                      Risk: {selectedTask.risk}
                    </span>
                  </div>
                </div>

                {selectedTask.description && (
                  <p className="text-sm text-slate-300 bg-slate-950/50 p-3 rounded-xl border border-slate-800/80">
                    {selectedTask.description}
                  </p>
                )}

                {/* State Machine Stepper */}
                <div className="flex items-center justify-between gap-1 text-[11px] font-mono text-slate-400 pt-2 border-t border-slate-800/80 overflow-x-auto pb-1">
                  {['CREATED', 'ANALYZED', 'PLANNED', 'WAITING_APPROVAL', 'APPROVED', 'IMPLEMENTING', 'COMPLETED'].map(
                    (step, idx) => {
                      const isCurrent = selectedTask.status === step;
                      return (
                        <div key={step} className="flex items-center gap-1.5 whitespace-nowrap">
                          <span
                            className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                              isCurrent
                                ? 'bg-indigo-600 text-white'
                                : 'bg-slate-800 text-slate-500 border border-slate-700'
                            }`}
                          >
                            {idx + 1}
                          </span>
                          <span className={isCurrent ? 'text-indigo-300 font-bold' : ''}>
                            {step.replace('_', ' ')}
                          </span>
                          {idx < 6 && <span className="text-slate-600">→</span>}
                        </div>
                      );
                    }
                  )}
                </div>

                {/* Workflow Actions */}
                <div className="flex flex-wrap items-center gap-2 pt-2">
                  {selectedTask.status === 'CREATED' && (
                    <button
                      onClick={() => handleAnalyze(selectedTask.task_id)}
                      disabled={actionLoading}
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition"
                    >
                      {actionLoading ? 'Analyzing...' : '🔍 Analyze Root Cause'}
                    </button>
                  )}

                  {selectedTask.status === 'ANALYZED' && (
                    <button
                      onClick={() => handlePlan(selectedTask.task_id)}
                      disabled={actionLoading}
                      className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition"
                    >
                      {actionLoading ? 'Planning...' : '📝 Generate Implementation Plan'}
                    </button>
                  )}

                  {selectedTask.status === 'WAITING_APPROVAL' && (
                    <>
                      <button
                        onClick={() => handleApprove(selectedTask.task_id)}
                        disabled={actionLoading}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold transition"
                      >
                        ✓ Approve Task
                      </button>
                      <button
                        onClick={() => handleReject(selectedTask.task_id)}
                        disabled={actionLoading}
                        className="px-4 py-2 bg-rose-600/80 hover:bg-rose-500 text-white rounded-xl text-xs font-semibold transition"
                      >
                        ✗ Reject
                      </button>
                    </>
                  )}

                  {selectedTask.status === 'APPROVED' && (
                    <button
                      onClick={() => handleExecute(selectedTask.task_id)}
                      disabled={actionLoading}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold transition"
                    >
                      {actionLoading ? 'Executing...' : '▶ Safe Fix & Verify (Fix Loop)'}
                    </button>
                  )}

                  {['COMPLETED', 'FAILED'].includes(selectedTask.status) && selectedTask.checkpoint_id && (
                    <button
                      onClick={() => handleRollback(selectedTask.task_id)}
                      disabled={actionLoading}
                      className="px-4 py-2 bg-amber-600/80 hover:bg-amber-500 text-white rounded-xl text-xs font-semibold transition"
                    >
                      ↺ Rollback Changes
                    </button>
                  )}
                </div>
              </div>

              {/* Root Cause & Analysis Card */}
              {selectedTask.root_cause && (
                <div className="bg-slate-900/50 border border-slate-800 p-5 rounded-2xl space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <span>🎯</span> Root Cause Analysis Evidence
                    </h3>
                    <span className="text-xs px-2 py-0.5 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded font-mono">
                      Confidence: {selectedTask.root_cause.confidence}
                    </span>
                  </div>

                  <p className="text-xs text-slate-300 font-medium">
                    {selectedTask.root_cause.summary}
                  </p>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs pt-2">
                    <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                      <span className="text-slate-400">Target File:</span>
                      <p className="text-slate-200 font-mono mt-0.5">
                        {selectedTask.root_cause.culprit_file || '(Not resolved)'}
                      </p>
                    </div>
                    <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                      <span className="text-slate-400">Target Symbol:</span>
                      <p className="text-slate-200 font-mono mt-0.5">
                        {selectedTask.root_cause.culprit_symbol || '(Module level)'}
                      </p>
                    </div>
                  </div>

                  {selectedTask.root_cause.evidence_points?.length > 0 && (
                    <div className="space-y-1 pt-1">
                      <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                        Evidence Points:
                      </span>
                      <ul className="text-xs text-slate-300 space-y-1">
                        {selectedTask.root_cause.evidence_points.map((pt, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="text-indigo-400">•</span> {pt}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Implementation Plan */}
              {selectedTask.implementation_plan?.length > 0 && (
                <div className="bg-slate-900/50 border border-slate-800 p-5 rounded-2xl space-y-3">
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <span>📋</span> Structured Implementation Plan
                  </h3>
                  <div className="space-y-2">
                    {selectedTask.implementation_plan.map((step) => (
                      <div
                        key={step.step_number}
                        className="p-3 bg-slate-950/50 border border-slate-800 rounded-xl text-xs space-y-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-indigo-400">
                            Step {step.step_number}: {step.operation}
                          </span>
                          <span className="font-mono text-slate-400">{step.file}</span>
                        </div>
                        <p className="text-slate-300">{step.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Proposed Unified Diff Viewer */}
              {selectedTask.patch && (
                <div className="bg-slate-900/50 border border-slate-800 p-5 rounded-2xl space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2">
                      <span>📄</span> Proposed Unified Diff
                    </h3>
                    <span className="text-xs font-mono text-slate-400">Review Before Execution</span>
                  </div>
                  <pre className="bg-slate-950 p-4 rounded-xl border border-slate-800/90 text-xs font-mono text-slate-300 overflow-x-auto max-h-72">
                    {selectedTask.patch}
                  </pre>
                </div>
              )}

              {/* PR-Ready Package Report */}
              {selectedTask.pr_summary && (
                <div className="bg-slate-900/50 border border-slate-800 p-5 rounded-2xl space-y-3">
                  <h3 className="text-sm font-bold text-emerald-400 flex items-center gap-2">
                    <span>📦</span> PR-Ready Summary Package
                  </h3>
                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800/90 text-xs font-mono text-slate-300 whitespace-pre-wrap max-h-80 overflow-y-auto">
                    {selectedTask.pr_summary}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-24 bg-slate-900/30 border border-slate-800/80 rounded-2xl text-slate-400 text-sm">
              Select a task from the list or create a new one to begin.
            </div>
          )}
        </div>
      </div>

      {/* Create Task Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl max-w-lg w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-white">Create Engineering Task</h2>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Issue / Task Title *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Fix login returning 500 when password is invalid"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Description / Context (Optional)
                </label>
                <textarea
                  rows={3}
                  placeholder="Provide additional traceback or requirements..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Type</label>
                  <select
                    value={newType}
                    onChange={(e) => setNewType(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="bug">Bug</option>
                    <option value="feature">Feature</option>
                    <option value="refactor">Refactor</option>
                    <option value="performance">Performance</option>
                    <option value="security">Security</option>
                    <option value="test">Test</option>
                    <option value="documentation">Documentation</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">Priority</label>
                  <select
                    value={newPriority}
                    onChange={(e) => setNewPriority(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="LOW">LOW</option>
                    <option value="MEDIUM">MEDIUM</option>
                    <option value="HIGH">HIGH</option>
                    <option value="CRITICAL">CRITICAL</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition"
                >
                  {actionLoading ? 'Creating...' : 'Create Task'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
