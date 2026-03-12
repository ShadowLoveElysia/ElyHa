import React, {useMemo} from 'react';
import {Network, Database, RefreshCw, BarChart3, GitBranch, Link2, Users, Globe} from 'lucide-react';
import type {ProjectInsights} from '../types';
import type {TranslationVars} from '../i18n';

interface KnowledgeGraphProps {
  projectId?: string;
  insights: ProjectInsights | null;
  loading: boolean;
  onRefresh: () => Promise<void>;
  t: (key: string, vars?: TranslationVars) => string;
}

export function KnowledgeGraph({projectId = '', insights, loading, onRefresh, t}: KnowledgeGraphProps) {
  const metrics = useMemo(() => {
    if (!insights) {
      return {
        nodeCount: 0,
        edgeCount: 0,
        storylineCount: 0,
        relationNodeCount: 0,
        relationEdgeCount: 0,
      };
    }
    const nodeCount = insights.storylines.reduce((sum, item) => sum + item.node_count, 0);
    const edgeCount = insights.storylines.reduce((sum, item) => sum + item.edge_count, 0);
    return {
      nodeCount,
      edgeCount,
      storylineCount: insights.storylines.length,
      relationNodeCount: insights.relation_graph.nodes.length,
      relationEdgeCount: insights.relation_graph.edges.length,
    };
  }, [insights]);

  if (!projectId) {
    return (
      <div className="w-full h-full bg-slate-50 flex items-center justify-center text-slate-500">
        {t('web.insight.select_project_hint')}
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-slate-50 flex flex-col absolute inset-0 z-0">
      <div className="h-14 border-b border-slate-200 bg-white flex items-center justify-between px-6 shrink-0 relative z-10 shadow-sm">
        <div className="flex items-center gap-2">
          <Network className="text-pink-500" size={20} />
          <span className="font-bold text-slate-800">{t('web.insight.project_graph_title')}</span>
        </div>
        <button
          onClick={() => void onRefresh()}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 text-sm font-medium hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          {t('web.insight.refresh')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {!insights ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-slate-500">
              <Database className="mx-auto mb-3 text-slate-400" size={32} />
              {loading ? t('web.insight.loading') : t('web.insight.empty')}
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-3">
              <MetricCard icon={<BarChart3 size={18} />} label={t('web.insight.metric.node_count')} value={String(metrics.nodeCount)} />
              <MetricCard icon={<Link2 size={18} />} label={t('web.insight.metric.edge_count')} value={String(metrics.edgeCount)} />
              <MetricCard icon={<GitBranch size={18} />} label={t('web.insight.metric.storyline_count')} value={String(metrics.storylineCount)} />
              <MetricCard icon={<Users size={18} />} label={t('web.insight.metric.relation_node_count')} value={String(metrics.relationNodeCount)} />
              <MetricCard icon={<Network size={18} />} label={t('web.insight.metric.relation_edge_count')} value={String(metrics.relationEdgeCount)} />
            </div>

            <section className="rounded-2xl bg-white border border-slate-200 shadow-sm p-4">
              <h3 className="font-semibold text-slate-800 mb-3">{t('web.insight.storyline_distribution')}</h3>
              <div className="space-y-2">
                {insights.storylines.length === 0 ? (
                  <p className="text-sm text-slate-500">{t('web.insight.storyline_empty')}</p>
                ) : (
                  insights.storylines.map((item) => (
                    <div key={item.storyline_id} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm">
                      <span className="font-medium text-slate-700">{item.storyline_id || t('web.insight.storyline_unassigned')}</span>
                      <span className="text-slate-500">{t('web.insight.storyline_counts', {nodes: item.node_count, edges: item.edge_count})}</span>
                    </div>
                  ))
                )}
              </div>
            </section>

            <section className="rounded-2xl bg-white border border-slate-200 shadow-sm p-4">
              <h3 className="font-semibold text-slate-800 mb-3">{t('web.insight.word_frequency_top')}</h3>
              <div className="flex flex-wrap gap-2">
                {insights.word_frequency.length === 0 ? (
                  <p className="text-sm text-slate-500">{t('web.insight.word_frequency_empty')}</p>
                ) : (
                  insights.word_frequency.slice(0, 40).map((item) => (
                    <span
                      key={item.term}
                      className="inline-flex items-center gap-1 rounded-full border border-pink-200 bg-pink-50 text-pink-700 px-3 py-1 text-xs font-semibold"
                    >
                      {item.term}
                      <span className="text-pink-400">{item.count}</span>
                    </span>
                  ))
                )}
              </div>
            </section>

            <section className="rounded-2xl bg-white border border-slate-200 shadow-sm p-4">
              <h3 className="font-semibold text-slate-800 mb-3">{t('web.insight.entity_stats')}</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <EntityPanel title={t('web.insight.characters')} icon={<Users size={14} />} rows={insights.characters} t={t} />
                <EntityPanel title={t('web.insight.worldviews')} icon={<Globe size={14} />} rows={insights.worldviews} t={t} />
                <EntityPanel title={t('web.insight.items')} icon={<Database size={14} />} rows={insights.items} t={t} />
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function MetricCard({icon, label, value}: {icon: React.ReactNode; label: string; value: string}) {
  return (
    <div className="rounded-xl bg-white border border-slate-200 px-4 py-3 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-slate-500 text-sm">{label}</span>
        <span className="text-pink-500">{icon}</span>
      </div>
      <div className="mt-2 text-2xl font-bold text-slate-800">{value}</div>
    </div>
  );
}

function EntityPanel({
  title,
  icon,
  rows,
  t,
}: {
  title: string;
  icon: React.ReactNode;
  rows: Array<{id: string; label: string; count: number}>;
  t: (key: string, vars?: TranslationVars) => string;
}) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
      <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 mb-2">
        {icon}
        <span>{title}</span>
      </div>
      <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
        {rows.length === 0 ? (
          <div className="text-xs text-slate-500">{t('web.insight.entity_empty')}</div>
        ) : (
          rows.map((row) => (
            <div key={row.id} className="flex items-center justify-between text-xs rounded-md bg-white border border-slate-200 px-2.5 py-1.5">
              <span className="text-slate-700 truncate">{row.label}</span>
              <span className="text-slate-500 ml-2">{row.count}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
