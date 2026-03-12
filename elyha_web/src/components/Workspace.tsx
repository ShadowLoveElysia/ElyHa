import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type ReactFlowInstance,
  BackgroundVariant,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {CustomNode} from './CustomNode';
import {GroupNode} from './GroupNode';
import {ContextMenu} from './ContextMenu';
import type {CreateNodePayload, GraphEdgePayload, GraphNodePayload, NodeType, UpdateNodePayload} from '../types';
import type {TranslationVars} from '../i18n';

interface WorkspaceProps {
  projectId: string;
  nodes: GraphNodePayload[];
  edges: GraphEdgePayload[];
  selectedNodeId: string;
  linkMode: boolean;
  busy: boolean;
  onSelectNode: (nodeId: string) => void | Promise<void>;
  onLinkNodeLeftClick: (nodeId: string) => void | Promise<void>;
  onLinkNodeRightClick: (nodeId: string) => void | Promise<void>;
  onCreateNode: (payload: CreateNodePayload) => Promise<void>;
  onUpdateNode: (nodeId: string, payload: UpdateNodePayload) => Promise<void>;
  onDeleteNode: (nodeId: string) => Promise<void>;
  onCreateEdge: (sourceId: string, targetId: string, label?: string) => Promise<void>;
  onDeleteEdge: (edgeId: string) => Promise<void>;
  onGenerateNode: (nodeId: string) => Promise<void>;
  onConfirm: (title: string, message: string, danger?: boolean) => Promise<boolean>;
  onPrompt: (options: {
    title: string;
    message?: string;
    defaultValue?: string;
    placeholder?: string;
    multiline?: boolean;
  }) => Promise<string | null>;
  onSelectOption: (options: {
    title: string;
    message?: string;
    defaultValue?: string;
    choices: Array<{value: string; label: string}>;
  }) => Promise<string | null>;
  t: (key: string, vars?: TranslationVars) => string;
}

function readString(meta: Record<string, unknown>, key: string, fallback = ''): string {
  const value = meta[key];
  if (typeof value === 'string') {
    return value;
  }
  return fallback;
}

function readNumber(meta: Record<string, unknown>, key: string, fallback: number): number {
  const value = meta[key];
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return parsed;
}

