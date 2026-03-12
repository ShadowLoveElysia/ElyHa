import React, {useEffect, useRef, useState} from 'react';
import {Send, Bot, User, X, Sparkles, MoreHorizontal, PlusCircle, ShieldCheck} from 'lucide-react';
import {cn} from '../utils';
import {sendAiChat} from '../api';
import type {AiSuggestedOption} from '../types';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  suggestions?: AiSuggestedOption[];
}

interface AIChatProps {
  isOpen: boolean;
  onClose: () => void;
  projectId?: string;
  selectedNodeId?: string;
  onCreateSuggestionNode?: (option: AiSuggestedOption) => Promise<void>;
  onRefreshProject?: () => Promise<void>;
  onStatus?: (text: string, isError?: boolean) => void;
}

function errorToText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error || '未知错误');
}

export function AIChat({
  isOpen,
  onClose,
  projectId = '',
  selectedNodeId = '',
  onCreateSuggestionNode,
  onRefreshProject,
  onStatus,
}: AIChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'boot',
      role: 'assistant',
      content: '你好，我已接入 ElyHa 后端。你可以让我协助剧情构思、生成章节，或给出可一键创建的节点建议。',
    },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [allowNodeWrite, setAllowNodeWrite] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({behavior: 'smooth'});
  }, [messages]);

  const appendMessage = (message: ChatMessage) => {
    setMessages((prev) => [...prev, message]);
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const message = input.trim();
    if (!message || busy) {
      return;
    }
    if (!projectId) {
      appendMessage({
        id: `${Date.now()}-warn`,
        role: 'system',
        content: '请先创建或选择项目，再使用 AI 聊天。',
      });
      return;
    }

    appendMessage({id: `${Date.now()}-user`, role: 'user', content: message});
    setInput('');
    setBusy(true);

    try {
      const response = await sendAiChat({
        project_id: projectId,
        message,
        node_id: allowNodeWrite && selectedNodeId ? selectedNodeId : undefined,
        token_budget: 1800,
      });

      appendMessage({
        id: `${Date.now()}-assistant`,
        role: 'assistant',
        content: response.reply || 'AI 已处理请求，但没有返回文本。',
        suggestions: response.suggested_options || [],
      });

      if (response.updated_node_id) {
        onStatus?.(`AI 已更新节点 ${response.updated_node_id}`, false);
        if (onRefreshProject) {
          await onRefreshProject();
        }
      }
    } catch (error) {
      const text = errorToText(error);
      appendMessage({
        id: `${Date.now()}-error`,
        role: 'system',
        content: `请求失败：${text}`,
      });
      onStatus?.(text, true);
    } finally {
      setBusy(false);
    }
  };

  const adoptSuggestion = async (option: AiSuggestedOption) => {
    if (!onCreateSuggestionNode) {
      return;
    }
    try {
      await onCreateSuggestionNode(option);
      onStatus?.(`已创建建议节点：${option.title || '未命名'}`, false);
    } catch (error) {
      onStatus?.(`创建建议节点失败：${errorToText(error)}`, true);
    }
  };

  return (
    <div
      className={cn(
        'fixed inset-y-0 right-0 w-96 bg-white border-l border-slate-200 shadow-2xl flex flex-col transform transition-transform duration-300 ease-in-out z-50',
        isOpen ? 'translate-x-0' : 'translate-x-full',
      )}
    >
      <div className="h-14 border-b border-slate-200 flex items-center justify-between px-4 shrink-0 bg-white/95 backdrop-blur">
        <div className="flex items-center gap-2 text-slate-800">
          <Sparkles size={18} className="text-pink-500" />
          <span className="font-bold">AI 助手</span>
        </div>
        <div className="flex items-center gap-2">
          <button className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors">
            <MoreHorizontal size={18} />
          </button>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="px-4 py-2 border-b border-slate-100 bg-slate-50 text-xs text-slate-600">
        <div className="flex items-center justify-between gap-3">
          <span className="truncate">项目: {projectId || '未选择'}</span>
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={allowNodeWrite}
              onChange={(event) => setAllowNodeWrite(event.target.checked)}
            />
            <span className="inline-flex items-center gap-1">
              <ShieldCheck size={12} />
              允许写入选中节点
            </span>
          </label>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className={cn('flex gap-3', msg.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
            <div
              className={cn(
                'w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow-sm',
                msg.role === 'user'
                  ? 'bg-slate-100 text-slate-600 border border-slate-200'
                  : msg.role === 'assistant'
                    ? 'bg-pink-500 text-white'
                    : 'bg-amber-100 text-amber-700 border border-amber-200',
              )}
            >
              {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div className="max-w-[80%] space-y-2">
              <div
                className={cn(
                  'rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm',
                  msg.role === 'user'
                    ? 'bg-slate-100 text-slate-800 rounded-tr-sm border border-slate-200/50'
                    : msg.role === 'assistant'
                      ? 'bg-pink-50 text-pink-900 border border-pink-100 rounded-tl-sm'
                      : 'bg-amber-50 text-amber-900 border border-amber-200 rounded-tl-sm',
                )}
              >
                {msg.content}
              </div>

              {msg.suggestions && msg.suggestions.length > 0 ? (
                <div className="space-y-2">
                  {msg.suggestions.map((option, idx) => (
                    <div key={`${msg.id}-${idx}`} className="rounded-xl border border-slate-200 bg-white p-3 text-xs shadow-sm">
                      <div className="font-semibold text-slate-800">{option.title || `建议 ${idx + 1}`}</div>
                      <div className="text-slate-600 mt-1 whitespace-pre-wrap">
                        {option.summary || option.description || option.outline_steps || '无摘要'}
                      </div>
                      <button
                        onClick={() => void adoptSuggestion(option)}
                        className="mt-2 inline-flex items-center gap-1 rounded-md bg-emerald-50 text-emerald-700 px-2.5 py-1.5 text-xs font-semibold hover:bg-emerald-100"
                      >
                        <PlusCircle size={13} />
                        创建为节点
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-slate-200 bg-white">
        <form onSubmit={(event) => void handleSend(event)} className="relative flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={projectId ? '输入你的想法或指令...' : '请先创建或选择项目'}
              disabled={!projectId || busy}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl py-3 pl-4 pr-12 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent resize-none min-h-[44px] max-h-32 shadow-inner disabled:opacity-60"
              rows={1}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend(event);
                }
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || !projectId || busy}
              className="absolute right-2 bottom-2 p-1.5 bg-pink-500 text-white rounded-lg hover:bg-pink-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              <Send size={16} />
            </button>
          </div>
        </form>
        <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400 font-medium">
          <span>Shift + Enter 换行</span>
          <span>{busy ? 'AI 处理中...' : '使用后端 /api/ai/chat'}</span>
        </div>
      </div>
    </div>
  );
}
