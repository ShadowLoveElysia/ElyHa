import React, {useEffect, useMemo, useRef, useState} from 'react';
import {Network, Database, RefreshCw, BarChart3, GitBranch, Link2, Users, Globe} from 'lucide-react';
import type {
  CharacterStatusPayload,
  ItemStatusPayload,
  ProjectInsights,
  RelationshipStatusPayload,
} from '../types';
import type {TranslationVars} from '../i18n';

interface KnowledgeGraphProps {
  projectId?: string;
  insights: ProjectInsights | null;
  relationships: RelationshipStatusPayload[];
  characterStates: CharacterStatusPayload[];
  itemStates: ItemStatusPayload[];
  loading: boolean;
  onRefresh: () => Promise<void>;
  onUpsertRelationship: (payload: {
    subject_character_id: string;
    object_character_id: string;
    relation_type: string;
    source_excerpt?: string;
  }) => Promise<boolean>;
  t: (key: string, vars?: TranslationVars) => string;
}

interface SatelliteItem {
  id: string;
  title: string;
  subtitle: string;
  tone: 'rose' | 'sky' | 'emerald' | 'amber' | 'slate';
  hopTarget?: string;
}

interface OrbitOffset {
  x: number;
  y: number;
}

export function KnowledgeGraph({
  projectId = '',
  insights,
  relationships,
  characterStates,
  itemStates,
  loading,
  onRefresh,
  onUpsertRelationship,
  t,
}: KnowledgeGraphProps) {
  const [subject, setSubject] = useState('');
  const [objectValue, setObjectValue] = useState('');
  const [relationType, setRelationType] = useState('');
  const [sourceExcerpt, setSourceExcerpt] = useState('');
  const [saving, setSaving] = useState(false);
  const [focusCharacter, setFocusCharacter] = useState('');
  const [orbitTransitioning, setOrbitTransitioning] = useState(false);
  const [orbitScale, setOrbitScale] = useState(1);
  const [orbitAutoRotate, setOrbitAutoRotate] = useState(false);
  const [orbitRotation, setOrbitRotation] = useState(0);
  const [draggingSatelliteId, setDraggingSatelliteId] = useState('');
  const [satelliteOffsets, setSatelliteOffsets] = useState<Record<string, OrbitOffset>>({});
  const dragStateRef = useRef<{
    pointerId: number;
    itemId: string;
    startClientX: number;
    startClientY: number;
    startOffsetX: number;
    startOffsetY: number;
    moved: boolean;
  } | null>(null);
  const suppressClickRef = useRef<{
    itemId: string;
    at: number;
  } | null>(null);
  const rotationFrameRef = useRef<number | null>(null);
  const lastRotationTsRef = useRef(0);

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

  const canSaveRelationship = Boolean(
    projectId &&
      subject.trim() &&
      objectValue.trim() &&
      relationType.trim() &&
      !saving,
  );

  const saveRelationship = async () => {
    if (!canSaveRelationship) {
      return;
    }
    setSaving(true);
    try {
      const ok = await onUpsertRelationship({
        subject_character_id: subject.trim(),
        object_character_id: objectValue.trim(),
        relation_type: relationType.trim(),
        source_excerpt: sourceExcerpt.trim(),
      });
      if (ok) {
        setSourceExcerpt('');
      }
    } finally {
      setSaving(false);
    }
  };

  const focusCandidates = useMemo(() => {
    const values = new Set<string>();
    for (const row of characterStates) {
      const id = String(row.character_id || '').trim();
      if (id) {
        values.add(id);
      }
    }
    for (const row of relationships) {
      const subjectId = String(row.subject_character_id || '').trim();
      const objectId = String(row.object_character_id || '').trim();
      if (subjectId) {
        values.add(subjectId);
      }
      if (objectId) {
        values.add(objectId);
      }
    }
    if (insights) {
      for (const row of insights.characters) {
        const name = String(row.name || '').trim();
        if (name) {
          values.add(name);
        }
      }
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b));
  }, [characterStates, insights, relationships]);

  useEffect(() => {
    if (!focusCandidates.length) {
      if (focusCharacter) {
        setFocusCharacter('');
      }
      return;
    }
    if (!focusCharacter || !focusCandidates.includes(focusCharacter)) {
      setFocusCharacter(focusCandidates[0]);
    }
  }, [focusCandidates, focusCharacter]);

  useEffect(() => {
    if (!focusCharacter) {
      setOrbitTransitioning(false);
      return;
    }
    setOrbitTransitioning(true);
    const timer = window.setTimeout(() => {
      setOrbitTransitioning(false);
    }, 260);
    return () => window.clearTimeout(timer);
  }, [focusCharacter]);

  useEffect(() => {
    setSatelliteOffsets({});
    setDraggingSatelliteId('');
    dragStateRef.current = null;
    suppressClickRef.current = null;
  }, [focusCharacter]);

  useEffect(() => {
    if (!orbitAutoRotate) {
      if (rotationFrameRef.current !== null) {
        window.cancelAnimationFrame(rotationFrameRef.current);
        rotationFrameRef.current = null;
      }
      lastRotationTsRef.current = 0;
      return;
    }
    const tick = (ts: number) => {
      if (lastRotationTsRef.current <= 0) {
        lastRotationTsRef.current = ts;
      }
      const deltaSec = (ts - lastRotationTsRef.current) / 1000;
      lastRotationTsRef.current = ts;
      setOrbitRotation((value) => {
        const next = value + deltaSec * 0.32;
        return next >= Math.PI * 2 ? next - Math.PI * 2 : next;
      });
      rotationFrameRef.current = window.requestAnimationFrame(tick);
    };
    rotationFrameRef.current = window.requestAnimationFrame(tick);
    return () => {
      if (rotationFrameRef.current !== null) {
        window.cancelAnimationFrame(rotationFrameRef.current);
        rotationFrameRef.current = null;
      }
      lastRotationTsRef.current = 0;
    };
  }, [orbitAutoRotate]);

  const focusState = useMemo(() => {
    const target = String(focusCharacter || '').trim();
    if (!target) {
      return null;
    }
    return characterStates.find((row) => String(row.character_id || '').trim() === target) || null;
  }, [characterStates, focusCharacter]);

  const satelliteItems = useMemo<SatelliteItem[]>(() => {
    const target = String(focusCharacter || '').trim();
    if (!target) {
      return [];
    }
    const items: SatelliteItem[] = [];

    for (const row of relationships) {
      const left = String(row.subject_character_id || '').trim();
      const right = String(row.object_character_id || '').trim();
      if (!left || !right) {
        continue;
      }
      if (left !== target && right !== target) {
        continue;
      }
      const other = left === target ? right : left;
      const relation = String(row.relation_type || '').trim() || 'related';
      const direction = left === target ? '\u2192' : '\u2190';
      items.push({
        id: `rel-${left}-${right}-${relation}`,
        title: other,
        subtitle: `${direction} ${relation}`,
        tone: 'rose',
        hopTarget: other,
      });
    }

    if (focusState) {
      items.push({
        id: `alive-${target}`,
        title: focusState.alive ? t('web.insight.state_alive') : t('web.insight.state_dead'),
        subtitle: t('web.insight.state_alive_label'),
        tone: 'emerald',
      });
      const location = String(focusState.location || '').trim();
      if (location) {
        items.push({
          id: `loc-${target}`,
          title: location,
          subtitle: t('web.insight.state_location'),
          tone: 'sky',
        });
      }
      const faction = String(focusState.faction || '').trim();
      if (faction) {
        items.push({
          id: `fac-${target}`,
          title: faction,
          subtitle: t('web.insight.state_faction'),
          tone: 'amber',
        });
      }
      for (const itemId of focusState.held_items || []) {
        const cleanItem = String(itemId || '').trim();
        if (!cleanItem) {
          continue;
        }
        items.push({
          id: `hold-${target}-${cleanItem}`,
          title: cleanItem,
          subtitle: t('web.insight.state_holding'),
          tone: 'slate',
        });
      }
      const attrs = focusState.state_attributes || {};
      for (const [key, value] of Object.entries(attrs).slice(0, 6)) {
        const label = `${key}: ${String(value ?? '')}`.trim();
        if (!label) {
          continue;
        }
        items.push({
          id: `attr-${target}-${key}`,
          title: label,
          subtitle: t('web.insight.state_attribute'),
          tone: 'emerald',
        });
      }
    }

    for (const row of itemStates) {
      const owner = String(row.owner_character_id || '').trim();
      if (!owner || owner !== target) {
        continue;
      }
      const itemId = String(row.item_id || '').trim();
      if (!itemId) {
        continue;
      }
      items.push({
        id: `own-${target}-${itemId}`,
        title: itemId,
        subtitle: row.destroyed ? t('web.insight.state_destroyed') : t('web.insight.state_owned_item'),
        tone: row.destroyed ? 'amber' : 'slate',
      });
    }

    return items.slice(0, 28);
  }, [focusCharacter, focusState, itemStates, relationships, t]);

  useEffect(() => {
    const validIds = new Set(satelliteItems.map((item) => item.id));
    setSatelliteOffsets((prev) => {
      const next: Record<string, OrbitOffset> = {};
      for (const [key, value] of Object.entries(prev) as Array<[string, OrbitOffset]>) {
        if (validIds.has(key)) {
          next[key] = value;
        }
      }
      return next;
    });
  }, [satelliteItems]);

  const handleOrbitWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (!event.altKey) {
      return;
    }
    event.preventDefault();
    const direction = event.deltaY < 0 ? 1 : -1;
    setOrbitScale((value) => {
      const next = value + direction * 0.08;
      if (next < 0.6) {
        return 0.6;
      }
      if (next > 2.2) {
        return 2.2;
      }
      return next;
    });
  };

  const handleSatellitePointerDown = (
    itemId: string,
    event: React.PointerEvent<HTMLButtonElement>,
  ) => {
    if (event.button !== 0) {
      return;
    }
    const offset = satelliteOffsets[itemId] || {x: 0, y: 0};
    dragStateRef.current = {
      pointerId: event.pointerId,
      itemId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startOffsetX: offset.x,
      startOffsetY: offset.y,
      moved: false,
    };
    setDraggingSatelliteId(itemId);
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handleSatellitePointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    const safeScale = Math.max(0.2, orbitScale);
    const deltaX = (event.clientX - dragState.startClientX) / safeScale;
    const deltaY = (event.clientY - dragState.startClientY) / safeScale;
    if (!dragState.moved && Math.hypot(deltaX, deltaY) > 2) {
      dragState.moved = true;
    }
    setSatelliteOffsets((prev) => ({
      ...prev,
      [dragState.itemId]: {
        x: dragState.startOffsetX + deltaX,
        y: dragState.startOffsetY + deltaY,
      },
    }));
  };

  const finishSatellitePointer = (event: React.PointerEvent<HTMLButtonElement>) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    if (dragState.moved) {
      suppressClickRef.current = {
        itemId: dragState.itemId,
        at: Date.now(),
      };
    }
    dragStateRef.current = null;
    setDraggingSatelliteId('');
  };

  const focusSummary = useMemo(() => {
    if (!focusState) {
      return t('web.insight.state_unknown');
    }
    const location = String(focusState.location || '').trim() || '-';
    const faction = String(focusState.faction || '').trim() || '-';
    const heldCount = Array.isArray(focusState.held_items) ? focusState.held_items.length : 0;
    return t('web.insight.state_center_summary', {
      alive: focusState.alive ? t('web.insight.state_alive') : t('web.insight.state_dead'),
      location,
      faction,
      held: heldCount,
    });
  }, [focusState, t]);

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
                <EntityPanel
                  title={t('web.insight.characters')}
                  icon={<Users size={14} />}
                  rows={insights.characters.map((item) => ({
                    id: item.name,
                    label: item.name,
                    count: item.count,
                  }))}
                  t={t}
                />
                <EntityPanel
                  title={t('web.insight.worldviews')}
                  icon={<Globe size={14} />}
                  rows={insights.worldviews.map((item) => ({
                    id: item.name,
                    label: item.name,
                    count: item.count,
                  }))}
                  t={t}
                />
                <EntityPanel
                  title={t('web.insight.items')}
                  icon={<Database size={14} />}
                  rows={insights.items.map((item) => ({
                    id: item.name,
                    label: item.owner
                      ? t('web.insight.item_owner_row', {name: item.name, owner: item.owner})
                      : item.name,
                    count: item.count,
                  }))}
                  t={t}
                />
              </div>
            </section>

            <section className="rounded-2xl bg-white border border-sky-200 shadow-sm p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-semibold text-slate-800">{t('web.insight.state_satellite_title')}</h3>
                <div className="flex items-center gap-3 text-xs text-slate-600">
                  <label className="inline-flex items-center gap-1.5 select-none">
                    <input
                      type="checkbox"
                      checked={orbitAutoRotate}
                      onChange={(event) => setOrbitAutoRotate(event.target.checked)}
                      className="h-3.5 w-3.5 rounded border-slate-300"
                    />
                    <span>{t('web.insight.state_satellite_auto_rotate')}</span>
                  </label>
                  <span>{t('web.insight.state_satellite_focus_label')}</span>
                  <select
                    value={focusCharacter}
                    onChange={(event) => setFocusCharacter(event.target.value)}
                    className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs"
                  >
                    {focusCandidates.length === 0 ? (
                      <option value="">{t('web.insight.state_satellite_empty')}</option>
                    ) : (
                      focusCandidates.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))
                    )}
                  </select>
                </div>
              </div>
              <p className="text-xs text-sky-700 mt-1">{t('web.insight.state_satellite_hint')}</p>
              {focusCharacter ? (
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <div className="mb-2 flex items-center justify-between text-[11px] text-slate-500">
                    <span>{t('web.insight.state_satellite_drag_zoom_tip')}</span>
                    <span>{Math.round(orbitScale * 100)}%</span>
                  </div>
                  <div
                    className={[
                      'relative h-[420px] w-full overflow-hidden rounded-lg border border-slate-200 bg-white transition-all duration-300 ease-out',
                      orbitTransitioning ? 'opacity-70 scale-[0.985]' : 'opacity-100 scale-100',
                    ].join(' ')}
                    onWheel={handleOrbitWheel}
                  >
                    <div
                      className="absolute inset-0"
                      style={{
                        transform: `scale(${orbitScale})`,
                        transformOrigin: '50% 50%',
                      }}
                    >
                      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-20 w-40 rounded-xl border border-sky-300 bg-sky-50 px-3 py-2 text-center shadow-sm transition-all duration-300">
                        <div className="text-sm font-semibold text-sky-800 truncate">{focusCharacter}</div>
                        <div className="mt-1 text-[11px] text-slate-600 leading-snug">{focusSummary}</div>
                      </div>
                      {satelliteItems.map((item, index) => {
                        const total = Math.max(1, satelliteItems.length);
                        const angle = (index / total) * Math.PI * 2 - Math.PI / 2 + orbitRotation;
                        const ring = index % 2 === 0 ? 132 : 186;
                        const baseX = Math.cos(angle) * ring;
                        const baseY = Math.sin(angle) * ring;
                        const offset = satelliteOffsets[item.id] || {x: 0, y: 0};
                        const x = baseX + offset.x;
                        const y = baseY + offset.y;
                        const toneClass = toneToClass(item.tone);
                        const isDragging = draggingSatelliteId === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => {
                              const suppressed = suppressClickRef.current;
                              if (
                                suppressed &&
                                suppressed.itemId === item.id &&
                                Date.now() - suppressed.at < 260
                              ) {
                                suppressClickRef.current = null;
                                return;
                              }
                              if (item.hopTarget && focusCandidates.includes(item.hopTarget)) {
                                setFocusCharacter(item.hopTarget);
                              }
                            }}
                            onPointerDown={(event) => handleSatellitePointerDown(item.id, event)}
                            onPointerMove={handleSatellitePointerMove}
                            onPointerUp={finishSatellitePointer}
                            onPointerCancel={finishSatellitePointer}
                            onLostPointerCapture={finishSatellitePointer}
                            className={[
                              'absolute z-10 w-32 rounded-lg border px-2.5 py-1.5 text-left text-[11px] shadow-sm',
                              toneClass,
                              isDragging ? 'cursor-grabbing select-none' : 'cursor-grab',
                              item.hopTarget ? 'hover:scale-[1.03]' : '',
                            ].join(' ')}
                            style={{
                              left: '50%',
                              top: '50%',
                              transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
                              transition: isDragging ? 'none' : 'transform 240ms ease',
                            }}
                          >
                            <div className="font-semibold truncate">{item.title}</div>
                            <div className="mt-0.5 text-[10px] opacity-80 truncate">{item.subtitle}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mt-3 text-xs text-slate-500">{t('web.insight.state_satellite_empty')}</div>
              )}
            </section>

            <section className="rounded-2xl bg-white border border-amber-200 shadow-sm p-4">
              <h3 className="font-semibold text-slate-800">{t('web.insight.relationship_editor_title')}</h3>
              <p className="text-xs text-amber-700 mt-1">{t('web.insight.relationship_editor_warning')}</p>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2">
                <input
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder={t('web.insight.relationship_subject_placeholder')}
                  className="h-9 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                />
                <input
                  value={objectValue}
                  onChange={(event) => setObjectValue(event.target.value)}
                  placeholder={t('web.insight.relationship_object_placeholder')}
                  className="h-9 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                />
                <input
                  value={relationType}
                  onChange={(event) => setRelationType(event.target.value)}
                  placeholder={t('web.insight.relationship_type_placeholder')}
                  className="h-9 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                />
              </div>
              <div className="mt-2">
                <input
                  value={sourceExcerpt}
                  onChange={(event) => setSourceExcerpt(event.target.value)}
                  placeholder={t('web.insight.relationship_source_placeholder')}
                  className="w-full h-9 rounded-lg border border-slate-200 px-3 text-sm bg-white"
                />
              </div>
              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="text-xs text-slate-500">{t('web.insight.relationship_sync_note')}</span>
                <button
                  onClick={() => void saveRelationship()}
                  disabled={!canSaveRelationship}
                  className="h-9 px-4 rounded-lg bg-amber-500 text-white text-sm font-semibold hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? t('web.insight.relationship_saving') : t('web.insight.relationship_save')}
                </button>
              </div>
              <div className="mt-3 space-y-1.5 max-h-52 overflow-y-auto pr-1">
                {relationships.length === 0 ? (
                  <div className="text-xs text-slate-500">{t('web.insight.relationship_empty')}</div>
                ) : (
                  relationships.slice(0, 120).map((row) => (
                    <div
                      key={`${row.subject_character_id}-${row.object_character_id}-${row.updated_at}`}
                      className="text-xs rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-slate-700"
                    >
                      <span className="font-medium">{row.subject_character_id}</span>
                      <span className="mx-1 text-slate-400">\u2192</span>
                      <span className="font-medium">{row.object_character_id}</span>
                      <span className="mx-1 text-slate-400">\u00b7</span>
                      <span className="text-amber-700">{row.relation_type || 'related'}</span>
                    </div>
                  ))
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function toneToClass(tone: SatelliteItem['tone']): string {
  if (tone === 'rose') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  if (tone === 'sky') {
    return 'border-sky-200 bg-sky-50 text-sky-700';
  }
  if (tone === 'emerald') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (tone === 'amber') {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  return 'border-slate-200 bg-slate-50 text-slate-700';
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
