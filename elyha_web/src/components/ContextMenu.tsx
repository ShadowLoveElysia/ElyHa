import React, { useEffect, useRef } from 'react';
import { FolderPlus, FilePlus, Trash2, Settings, Link, Sparkles } from 'lucide-react';
import type {TranslationVars} from '../i18n';

interface ContextMenuProps {
  x: number;
  y: number;
  type: 'pane' | 'node';
  onClose: () => void;
  onAction: (action: string) => void;
  t: (key: string, vars?: TranslationVars) => string;
}

export function ContextMenu({ x, y, type, onClose, onAction, t }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  return (
    <div
      ref={menuRef}
      style={{ top: y, left: x }}
      className="fixed z-50 w-48 bg-white rounded-xl shadow-xl border border-slate-200 py-1 overflow-hidden"
    >
      {type === 'pane' ? (
        <>
          <button onClick={() => onAction('create-group')} className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-pink-50 hover:text-pink-600 flex items-center gap-2 transition-colors">
            <FolderPlus size={16} /> {t('web.context_menu.create_group')}
          </button>
          <button onClick={() => onAction('create-node')} className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-pink-50 hover:text-pink-600 flex items-center gap-2 transition-colors">
            <FilePlus size={16} /> {t('web.context_menu.create_node')}
          </button>
        </>
      ) : (
        <>
          <button onClick={() => onAction('settings')} className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2 transition-colors">
            <Settings size={16} /> {t('web.context_menu.settings')}
          </button>
          <button onClick={() => onAction('bind')} className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2 transition-colors">
            <Link size={16} /> {t('web.context_menu.bind_storyline')}
          </button>
          <button onClick={() => onAction('toggle-type')} className="w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2 transition-colors">
            <Sparkles size={16} /> {t('web.context_menu.toggle_type')}
          </button>
          <div className="h-px bg-slate-200 my-1" />
          <button onClick={() => onAction('delete')} className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2 transition-colors">
            <Trash2 size={16} /> {t('web.context_menu.delete_node')}
          </button>
        </>
      )}
    </div>
  );
}