function normalizeMeta(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function contentPreview(node: GraphNodePayload): string {
  const metadata = normalizeMeta(node.metadata);
  const content = readString(metadata, 'content');
  if (content.trim()) {
    return content;
  }
  const summary = readString(metadata, 'summary');
  if (summary.trim()) {
    return summary;
  }
  const outline = readString(metadata, 'outline_markdown');
  if (outline.trim()) {
    return outline;
  }
  return '';
}

function visualKind(node: GraphNodePayload): 'document' | 'generation' {
  if (node.type === 'chapter' || node.type === 'checkpoint') {
    return 'document';
  }
  return 'generation';
}

export function Workspace({
  projectId,
  nodes,
  edges,
  selectedNodeId,
  linkMode,
  busy,
  onSelectNode,
  onLinkNodeLeftClick,
  onLinkNodeRightClick,
  onCreateNode,
  onUpdateNode,
  onDeleteNode,
  onCreateEdge,
  onDeleteEdge,
  onGenerateNode,
  onConfirm,
  onPrompt,
  onSelectOption,
  t,
}: WorkspaceProps) {
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);
  const [menu, setMenu] = useState<{x: number; y: number; type: 'pane' | 'node'; nodeId?: string} | null>(null);
  const nodeTypes = useMemo(
    () => ({
      custom: (props: any) => <CustomNode {...props} t={t} />,
      group: (props: any) => <GroupNode {...props} t={t} />,
    }),
    [t],
  );

  const nodeMap = useMemo(() => {
    return new Map(nodes.map((node) => [node.id, node]));
  }, [nodes]);

  const flowNodes = useMemo<Node[]>(() => {
    return nodes.map((node) => {
      const metadata = normalizeMeta(node.metadata);
      if (node.type === 'group') {
        const width = Math.max(260, readNumber(metadata, 'group_width', 360));
        const height = Math.max(120, readNumber(metadata, 'group_height', 420));
        return {
          id: node.id,
          type: 'group',
          position: {x: node.pos_x, y: node.pos_y},
          selected: node.id === selectedNodeId,
          style: {
            width,
            height,
          },
          data: {
            label: node.title,
          },
        };
      }

      return {
        id: node.id,
        type: 'custom',
        position: {x: node.pos_x, y: node.pos_y},
        selected: node.id === selectedNodeId,
        data: {
          label: node.title,
          type: visualKind(node),
          nodeType: node.type,
          nodeTypeLabel: t(`web.option.node_type.${node.type}`),
          content: contentPreview(node),
          status: node.status,
          onSaveContent: async (nextContent: string) => {
            const metadata = {
              ...normalizeMeta(node.metadata),
              content: nextContent,
              summary: nextContent.slice(0, 200),
            };
            await onUpdateNode(node.id, {metadata});
          },
          onRun: async () => {
            await onGenerateNode(node.id);
          },
        },
      };
    });
  }, [nodes, onGenerateNode, onUpdateNode, selectedNodeId, t]);

  const flowEdges = useMemo<Edge[]>(() => {
    return edges.map((edge) => ({
      id: edge.id,
      source: edge.source_id,
      target: edge.target_id,
      label: edge.label,
      animated: true,
      style: {stroke: '#ec4899', strokeWidth: 2},
    }));
  }, [edges]);

  const [reactFlowNodes, setReactFlowNodes, onReactFlowNodesChange] = useNodesState(flowNodes);
  const [reactFlowEdges, setReactFlowEdges, onReactFlowEdgesChange] = useEdgesState(flowEdges);

  useEffect(() => {
    setReactFlowNodes(flowNodes);
  }, [flowNodes, setReactFlowNodes]);

  useEffect(() => {
    setReactFlowEdges(flowEdges);
  }, [flowEdges, setReactFlowEdges]);

  const onConnect = useCallback(
    (params: Connection) => {
      if (!params.source || !params.target) {
        return;
      }
      void onCreateEdge(params.source, params.target, '');
    },
    [onCreateEdge],
  );

  const onPaneContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    setMenu({x: event.clientX, y: event.clientY, type: 'pane'});
  }, []);

  const onNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      event.preventDefault();
      if (linkMode) {
        void onLinkNodeRightClick(node.id);
        return;
      }
      setMenu({x: event.clientX, y: event.clientY, type: 'node', nodeId: node.id});
    },
    [linkMode, onLinkNodeRightClick],
  );

  const onPaneClick = useCallback(() => {
    setMenu(null);
    void onSelectNode('');
  }, [onSelectNode]);

  const handleMenuAction = useCallback(
    async (action: string) => {
      if (!menu) {
        return;
      }

      if (menu.type === 'pane') {
        if (!rfInstance) {
          return;
        }
        const position = rfInstance.screenToFlowPosition({x: menu.x, y: menu.y});
        if (action === 'create-group') {
          await onCreateNode({
            title: t('web.node.create_group_title'),
            type: 'group',
            pos_x: position.x,
            pos_y: position.y,
            metadata: {
              group_width: 360,
              group_height: 420,
            },
          });
        }
        if (action === 'create-node') {
          await onCreateNode({
            title: t('web.node.quick_create_title'),
            type: 'chapter',
            pos_x: position.x,
            pos_y: position.y,
            metadata: {
              content: '',
              summary: '',
            },
          });
        }
      }

      if (menu.type === 'node' && menu.nodeId) {
        const targetNode = nodeMap.get(menu.nodeId);
        if (!targetNode) {
          return;
        }

        if (action === 'delete') {
          const ok = await onConfirm(
            t('web.modal.node_delete_title'),
            t('web.modal.node_delete_body', {title: targetNode.title}),
            true,
          );
          if (ok) {
            await onDeleteNode(menu.nodeId);
          }
        }

        if (action === 'toggle-type' && targetNode.type !== 'group') {
          const cycle: NodeType[] = ['chapter', 'branch', 'parallel', 'checkpoint', 'merge'];
          const index = Math.max(0, cycle.indexOf(targetNode.type));
          const nextType = cycle[(index + 1) % cycle.length];
          await onUpdateNode(menu.nodeId, {type: nextType});
        }

        if (action === 'settings') {
          const fieldChoices: Array<{value: string; label: string}> = [
            {value: 'title', label: t('web.node.editor.field.title')},
            {value: 'storyline', label: t('web.node.editor.field.storyline')},
            {value: 'status', label: t('web.node.editor.field.status')},
          ];
          if (targetNode.type !== 'group') {
            fieldChoices.splice(1, 0, {value: 'content', label: t('web.node.editor.field.content')});
            fieldChoices.push({value: 'type', label: t('web.node.editor.field.type')});
          }

          const selectedField = await onSelectOption({
            title: t('web.node.editor.choose_field_title'),
            message: t('web.node.editor.choose_field_body'),
            defaultValue: fieldChoices[0]?.value || '',
            choices: fieldChoices,
          });
          if (!selectedField) {
            setMenu(null);
            return;
          }

          if (selectedField === 'title') {
            const nextTitle = await onPrompt({
              title: t('web.node.editor.title_prompt_title'),
              message: t('web.node.editor.title_prompt_body'),
              defaultValue: targetNode.title,
              placeholder: t('web.inspector.title_placeholder'),
            });
            if (nextTitle !== null && nextTitle.trim() && nextTitle.trim() !== targetNode.title) {
              await onUpdateNode(menu.nodeId, {title: nextTitle.trim()});
            }
          }

          if (selectedField === 'content' && targetNode.type !== 'group') {
            const currentContent = readString(normalizeMeta(targetNode.metadata), 'content');
            const nextContent = await onPrompt({
              title: t('web.node.editor.content_prompt_title'),
              message: t('web.node.editor.content_prompt_body'),
              defaultValue: currentContent,
              placeholder: t('web.node.editor.content_prompt_placeholder'),
              multiline: true,
            });
            if (nextContent !== null && nextContent !== currentContent) {
              await onUpdateNode(menu.nodeId, {
                metadata: {
                  ...normalizeMeta(targetNode.metadata),
                  content: nextContent,
                  summary: nextContent.slice(0, 200),
                },
              });
            }
          }

          if (selectedField === 'storyline') {
            const currentStoryline = targetNode.storyline_id || '';
            const nextStoryline = await onPrompt({
              title: t('web.node.editor.storyline_prompt_title'),
              message: t('web.node.editor.storyline_prompt_body'),
              defaultValue: currentStoryline,
              placeholder: t('web.node.editor.storyline_prompt_placeholder'),
            });
            if (nextStoryline !== null) {
              await onUpdateNode(menu.nodeId, {
                storyline_id: nextStoryline.trim() || null,
              });
            }
          }

          if (selectedField === 'type' && targetNode.type !== 'group') {
            const typeCycle: NodeType[] = ['chapter', 'branch', 'parallel', 'checkpoint', 'merge'];
            const nextType = await onSelectOption({
              title: t('web.node.editor.type_prompt_title'),
              message: t('web.node.editor.type_prompt_body'),
              defaultValue: targetNode.type,
              choices: typeCycle.map((item) => ({
                value: item,
                label: t(`web.option.node_type.${item}`),
              })),
            });
            if (nextType && nextType !== targetNode.type) {
              await onUpdateNode(menu.nodeId, {type: nextType as NodeType});
            }
          }

          if (selectedField === 'status') {
            const statuses: Array<'draft' | 'generated' | 'reviewed' | 'approved'> = ['draft', 'generated', 'reviewed', 'approved'];
            const nextStatus = await onSelectOption({
              title: t('web.node.editor.status_prompt_title'),
              message: t('web.node.editor.status_prompt_body'),
              defaultValue: targetNode.status,
              choices: statuses.map((item) => ({
                value: item,
                label: t(`web.option.node_status.${item}`),
              })),
            });
            if (nextStatus && nextStatus !== targetNode.status) {
              await onUpdateNode(menu.nodeId, {status: nextStatus as GraphNodePayload['status']});
            }
          }
        }

        if (action === 'bind') {
          const currentStoryline = targetNode.storyline_id || '';
          const nextStoryline = await onPrompt({
            title: t('web.node.editor.storyline_prompt_title'),
            message: t('web.node.editor.storyline_prompt_body'),
            defaultValue: currentStoryline,
            placeholder: t('web.node.editor.storyline_prompt_placeholder'),
          });
          if (nextStoryline !== null) {
            await onUpdateNode(menu.nodeId, {
              storyline_id: nextStoryline.trim() || null,
            });
          }
        }
      }

      setMenu(null);
    },
    [menu, nodeMap, onCreateNode, onDeleteNode, onPrompt, onSelectOption, onUpdateNode, rfInstance, t],
  );

  const handleNodeDragStop = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      void onUpdateNode(node.id, {
        pos_x: node.position.x,
        pos_y: node.position.y,
      });
    },
    [onUpdateNode],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onReactFlowNodesChange(changes);
      for (const change of changes as Array<any>) {
        if (change.type !== 'dimensions' || !change.dimensions || change.resizing) {
          continue;
        }
        const source = nodeMap.get(change.id);
        if (!source || source.type !== 'group') {
          continue;
        }
        const width = Math.round(Number(change.dimensions.width) || 360);
        const height = Math.round(Number(change.dimensions.height) || 420);
        const metadata = {
          ...normalizeMeta(source.metadata),
          group_width: width,
          group_height: height,
        };
        void onUpdateNode(source.id, {metadata});
      }
    },
    [nodeMap, onReactFlowNodesChange, onUpdateNode],
  );

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (linkMode) {
        void onLinkNodeLeftClick(node.id);
        return;
      }
      void onSelectNode(node.id);
    },
    [linkMode, onLinkNodeLeftClick, onSelectNode],
  );

  if (!projectId) {
    return (
      <div className="w-full h-full bg-slate-50 flex items-center justify-center text-slate-500">
        {t('web.workspace.select_project_hint')}
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-slate-50 relative">
      <ReactFlow
        nodes={reactFlowNodes}
        edges={reactFlowEdges}
        onNodesChange={handleNodesChange}
        onEdgesChange={onReactFlowEdgesChange}
        onConnect={onConnect}
        onInit={setRfInstance}
        onPaneContextMenu={onPaneContextMenu}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={onPaneClick}
        onNodeClick={handleNodeClick}
        onNodeDragStop={handleNodeDragStop}
        onNodesDelete={(deletedNodes) => {
          for (const node of deletedNodes) {
            void onDeleteNode(node.id);
          }
        }}
        onEdgesDelete={(deletedEdges) => {
          for (const edge of deletedEdges) {
            void onDeleteEdge(edge.id);
          }
        }}
        onEdgeDoubleClick={(_event, edge) => {
          void (async () => {
            const ok = await onConfirm(
              t('web.modal.edge_delete_title'),
              t('web.modal.edge_delete_body', {source: edge.source, target: edge.target}),
              true,
            );
            if (ok) {
              void onDeleteEdge(edge.id);
            }
          })();
        }}
        nodeTypes={nodeTypes}
        fitView
        className="bg-slate-50"
        minZoom={0.35}
        maxZoom={2.3}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={2} color="#cbd5e1" />
        <Controls className="bg-white border-slate-200 fill-slate-600" />
        <MiniMap
          className="bg-white border-slate-200"
          maskColor="rgba(248, 250, 252, 0.7)"
          nodeColor="#ec4899"
        />
      </ReactFlow>

      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          type={menu.type}
          onClose={() => setMenu(null)}
          onAction={(action) => void handleMenuAction(action)}
          t={t}
        />
      )}

      {busy ? (
        <div className="absolute inset-x-0 bottom-0 p-3 flex justify-center pointer-events-none">
          <div className="px-3 py-1.5 rounded-full text-xs font-semibold bg-slate-900 text-white shadow-lg">{t('web.workspace.syncing')}</div>
        </div>
      ) : null}
    </div>
  );
}
