import React, { useState } from 'react';
import { NodeResizer, useReactFlow } from '@xyflow/react';
import { Folder, ArrowDownAZ, ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '../utils';

export function GroupNode({ id, data, selected }: any) {
  const { getNodes, setNodes } = useReactFlow();
  const label = data?.label || '分组节点';
  const [collapsed, setCollapsed] = useState(false);
  const [prevSize, setPrevSize] = useState({ width: 360, height: 500 });

  const sortChildren = (e: React.MouseEvent) => {
    e.stopPropagation();
    const allNodes = getNodes();
    const children = allNodes.filter(n => n.parentId === id);
    
    // Sort by current Y position to maintain relative order
    children.sort((a, b) => a.position.y - b.position.y);
    
    let currentY = 60; // Start below the header
    const updatedChildren = children.map(c => {
      // Estimate height or use measured if available
      const height = c.measured?.height || 180;
      const pos = { x: 20, y: currentY };
      currentY += height + 20; // 20px gap
      return { ...c, position: pos };
    });

    setNodes(nds => nds.map(n => {
      const updated = updatedChildren.find(uc => uc.id === n.id);
      return updated ? { ...n, position: updated.position } : n;
    }));
  };

  const toggleCollapse = (e: React.MouseEvent) => {
    e.stopPropagation();
    const willCollapse = !collapsed;
    setCollapsed(willCollapse);

    setNodes(nds => nds.map(n => {
      if (n.parentId === id) {
        return { ...n, hidden: willCollapse };
      }
      if (n.id === id) {
        if (willCollapse) {
          // Save current size before collapsing
          const currentWidth = n.measured?.width ?? n.style?.width ?? 360;
          const currentHeight = n.measured?.height ?? n.style?.height ?? 500;
          setPrevSize({ width: Number(currentWidth), height: Number(currentHeight) });
          return { ...n, style: { ...n.style, width: 300, height: 48, minHeight: 48 } };
        } else {
          return { ...n, style: { ...n.style, width: prevSize.width, height: prevSize.height, minHeight: 250 } };
        }
      }
      return n;
    }));
  };

  return (
    <div className={cn(
      "w-full h-full bg-slate-50/50 border-2 border-dashed border-slate-300 rounded-2xl shadow-sm transition-colors hover:border-pink-300 relative",
      collapsed && "bg-white border-solid border-slate-200 shadow-md"
    )}>
      {!collapsed && <NodeResizer color="#ec4899" isVisible={selected} minWidth={350} minHeight={250} />}
      <div className={cn(
        "px-4 py-3 flex items-center justify-between border-b border-slate-200/80 bg-white/80 rounded-t-2xl backdrop-blur-sm",
        collapsed && "border-b-0 rounded-b-2xl"
      )}>
        <div className="flex items-center gap-2 cursor-pointer" onClick={toggleCollapse}>
          {collapsed ? <ChevronRight size={18} className="text-slate-400 hover:text-pink-500 transition-colors" /> : <ChevronDown size={18} className="text-slate-400 hover:text-pink-500 transition-colors" />}
          <Folder size={18} className="text-pink-500" />
          <span className="text-sm font-bold text-slate-700">{label}</span>
        </div>
        {!collapsed && (
          <button 
            onClick={sortChildren} 
            className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold text-pink-600 bg-pink-50 hover:bg-pink-100 rounded-md transition-colors"
            title="按当前顺序自动排列子节点"
          >
            <ArrowDownAZ size={14} />
            <span>自然排序</span>
          </button>
        )}
      </div>
    </div>
  );
}
