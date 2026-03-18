"""Read-only project insights built from SQLite graph/content state."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
import json
import re
from typing import Any

from elyha_core.i18n import tr
from elyha_core.storage.repository import SQLiteRepository

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]{1,}|[\u3040-\u30ff\u3400-\u9fff]{2,}")
_SPLIT_RE = re.compile(r"[,，;；、|/\n\r\t]+")
_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "have",
    "has",
    "into",
    "then",
    "than",
    "will",
    "was",
    "were",
    "are",
    "you",
    "your",
    "their",
    "his",
    "her",
    "its",
    "not",
    "but",
    "about",
    "章节",
    "场景",
    "角色",
    "剧情",
    "故事",
    "世界",
    "设定",
    "这里",
    "这个",
    "那个",
    "一个",
    "我们",
    "你们",
    "他们",
    "她们",
    "以及",
    "如果",
    "因为",
    "所以",
    "而且",
    "然后",
    "进行",
    "可以",
    "需要",
    "还是",
    "为了",
    "已经",
    "没有",
    "非常",
    "可能",
    "です",
    "ます",
    "する",
    "した",
    "して",
    "いる",
    "ある",
    "ない",
}


class InsightService:
    """Aggregate analytics and relation graph data for one project."""

    def __init__(self, repository: SQLiteRepository) -> None:
        self.repository = repository

    def build_project_insights(
        self,
        project_id: str,
        *,
        top_words: int = 48,
        top_entities: int = 40,
    ) -> dict[str, Any]:
        project = self.repository.get_project(project_id)
        if project is None:
            raise KeyError(tr("err.project_not_found", project_id=project_id))

        node_rows = self._list_node_rows(project_id)
        edges = self.repository.list_edges(project_id)

        word_counter: Counter[str] = Counter()
        word_nodes: dict[str, set[str]] = defaultdict(set)
        storyline_nodes: dict[str, int] = defaultdict(int)
        storyline_edges: dict[str, int] = defaultdict(int)
        node_storyline: dict[str, str] = {}

        char_counter: Counter[str] = Counter()
        char_nodes: dict[str, set[str]] = defaultdict(set)
        world_counter: Counter[str] = Counter()
        world_nodes: dict[str, set[str]] = defaultdict(set)
        item_counter: Counter[str] = Counter()
        item_nodes: dict[str, set[str]] = defaultdict(set)
        item_owner: dict[str, str] = {}

        relation_counter: Counter[tuple[str, str, str]] = Counter()
        ownership_counter: Counter[tuple[str, str]] = Counter()
        world_char_counter: Counter[tuple[str, str]] = Counter()

        for row in node_rows:
            node_id = str(row["id"])
            storyline_id = self._storyline_key(row["storyline_id"])
            node_storyline[node_id] = storyline_id
            storyline_nodes[storyline_id] += 1
            metadata = self._decode_metadata(row["metadata_json"])
            text_blob = self._compose_text_blob(row, metadata)
            for token in self._tokenize(text_blob):
                word_counter[token] += 1
                word_nodes[token].add(node_id)

            characters = self._extract_characters(metadata)
            worlds = self._extract_world_terms(metadata)
            items, node_owner_pairs = self._extract_items(metadata)

            for name in characters:
                char_counter[name] += 1
                char_nodes[name].add(node_id)

            for term in worlds:
                world_counter[term] += 1
                world_nodes[term].add(node_id)

            for item_name in items:
                item_counter[item_name] += 1
                item_nodes[item_name].add(node_id)

            explicit_relations = self._extract_character_relations(metadata)
            for source, target, label in explicit_relations:
                if source == target:
                    continue
                relation_counter[(source, target, label)] += 1
                char_counter[source] += 1
                char_counter[target] += 1
                char_nodes[source].add(node_id)
                char_nodes[target].add(node_id)

            for left, right in combinations(sorted(characters), 2):
                relation_counter[(left, right, "cooccur")] += 1

            for world in worlds:
                for character in characters:
                    world_char_counter[(world, character)] += 1

            for item_name, owner in node_owner_pairs:
                ownership_counter[(item_name, owner)] += 1
                if owner and item_name:
                    item_owner[item_name] = owner
                if owner:
                    char_counter[owner] += 1
                    char_nodes[owner].add(node_id)

        for row in self._list_relationship_rows(project_id):
            subject = self._normalize_name(row.get("subject_character_id"))
            object_ = self._normalize_name(row.get("object_character_id"))
            relation = self._normalize_name(row.get("relation_type")) or "related"
            if not subject or not object_ or subject == object_:
                continue
            relation_counter[(subject, object_, relation)] += 1
            char_counter[subject] += 1
            char_counter[object_] += 1

        for edge in edges:
            source_storyline = node_storyline.get(edge.source_id, "")
            storyline_edges[source_storyline] += 1

        word_frequency = [
            {
                "term": term,
                "count": count,
                "node_ids": sorted(word_nodes.get(term, set())),
            }
            for term, count in word_counter.most_common(max(1, top_words))
        ]

        storylines = []
        storyline_keys = sorted(set(storyline_nodes.keys()) | set(storyline_edges.keys()))
        for storyline_id in storyline_keys:
            storylines.append(
                {
                    "storyline_id": storyline_id,
                    "node_count": storyline_nodes.get(storyline_id, 0),
                    "edge_count": storyline_edges.get(storyline_id, 0),
                }
            )

        characters = self._pack_entity_rows(char_counter, char_nodes, top_entities)
        worldviews = self._pack_entity_rows(world_counter, world_nodes, top_entities)
        items = self._pack_item_rows(item_counter, item_nodes, item_owner, top_entities)

        relation_graph = self._build_relation_graph(
            char_counter=char_counter,
            char_nodes=char_nodes,
            world_counter=world_counter,
            world_nodes=world_nodes,
            item_counter=item_counter,
            item_nodes=item_nodes,
            relation_counter=relation_counter,
            ownership_counter=ownership_counter,
            world_char_counter=world_char_counter,
            top_entities=top_entities,
        )

        return {
            "project_id": project_id,
            "revision": project.active_revision,
            "read_only_default": True,
            "word_frequency": word_frequency,
            "storylines": storylines,
            "characters": characters,
            "worldviews": worldviews,
            "items": items,
            "relation_graph": relation_graph,
        }

    def _list_node_rows(self, project_id: str) -> list[dict[str, Any]]:
        with self.repository.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT
                    n.id,
                    n.title,
                    n.storyline_id,
                    n.metadata_json,
                    COALESCE(GROUP_CONCAT(c.content, ' '), '') AS chunk_text
                FROM nodes AS n
                LEFT JOIN node_chunks AS c
                    ON c.node_id = n.id
                WHERE n.project_id = ?
                GROUP BY n.id
                ORDER BY n.created_at ASC, n.id ASC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _decode_metadata(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}

    def _list_relationship_rows(self, project_id: str) -> list[dict[str, Any]]:
        with self.repository.store.read_only() as conn:
            rows = conn.execute(
                """
                SELECT subject_character_id, object_character_id, relation_type
                FROM relationship_status
                WHERE project_id = ?
                ORDER BY updated_at DESC, subject_character_id ASC, object_character_id ASC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _compose_text_blob(self, row: dict[str, Any], metadata: dict[str, Any]) -> str:
        parts = [
            str(row.get("title") or ""),
            str(row.get("chunk_text") or ""),
            str(metadata.get("content") or ""),
            str(metadata.get("summary") or ""),
        ]
        return " ".join(part for part in parts if part).strip()

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []
        tokens: list[str] = []
        for match in _TOKEN_RE.finditer(text):
            token = match.group(0).strip().lower()
            if len(token) < 2 or token in _STOP_WORDS:
                continue
            if token.isdigit():
                continue
            tokens.append(token)
        return tokens

    def _extract_characters(self, metadata: dict[str, Any]) -> set[str]:
        values = []
        for key in ("characters", "character_names", "roles", "cast"):
            values.extend(self._extract_name_values(metadata.get(key)))
        return set(values)

    def _extract_world_terms(self, metadata: dict[str, Any]) -> set[str]:
        values = []
        for key in ("worldview", "world", "setting", "lore"):
            values.extend(self._extract_name_values(metadata.get(key)))
        return set(values)

    def _extract_items(self, metadata: dict[str, Any]) -> tuple[set[str], set[tuple[str, str]]]:
        item_names: set[str] = set()
        owner_pairs: set[tuple[str, str]] = set()
        for key in ("items", "inventory", "artifacts"):
            value = metadata.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        normalized = self._normalize_name(item)
                        if normalized:
                            item_names.add(normalized)
                        continue
                    if isinstance(item, dict):
                        name = self._normalize_name(
                            item.get("name") or item.get("title") or item.get("item")
                        )
                        owner = self._normalize_name(item.get("owner") or item.get("holder"))
                        if name:
                            item_names.add(name)
                            if owner:
                                owner_pairs.add((name, owner))
            if isinstance(value, dict):
                for item_name, owner in value.items():
                    name = self._normalize_name(item_name)
                    holder = self._normalize_name(owner)
                    if name:
                        item_names.add(name)
                        if holder:
                            owner_pairs.add((name, holder))
        owner_map = metadata.get("item_owner_map")
        if isinstance(owner_map, dict):
            for item_name, owner in owner_map.items():
                name = self._normalize_name(item_name)
                holder = self._normalize_name(owner)
                if name:
                    item_names.add(name)
                    if holder:
                        owner_pairs.add((name, holder))
        return item_names, owner_pairs

    def _extract_character_relations(self, metadata: dict[str, Any]) -> set[tuple[str, str, str]]:
        relations: set[tuple[str, str, str]] = set()
        for key in ("character_relations", "relations"):
            value = metadata.get(key)
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                source = self._normalize_name(
                    item.get("source") or item.get("from") or item.get("a")
                )
                target = self._normalize_name(
                    item.get("target") or item.get("to") or item.get("b")
                )
                label = self._normalize_name(item.get("type") or item.get("label") or "related")
                if source and target:
                    relations.add((source, target, label or "related"))
        return relations

    def _extract_name_values(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item for item in (self._normalize_name(part) for part in _SPLIT_RE.split(value)) if item]
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                if isinstance(item, str):
                    normalized = self._normalize_name(item)
                    if normalized:
                        result.append(normalized)
                    continue
                if isinstance(item, dict):
                    normalized = self._normalize_name(
                        item.get("name") or item.get("title") or item.get("label")
                    )
                    if normalized:
                        result.append(normalized)
            return result
        if isinstance(value, dict):
            result = []
            for key, nested in value.items():
                normalized_key = self._normalize_name(key)
                if normalized_key:
                    result.append(normalized_key)
                if isinstance(nested, str):
                    normalized_nested = self._normalize_name(nested)
                    if normalized_nested:
                        result.append(normalized_nested)
            return result
        return []

    def _normalize_name(self, raw: Any) -> str:
        if raw is None:
            return ""
        text = str(raw).strip()
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text[:120]

    def _storyline_key(self, value: Any) -> str:
        raw = str(value or "").strip()
        return raw

    def _pack_entity_rows(
        self,
        counter: Counter[str],
        node_map: dict[str, set[str]],
        limit: int,
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "count": count,
                "node_ids": sorted(node_map.get(name, set())),
            }
            for name, count in counter.most_common(max(1, limit))
        ]

    def _pack_item_rows(
        self,
        counter: Counter[str],
        node_map: dict[str, set[str]],
        owners: dict[str, str],
        limit: int,
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "owner": owners.get(name, ""),
                "count": count,
                "node_ids": sorted(node_map.get(name, set())),
            }
            for name, count in counter.most_common(max(1, limit))
        ]

    def _build_relation_graph(
        self,
        *,
        char_counter: Counter[str],
        char_nodes: dict[str, set[str]],
        world_counter: Counter[str],
        world_nodes: dict[str, set[str]],
        item_counter: Counter[str],
        item_nodes: dict[str, set[str]],
        relation_counter: Counter[tuple[str, str, str]],
        ownership_counter: Counter[tuple[str, str]],
        world_char_counter: Counter[tuple[str, str]],
        top_entities: int,
    ) -> dict[str, Any]:
        graph_nodes: dict[str, dict[str, Any]] = {}
        graph_edges: list[dict[str, Any]] = []

        top_characters = {name for name, _ in char_counter.most_common(max(1, top_entities))}
        top_worlds = {name for name, _ in world_counter.most_common(max(1, top_entities))}
        top_items = {name for name, _ in item_counter.most_common(max(1, top_entities))}

        def add_node(entity_type: str, name: str, weight: int, node_ids: set[str]) -> str:
            node_id = f"{entity_type}:{name}"
            if node_id not in graph_nodes:
                graph_nodes[node_id] = {
                    "id": node_id,
                    "type": entity_type,
                    "label": name,
                    "weight": int(weight),
                    "node_ids": sorted(node_ids),
                }
            return node_id

        for name in top_characters:
            add_node("character", name, char_counter[name], char_nodes.get(name, set()))
        for name in top_worlds:
            add_node("world", name, world_counter[name], world_nodes.get(name, set()))
        for name in top_items:
            add_node("item", name, item_counter[name], item_nodes.get(name, set()))

        def has_node(entity_type: str, name: str) -> bool:
            return f"{entity_type}:{name}" in graph_nodes

        for (source, target, label), count in relation_counter.most_common(max(1, top_entities * 3)):
            if not (has_node("character", source) and has_node("character", target)):
                continue
            graph_edges.append(
                {
                    "source": f"character:{source}",
                    "target": f"character:{target}",
                    "relation": label,
                    "weight": int(count),
                }
            )

        for (item_name, owner), count in ownership_counter.most_common(max(1, top_entities * 3)):
            if not (has_node("item", item_name) and has_node("character", owner)):
                continue
            graph_edges.append(
                {
                    "source": f"item:{item_name}",
                    "target": f"character:{owner}",
                    "relation": "owned_by",
                    "weight": int(count),
                }
            )

        for (world_name, character), count in world_char_counter.most_common(max(1, top_entities * 3)):
            if not (has_node("world", world_name) and has_node("character", character)):
                continue
            graph_edges.append(
                {
                    "source": f"world:{world_name}",
                    "target": f"character:{character}",
                    "relation": "appears_in",
                    "weight": int(count),
                }
            )

        return {
            "nodes": sorted(graph_nodes.values(), key=lambda item: (item["type"], item["label"])),
            "edges": graph_edges,
        }
