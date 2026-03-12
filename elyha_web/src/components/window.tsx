import React, {useEffect, useState} from 'react';
import {AlertTriangle} from 'lucide-react';
import {cn} from '../utils';
import type {TranslationVars} from '../i18n';

export type WindowDialogType = 'alert' | 'confirm' | 'prompt' | 'select';
export interface WindowDialogOption {
  value: string;
  label: string;
}

export interface WindowDialogState {
  type: WindowDialogType;
  title: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  defaultValue?: string;
  placeholder?: string;
  multiline?: boolean;
  options?: WindowDialogOption[];
}

interface WindowDialogProps {
  dialog: WindowDialogState | null;
  onConfirm: (value?: string) => void;
  onCancel: () => void;
  t?: (key: string, vars?: TranslationVars) => string;
}

export function WindowDialog({dialog, onConfirm, onCancel, t}: WindowDialogProps) {
  const [value, setValue] = useState('');

  useEffect(() => {
    if (!dialog) {
      setValue('');
      return;
    }
    if (dialog.type === 'prompt') {
      setValue(dialog.defaultValue || '');
      return;
    }
    if (dialog.type === 'select') {
      const fallback = dialog.options?.[0]?.value || '';
      setValue(dialog.defaultValue || fallback);
      return;
    }
    setValue('');
  }, [dialog]);

  useEffect(() => {
    if (!dialog) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key === 'Enter' && (dialog.type === 'confirm' || dialog.type === 'alert')) {
        event.preventDefault();
        onConfirm();
      }
      if (event.key === 'Enter' && dialog.type === 'prompt' && !dialog.multiline) {
        event.preventDefault();
        onConfirm(value);
      }
      if (event.key === 'Enter' && dialog.type === 'select') {
        event.preventDefault();
        onConfirm(value);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [dialog, onCancel, onConfirm, value]);

  if (!dialog) {
    return null;
  }

  const confirmText = dialog.confirmText || (t ? t('web.modal.confirm') : 'Confirm');
  const cancelText = dialog.cancelText || (t ? t('web.modal.cancel') : 'Cancel');
  const isDanger = Boolean(dialog.danger);

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/35 backdrop-blur-[1px]" onClick={onCancel} />
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-200 bg-white shadow-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
          {isDanger ? <AlertTriangle size={18} className="text-red-500" /> : null}
          <h3 className="text-base font-bold text-slate-800">{dialog.title}</h3>
        </div>

        <div className="px-5 py-4 space-y-3">
          {dialog.message ? <p className="text-sm text-slate-600 whitespace-pre-wrap leading-relaxed">{dialog.message}</p> : null}

          {dialog.type === 'prompt' ? (
            dialog.multiline ? (
              <textarea
                value={value}
                onChange={(event) => setValue(event.target.value)}
                autoFocus
                rows={8}
                placeholder={dialog.placeholder || ''}
                className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-pink-300"
              />
            ) : (
              <input
                value={value}
                onChange={(event) => setValue(event.target.value)}
                autoFocus
                placeholder={dialog.placeholder || ''}
                className="w-full h-11 rounded-xl border border-slate-200 px-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-pink-300"
              />
            )
          ) : null}

          {dialog.type === 'select' ? (
            <select
              value={value}
              onChange={(event) => setValue(event.target.value)}
              autoFocus
              className="w-full h-11 rounded-xl border border-slate-200 px-3 text-sm text-slate-700 bg-white focus:outline-none focus:ring-2 focus:ring-pink-300"
            >
              {(dialog.options || []).map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : null}
        </div>

        <div className="px-5 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2">
          {dialog.type !== 'alert' ? (
            <button
              onClick={onCancel}
              className="h-10 px-4 rounded-lg border border-slate-300 text-slate-700 text-sm font-semibold hover:bg-slate-100"
            >
              {cancelText}
            </button>
          ) : null}

          <button
            onClick={() => onConfirm(dialog.type === 'prompt' || dialog.type === 'select' ? value : undefined)}
            className={cn(
              'h-10 px-4 rounded-lg text-sm font-semibold text-white',
              isDanger ? 'bg-red-500 hover:bg-red-600' : 'bg-pink-500 hover:bg-pink-600',
            )}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
