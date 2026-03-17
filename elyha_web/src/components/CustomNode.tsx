import React, {useEffect, useState} from 'react';
import {Handle, NodeResizer, Position} from '@xyflow/react';
import {FileText, Sparkles, Settings2, Play, ChevronDown, ChevronUp, Save} from 'lucide-react';
import {cn} from '../utils';
import type {TranslationVars} from '../i18n';

interface CustomNodeData {
  label: string;
  type: 'document' | 'generation';
  nodeType: string;
  nodeTypeLabel?: string;
  content: string;
  status: string;
  onSaveContent?: (content: string) => Promise<void>;
  onRun?: () => Promise<void>;
}

interface CustomNodeProps {
  data: CustomNodeData;
  selected: boolean;
  t?: (key: string, vars?: TranslationVars) => string;
}

export function CustomNode({data, selected, t}: CustomNodeProps) {
  const safeData = data || ({} as CustomNodeData);
  const label = safeData.label || (t ? t('web.node.untitled') : 'Untitled');
  const nodeType = safeData.nodeType || 'chapter';
  const nodeTypeLabel = safeData.nodeTypeLabel || nodeType;
  const kind = safeData.type === 'generation' ? 'generation' : 'document';
  const status = safeData.status || 'draft';
  const content = safeData.content || '';

  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftContent, setDraftContent] = useState(content);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!editing) {
      setDraftContent(content);
    }
  }, [content, editing]);

  const saveContent = async () => {
    if (!safeData.onSaveContent) {
      setEditing(false);
      return;
    }
    setBusy(true);
    try {
      await safeData.onSaveContent(draftContent);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };

  const runNode = async () => {
    if (!safeData.onRun || busy) {
      return;
    }
    setBusy(true);
    try {
      await safeData.onRun();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className={cn(
        'bg-white border rounded-xl shadow-sm w-full h-full min-h-[190px] overflow-hidden transition-all duration-200 flex flex-col',
        selected ? 'ring-2 ring-pink-500 border-pink-500/50 shadow-md' : 'border-slate-200 hover:border-slate-300',
      )}
    >
      <NodeResizer color="#ec4899" isVisible={selected} minWidth={250} minHeight={190} />
      <Handle type="target" position={Position.Left} className="w-3 h-3 bg-white border-2 border-slate-300" />

      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-slate-50/50">
        <div className="flex items-center gap-2 min-w-0">
          <div className={cn('p-1.5 rounded-md', kind === 'generation' ? 'bg-pink-50 text-pink-500' : 'bg-emerald-50 text-emerald-500')}>
            {kind === 'generation' ? <Sparkles size={14} /> : <FileText size={14} />}
          </div>
          <div className="min-w-0">
            <span className="text-sm font-bold text-slate-700 truncate block" title={label}>
              {label}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-slate-400">{nodeTypeLabel}</span>
          </div>
        </div>
        <button
          className="text-slate-400 hover:text-slate-600 transition-colors"
          onClick={() => setEditing((value) => !value)}
          title={t ? t('web.node.edit_content') : 'Edit'}
        >
          <Settings2 size={14} />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {editing ? (
          <div className="space-y-2">
            <textarea
              value={draftContent}
              onChange={(event) => setDraftContent(event.target.value)}
              className="w-full min-h-[120px] rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-pink-300"
              placeholder={t ? t('web.node.content_placeholder') : 'Input content'}
            />
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => {
                  setDraftContent(content);
                  setEditing(false);
                }}
                className="px-2.5 py-1.5 rounded-md text-xs font-semibold text-slate-500 hover:bg-slate-100"
              >
                {t ? t('web.modal.cancel') : 'Cancel'}
              </button>
              <button
                onClick={() => void saveContent()}
                disabled={busy}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-semibold text-white bg-pink-500 hover:bg-pink-600 disabled:opacity-50"
              >
                <Save size={12} />
                {t ? t('web.runtime.save') : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <div className="relative">
            <p className={cn('text-xs text-slate-600 leading-relaxed whitespace-pre-wrap transition-all duration-200', !expanded && 'line-clamp-4')}>
              {content || (t ? t('web.node.empty_content') : 'No content')}
            </p>
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-[10px] font-bold text-pink-500 hover:text-pink-600 mt-2 transition-colors"
            >
              {expanded ? (
                <>
                  <ChevronUp size={12} /> {t ? t('web.node.collapse_content') : 'Collapse'}
                </>
              ) : (
                <>
                  <ChevronDown size={12} /> {t ? t('web.node.expand_content') : 'Expand'}
                </>
              )}
            </button>
          </div>
        )}

        <div className="flex items-center justify-between pt-3 border-t border-slate-100">
          <div className="flex items-center gap-1.5">
            <div
              className={cn(
                'w-2 h-2 rounded-full',
                status === 'approved'
                  ? 'bg-emerald-500'
                  : status === 'generated'
                    ? 'bg-amber-500 animate-pulse'
                    : status === 'reviewed'
                      ? 'bg-sky-500'
                      : 'bg-slate-300',
              )}
            />
            <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">{status}</span>
          </div>

          <button
            onClick={() => void runNode()}
            disabled={busy}
            className="flex items-center gap-1 text-xs font-bold text-pink-600 hover:text-pink-700 transition-colors bg-pink-50 hover:bg-pink-100 px-2.5 py-1.5 rounded-md disabled:opacity-50"
          >
            <Play size={12} />
            <span>{busy ? (t ? t('web.node.running') : 'Running') : (t ? t('web.node.run') : 'Run')}</span>
          </button>
        </div>
      </div>

      <Handle type="source" position={Position.Right} className="w-3 h-3 bg-white border-2 border-slate-300" />
    </div>
  );
}
