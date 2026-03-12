import React, {useState} from 'react';
import {
  LayoutDashboard,
  Settings,
  ListTree,
  FolderOpen,
  PlusSquare,
  Network,
  Trash2,
} from 'lucide-react';
import {cn} from '../utils';
import type {ProjectPayload} from '../types';
import type {TranslationVars} from '../i18n';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (id: string) => void;
  projects: ProjectPayload[];
  currentProjectId: string;
  onSelectProject: (id: string) => void;
  onCreateProject: (title: string) => Promise<void>;
  onDeleteProject: (id: string) => Promise<void>;
  onQuickCreateNode: () => Promise<void>;
  onConfirm: (title: string, message: string, danger?: boolean) => Promise<boolean>;
  t: (key: string, vars?: TranslationVars) => string;
}

export function Sidebar({
  activeTab,
  setActiveTab,
  projects,
  currentProjectId,
  onSelectProject,
  onCreateProject,
  onDeleteProject,
  onQuickCreateNode,
  onConfirm,
  t,
}: SidebarProps) {
  const [newProjectTitle, setNewProjectTitle] = useState('');
  const [busy, setBusy] = useState(false);

  const currentProject = projects.find((item) => item.id === currentProjectId) || null;
  const navItems = [
    {icon: LayoutDashboard, label: t('web.nav.workspace'), id: 'workspace'},
    {icon: ListTree, label: t('web.nav.outline'), id: 'outline'},
    {icon: Network, label: t('web.nav.graph'), id: 'graph'},
    {icon: Settings, label: t('web.nav.settings'), id: 'settings'},
  ];

  const handleCreateProject = async () => {
    const title = newProjectTitle.trim();
    if (!title || busy) {
      return;
    }
    setBusy(true);
    try {
      await onCreateProject(title);
      setNewProjectTitle('');
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteProject = async () => {
    if (!currentProject || busy) {
      return;
    }
    const ok = await onConfirm(
      t('web.modal.project_delete_title'),
      t('web.modal.project_delete_body', {title: currentProject.title}),
      true,
    );
    if (!ok) {
      return;
    }
    setBusy(true);
    try {
      await onDeleteProject(currentProject.id);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="w-16 lg:w-72 h-full bg-white border-r border-slate-200 flex flex-col transition-all duration-300 shrink-0">
      <div className="h-14 flex items-center justify-center lg:justify-start lg:px-6 border-b border-slate-200">
        <div className="w-8 h-8 rounded-lg overflow-hidden shrink-0 bg-pink-100 border border-pink-200 flex items-center justify-center text-pink-600 font-bold">
          EH
        </div>
        <span className="ml-3 font-bold text-slate-800 hidden lg:block truncate tracking-tight">ElyHa Studio</span>
      </div>

      <div className="flex-1 py-6 flex flex-col gap-2 px-3 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                'flex items-center justify-center lg:justify-start h-10 lg:px-3 rounded-lg transition-colors group relative',
                isActive
                  ? 'bg-pink-50 text-pink-600 font-semibold'
                  : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900 font-medium',
              )}
            >
              <Icon
                size={20}
                className={cn('shrink-0', isActive ? 'text-pink-600' : 'text-slate-400 group-hover:text-slate-600')}
              />
              <span className="ml-3 text-sm hidden lg:block">{item.label}</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-slate-800 text-white text-xs rounded opacity-0 pointer-events-none group-hover:opacity-100 lg:hidden z-50 whitespace-nowrap shadow-md">
                {item.label}
              </div>
            </button>
          );
        })}
      </div>

      <div className="p-3 border-t border-slate-200 flex flex-col gap-2">
        <div className="hidden lg:block">
          <label className="block text-[11px] font-semibold uppercase tracking-wide text-slate-500 mb-1">{t('web.project.current')}</label>
          <select
            value={currentProjectId}
            onChange={(event) => onSelectProject(event.target.value)}
            className="w-full h-9 px-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-pink-300"
          >
            {projects.length === 0 && <option value="">{t('web.project.no_projects')}</option>}
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.title}
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={() => void onQuickCreateNode()}
          disabled={!currentProjectId || busy}
          className="flex items-center justify-center lg:justify-start h-10 lg:px-3 rounded-lg text-slate-500 hover:bg-slate-50 hover:text-slate-900 transition-colors group relative font-medium disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <PlusSquare size={20} className="shrink-0 text-slate-400 group-hover:text-slate-600" />
          <span className="ml-3 text-sm hidden lg:block">{t('web.sidebar.quick_create_node')}</span>
        </button>

        <button
          onClick={handleDeleteProject}
          disabled={!currentProjectId || busy}
          className="flex items-center justify-center lg:justify-start h-10 lg:px-3 rounded-lg text-red-500 hover:bg-red-50 hover:text-red-700 transition-colors group relative font-medium disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Trash2 size={20} className="shrink-0" />
          <span className="ml-3 text-sm hidden lg:block">{t('web.project.delete')}</span>
        </button>

        <div className="hidden lg:flex items-center gap-2 pt-1">
          <input
            value={newProjectTitle}
            onChange={(event) => setNewProjectTitle(event.target.value)}
            placeholder={t('web.project.new_placeholder')}
            className="flex-1 h-9 px-3 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-pink-300"
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                void handleCreateProject();
              }
            }}
          />
          <button
            onClick={() => void handleCreateProject()}
            disabled={!newProjectTitle.trim() || busy}
            className="h-9 px-3 rounded-lg bg-pink-500 text-white text-sm font-semibold hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed"
            title={t('web.project.create')}
          >
            <FolderOpen size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
