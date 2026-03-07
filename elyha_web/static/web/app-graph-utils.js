(function () {
  "use strict";

  function rectAnchor(centerX, centerY, targetX, targetY, halfWidth, halfHeight) {
    const dx = targetX - centerX;
    const dy = targetY - centerY;
    if (dx === 0 && dy === 0) {
      return { x: centerX, y: centerY };
    }
    const scale = 1 / Math.max(Math.abs(dx) / halfWidth, Math.abs(dy) / halfHeight, 0.0001);
    return {
      x: centerX + dx * scale,
      y: centerY + dy * scale
    };
  }

  function cubicMidpoint(p0, p1, p2, p3) {
    return {
      x: 0.125 * p0.x + 0.375 * p1.x + 0.375 * p2.x + 0.125 * p3.x,
      y: 0.125 * p0.y + 0.375 * p1.y + 0.375 * p2.y + 0.125 * p3.y
    };
  }

  function edgeNarrativeOrder(edge) {
    const raw = edge ? edge.narrative_order : null;
    const value = Number(raw);
    if (!Number.isFinite(value)) {
      return null;
    }
    const normalized = Math.floor(value);
    return normalized > 0 ? normalized : null;
  }

  function edgeDisplayLabel(edge) {
    const order = edgeNarrativeOrder(edge);
    const orderText = order ? String(order) : "";
    const label = edge && typeof edge.label === "string" ? edge.label.trim() : "";
    if (orderText && label) {
      return orderText + " | " + label;
    }
    return orderText || label;
  }

  function compareEdgesByNarrativeOrder(left, right) {
    const leftOrder = edgeNarrativeOrder(left);
    const rightOrder = edgeNarrativeOrder(right);
    const leftRank = leftOrder === null ? 10 ** 9 : leftOrder;
    const rightRank = rightOrder === null ? 10 ** 9 : rightOrder;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    const leftTime = String(left && left.created_at ? left.created_at : "");
    const rightTime = String(right && right.created_at ? right.created_at : "");
    if (leftTime !== rightTime) {
      return leftTime.localeCompare(rightTime);
    }
    return String(left && left.id ? left.id : "").localeCompare(String(right && right.id ? right.id : ""));
  }

  function clampZoom(value, minZoom, maxZoom) {
    const normalized = Math.round(Number(value || 0) * 100) / 100;
    const min = Number.isFinite(minZoom) ? minZoom : 0.4;
    const max = Number.isFinite(maxZoom) ? maxZoom : 2.4;
    return Math.min(max, Math.max(min, normalized));
  }

  function nodeMetadataObject(node) {
    if (!node || !node.metadata || typeof node.metadata !== "object" || Array.isArray(node.metadata)) {
      return {};
    }
    return Object.assign({}, node.metadata);
  }

  function readGroupBinding(metadata) {
    const source = metadata && typeof metadata === "object" ? metadata : {};
    const rawBinding = source.group_binding;
    const rawParent = source.group_parent_id;
    return {
      binding: rawBinding === "bound" ? "bound" : "independent",
      parentId: typeof rawParent === "string" ? rawParent.trim() : ""
    };
  }

  function applyGroupBinding(metadata, binding, parentId) {
    const next = Object.assign({}, metadata);
    if (binding === "bound" && parentId) {
      next.group_binding = "bound";
      next.group_parent_id = parentId;
    } else {
      next.group_binding = "independent";
      delete next.group_parent_id;
    }
    return next;
  }

  function sceneRenderSizeByMetadata(metadata, options) {
    const opts = options || {};
    const asNumber = opts.asNumber;
    const nodeMinWidth = Number.isFinite(opts.nodeMinWidth) ? opts.nodeMinWidth : 160;
    const nodeMinHeight = Number.isFinite(opts.nodeMinHeight) ? opts.nodeMinHeight : 86;
    const nodeWidth = Number.isFinite(opts.nodeWidth) ? opts.nodeWidth : 224;
    const nodeHeight = Number.isFinite(opts.nodeHeight) ? opts.nodeHeight : 120;
    const parse = typeof asNumber === "function"
      ? asNumber
      : function (input, fallbackValue) {
          const parsed = Number(input);
          return Number.isFinite(parsed) ? parsed : fallbackValue;
        };
    const source = metadata && typeof metadata === "object" ? metadata : {};
    return {
      width: Math.max(nodeMinWidth, parse(source.node_width, nodeWidth)),
      height: Math.max(nodeMinHeight, parse(source.node_height, nodeHeight))
    };
  }

  function groupRenderSizeByMetadata(metadata, options) {
    const opts = options || {};
    const asNumber = opts.asNumber;
    const groupMinWidth = Number.isFinite(opts.groupMinWidth) ? opts.groupMinWidth : 403;
    const groupMinHeight = Number.isFinite(opts.groupMinHeight) ? opts.groupMinHeight : 192;
    const parse = typeof asNumber === "function"
      ? asNumber
      : function (input, fallbackValue) {
          const parsed = Number(input);
          return Number.isFinite(parsed) ? parsed : fallbackValue;
        };
    const source = metadata && typeof metadata === "object" ? metadata : {};
    return {
      width: Math.max(groupMinWidth, parse(source.group_width, 820)),
      height: Math.max(groupMinHeight, parse(source.group_height, 460))
    };
  }

  function findContainingGroupId(node, allNodes, options) {
    if (!node || node.type === "group") {
      return "";
    }
    const opts = options || {};
    const asNumber = typeof opts.asNumber === "function"
      ? opts.asNumber
      : function (input, fallbackValue) {
          const parsed = Number(input);
          return Number.isFinite(parsed) ? parsed : fallbackValue;
        };
    const metadataOf = typeof opts.nodeMetadataObject === "function" ? opts.nodeMetadataObject : nodeMetadataObject;
    const groupSizeOf = typeof opts.groupRenderSizeByMetadata === "function" ? opts.groupRenderSizeByMetadata : groupRenderSizeByMetadata;
    const nodeSizeOf = typeof opts.nodeRenderSize === "function" ? opts.nodeRenderSize : function () {
      return { width: 0, height: 0 };
    };

    const nodeSize = nodeSizeOf(node);
    const nodeCenterX = asNumber(node.pos_x, 0) + nodeSize.width / 2;
    const nodeCenterY = asNumber(node.pos_y, 0) + nodeSize.height / 2;
    const groups = (allNodes || [])
      .filter(function (item) {
        return item.type === "group" && item.id !== node.id;
      })
      .sort(function (left, right) {
        const leftMeta = metadataOf(left);
        const rightMeta = metadataOf(right);
        const leftSize = groupSizeOf(leftMeta);
        const rightSize = groupSizeOf(rightMeta);
        return rightSize.width * rightSize.height - leftSize.width * leftSize.height;
      });
    for (let index = 0; index < groups.length; index += 1) {
      const group = groups[index];
      const groupMeta = metadataOf(group);
      const size = groupSizeOf(groupMeta);
      const left = asNumber(group.pos_x, 0);
      const top = asNumber(group.pos_y, 0);
      if (
        nodeCenterX >= left &&
        nodeCenterX <= left + size.width &&
        nodeCenterY >= top &&
        nodeCenterY <= top + size.height
      ) {
        return group.id;
      }
    }
    return "";
  }

  window.ElyhaWebGraphUtils = {
    rectAnchor: rectAnchor,
    cubicMidpoint: cubicMidpoint,
    edgeNarrativeOrder: edgeNarrativeOrder,
    edgeDisplayLabel: edgeDisplayLabel,
    compareEdgesByNarrativeOrder: compareEdgesByNarrativeOrder,
    clampZoom: clampZoom,
    nodeMetadataObject: nodeMetadataObject,
    readGroupBinding: readGroupBinding,
    applyGroupBinding: applyGroupBinding,
    sceneRenderSizeByMetadata: sceneRenderSizeByMetadata,
    groupRenderSizeByMetadata: groupRenderSizeByMetadata,
    findContainingGroupId: findContainingGroupId
  };
})();
