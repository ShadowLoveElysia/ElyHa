import React from 'react';
import {AlertTriangle, MessageSquare, RefreshCw, Save, Undo2, Play, Link2, Languages} from 'lucide-react';
import {cn} from '../utils';
import type {TranslationVars} from '../i18n';

interface HeaderProps {
  isChatOpen: boolean;
  setIsChatOpen: (open: boolean) => void;
  projectTitle: string;
  selectedNodeTitle: string;
  busy: boolean;
  onRollback: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onSnapshot: () => Promise<void>;
  onValidate: () => Promise<void>;
  onGenerateSelected: () => Promise<void>;
  linkMode: boolean;
  linkSourceNodeTitle: string;
  onToggleLinkMode: () => void;
  localeLabel: string;
  onOpenLanguageSwitcher: () => void;
  t: (key: string, vars?: TranslationVars) => string;
}

export function Header({
  isChatOpen,
  setIsChatOpen,
  projectTitle,
  selectedNodeTitle,
  busy,
  onRollback,
  onRefresh,
  onSnapshot,
  onValidate,
  onGenerateSelected,
  linkMode,
  linkSourceNodeTitle,
  onToggleLinkMode,
  localeLabel,
  onOpenLanguageSwitcher,
  t,
}: HeaderProps) {
  return (
    <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 shrink-0 shadow-sm z-10 gap-3">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 rounded-md border border-slate-200 min-w-0">
          <span className={cn('w-2 h-2 rounded-full shadow-[0_0_8px_rgba(16,185,129,0.5)]', busy ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500')} />
          <span className="text-xs font-semibold text-slate-700 truncate max-w-[240px]" title={projectTitle}>
            {t('web.top.project_label', {title: projectTitle || t('web.top.project_unselected')})}
          </span>
        </div>

        {selectedNodeTitle ? (
          <div className="hidden xl:flex items-center gap-2 px-3 py-1.5 bg-pink-50 rounded-md border border-pink-200 min-w-0">
            <span className="text-xs font-semibold text-pink-700 truncate max-w-[220px]" title={selectedNodeTitle}>
              {t('web.top.node_label', {title: selectedNodeTitle})}
            </span>
          </div>
        ) : null}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="hidden lg:flex items-center bg-slate-50 rounded-lg p-1 border border-slate-200">
          <button
            onClick={() => void onRollback()}
            disabled={busy}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-200/50 transition-colors disabled:opacity-50"
          >
            <Undo2 size={16} />
            <span>{t('web.top.rollback_snapshot')}</span>
          </button>
          <div className="w-px h-4 bg-slate-200 mx-1" />
          <button
            onClick={() => void onRefresh()}
            disabled={busy}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-200/50 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={16} />
            <span>{t('web.top.refresh_workspace')}</span>
          </button>
          <div className="w-px h-4 bg-slate-200 mx-1" />
          <button
            onClick={() => void onSnapshot()}
            disabled={busy}
            className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-200/50 transition-colors disabled:opacity-50"
          >
            <Save size={16} />
            <span>{t('web.top.save_snapshot')}</span>
          </button>
        </div>

        <button
          onClick={() => void onValidate()}
          disabled={busy}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-50 border border-slate-200 transition-colors disabled:opacity-50"
        >
          <AlertTriangle size={16} />
          <span>{t('web.top.validate_project')}</span>
        </button>

        <button
          onClick={onToggleLinkMode}
          className={cn(
            'hidden md:flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border transition-colors',
            linkMode
              ? 'bg-pink-500 text-white border-pink-500 shadow-[0_0_12px_rgba(236,72,153,0.25)]'
              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-300',
          )}
          title={
            linkMode
              ? `${t('web.top.link_mode_hint')} / ${t('web.top.link_mode_source', {node: linkSourceNodeTitle || t('web.top.link_mode_source_empty')})}`
              : t('web.top.link_mode_enable')
          }
        >
          <Link2 size={16} />
          <span>{linkMode ? t('web.top.link_mode_on') : t('web.top.link_mode')}</span>
        </button>

        {linkMode ? (
          <div className="hidden xl:flex items-center px-3 py-2 rounded-lg border border-pink-100 bg-pink-50 text-[11px] font-semibold text-pink-700">
            {t('web.top.link_mode_hint')}
          </div>
        ) : null}

        <button
          onClick={onOpenLanguageSwitcher}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-50 border border-slate-200 transition-colors"
          title={t('web.top.language_switch')}
        >
          <Languages size={16} />
          <span>{t('web.top.locale_label')}: {localeLabel}</span>
        </button>

        <button
          onClick={() => setIsChatOpen(!isChatOpen)}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all border',
            isChatOpen
              ? 'bg-pink-500 text-white border-pink-500 shadow-[0_0_15px_rgba(236,72,153,0.3)]'
              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-300',
          )}
        >
          <MessageSquare size={16} />
          <span className="hidden sm:inline">{t('web.chat.toggle')}</span>
        </button>

        <button
          onClick={() => void onGenerateSelected()}
          disabled={busy || !selectedNodeTitle}
          className="ml-1 flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500 text-white hover:bg-emerald-600 border border-emerald-500 transition-colors shadow-[0_4px_10px_rgba(16,185,129,0.2)] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Play size={16} />
          <span className="hidden sm:inline">{t('web.top.generate_selected')}</span>
          <span className="sm:hidden">{t('web.top.generate')}</span>
        </button>
      </div>
    </header>
  );
}
