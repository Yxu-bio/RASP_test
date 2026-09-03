from dataclasses import dataclass, field
from functools import lru_cache
import re


@dataclass
class RangeStateColorPalette:
    area_order: list = field(default_factory=list)
    area_colors: dict = field(default_factory=dict)
    state_colors: dict = field(default_factory=dict)
    independent_state_colors: dict = field(default_factory=dict)
    biogeobears_state_colors: dict = field(default_factory=dict)
    state_area_members: dict = field(default_factory=dict)


class RangeStateColorMapper:
    """Build composition-aware colors for discrete geographic ranges."""

    AREA_PALETTE = [
        "#e41a1c",
        "#377eb8",
        "#4daf4a",
        "#984ea3",
        "#ff7f00",
        "#ffff33",
        "#a65628",
        "#f781bf",
        "#999999",
        "#66c2a5",
        "#fc8d62",
        "#8da0cb",
        "#e78ac3",
        "#a6d854",
        "#ffd92f",
        "#1b9e77",
        "#d95f02",
        "#7570b3",
        "#e7298a",
        "#66a61e",
    ]
    EMPTY_STATES = {"", "/", "0", "EMPTY", "NONE", "NULL"}
    UNKNOWN_STATES = {"*", "?"}

    @classmethod
    def build(cls, state_order, area_order=None, base_colors=None):
        states = cls._ordered_unique(state_order)
        areas = cls._ordered_unique(area_order)
        if not areas:
            areas = cls._infer_area_order(states)

        preferred = {
            str(key).strip(): str(value).strip()
            for key, value in dict(base_colors or {}).items()
            if str(key).strip() and cls._is_hex_color(value)
        }
        area_colors = {}
        for index, area in enumerate(areas):
            area_colors[area] = preferred.get(
                area,
                cls.AREA_PALETTE[index % len(cls.AREA_PALETTE)],
            )

        state_colors = {}
        state_area_members = {}
        for state in states:
            members = cls.members_for_state(state, areas)
            state_area_members[state] = members
            normalized = state.strip().upper()
            if normalized in cls.EMPTY_STATES:
                state_colors[state] = "#ffffff"
            elif normalized in cls.UNKNOWN_STATES:
                state_colors[state] = "#000000"
            elif len(members) == 1:
                state_colors[state] = area_colors[members[0]]
            elif len(members) > 1:
                state_colors[state] = cls.mix_colors(
                    [area_colors[area] for area in members]
                )
            else:
                state_colors[state] = "#808080"

        independent_state_colors = cls.build_independent_state_colors(states)
        biogeobears_state_colors = cls.build_biogeobears_state_colors(
            states,
            area_order=areas,
            area_colors=area_colors,
        )

        return RangeStateColorPalette(
            area_order=areas,
            area_colors=area_colors,
            state_colors=state_colors,
            independent_state_colors=independent_state_colors,
            biogeobears_state_colors=biogeobears_state_colors,
            state_area_members=state_area_members,
        )

    @classmethod
    def apply_to_result(cls, result, *, state_order=None, area_order=None, base_colors=None):
        states = list(state_order if state_order is not None else getattr(result, "state_order", []) or [])
        areas = list(area_order if area_order is not None else getattr(result, "area_order", []) or [])
        preferred = base_colors
        if preferred is None:
            preferred = dict(getattr(result, "area_colors", {}) or {})
        palette = cls.build(states, area_order=areas, base_colors=preferred)

        result.state_order = list(states)
        result.area_order = list(palette.area_order)
        result.area_colors = dict(palette.area_colors)
        result.state_colors = dict(palette.state_colors)
        existing_independent = dict(
            getattr(result, "independent_state_colors", {}) or {}
        )
        result.independent_state_colors = cls.build_independent_state_colors(
            states,
            base_colors=existing_independent,
        )
        result.biogeobears_state_colors = dict(
            palette.biogeobears_state_colors
        )
        result.state_area_members = {
            state: list(members)
            for state, members in palette.state_area_members.items()
        }

        for node_result in dict(getattr(result, "node_results", {}) or {}).values():
            labels = list(getattr(node_result, "pie_labels", []) or [])
            node_result.pie_colors = [
                result.state_colors.get(label, "#808080")
                for label in labels
            ]
        return palette

    @classmethod
    def build_independent_state_colors(cls, state_order, base_colors=None):
        """Assign each complete range state its own categorical color."""
        preferred = {
            str(key).strip(): str(value).strip()
            for key, value in dict(base_colors or {}).items()
            if str(key).strip() and cls._is_hex_color(value)
        }
        colors = {}
        palette_index = 0
        for state in cls._ordered_unique(state_order):
            normalized = state.strip().upper()
            if state in preferred:
                colors[state] = preferred[state]
            elif normalized in cls.EMPTY_STATES:
                colors[state] = "#ffffff"
            elif normalized in cls.UNKNOWN_STATES:
                colors[state] = "#000000"
            else:
                colors[state] = cls.AREA_PALETTE[
                    palette_index % len(cls.AREA_PALETTE)
                ]
            if normalized not in cls.EMPTY_STATES | cls.UNKNOWN_STATES:
                palette_index += 1
        return colors

    @classmethod
    def build_biogeobears_state_colors(
        cls,
        state_order,
        *,
        area_order,
        area_colors,
    ):
        """Reproduce BioGeoBEARS' solid-color range mixing rule."""
        areas = cls._ordered_unique(area_order)
        base = dict(area_colors or {})
        colors = {}
        for state in cls._ordered_unique(state_order):
            normalized = state.strip().upper()
            members = cls.members_for_state(state, areas)
            if normalized in cls.EMPTY_STATES | cls.UNKNOWN_STATES:
                colors[state] = "#000000"
            elif areas and len(members) == len(areas):
                colors[state] = "#ffffff"
            elif len(members) == 1:
                colors[state] = base.get(members[0], "#808080")
            elif len(members) > 1:
                colors[state] = cls.mix_colors(
                    [base[area] for area in members if area in base]
                )
            else:
                colors[state] = "#808080"
        return colors

    @classmethod
    def members_for_state(cls, state, area_order):
        text = str(state or "").strip()
        areas = cls._ordered_unique(area_order)
        if not text or text.upper() in cls.EMPTY_STATES | cls.UNKNOWN_STATES:
            return []

        canonical = {area.upper(): area for area in areas}
        if text.upper() in canonical:
            return [canonical[text.upper()]]

        tokens = [token for token in re.split(r"[\s_,;|+/]+", text) if token]
        if len(tokens) > 1 and all(token.upper() in canonical for token in tokens):
            present = {canonical[token.upper()] for token in tokens}
            return [area for area in areas if area in present]

        compact = re.sub(r"[\s_,;|+]", "", text)
        members = cls._split_compact_state(compact, areas)
        if members:
            present = set(members)
            return [area for area in areas if area in present]
        return []

    @classmethod
    def segmented_colors(cls, result, state):
        members = list(
            dict(getattr(result, "state_area_members", {}) or {}).get(str(state), [])
        )
        area_colors = dict(getattr(result, "area_colors", {}) or {})
        return [area_colors[area] for area in members if area in area_colors]

    @classmethod
    def mix_colors(cls, colors):
        channels = []
        for color in list(colors or []):
            if not cls._is_hex_color(color):
                continue
            raw = str(color).strip().lstrip("#")
            channels.append(
                (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
            )
        if not channels:
            return "#808080"
        count = float(len(channels))
        return "#%02x%02x%02x" % tuple(
            int(round(sum(value[index] for value in channels) / count))
            for index in range(3)
        )

    @classmethod
    def _split_compact_state(cls, text, area_order):
        compact = str(text or "")
        if not compact:
            return []
        candidates = sorted(
            enumerate(area_order),
            key=lambda item: (-len(item[1]), item[0]),
        )

        @lru_cache(maxsize=None)
        def split_at(position):
            if position == len(compact):
                return ()
            for _index, area in candidates:
                end = position + len(area)
                if compact[position:end].upper() != area.upper():
                    continue
                remainder = split_at(end)
                if remainder is not None:
                    return (area,) + remainder
            return None

        parsed = split_at(0)
        return list(parsed) if parsed else []

    @classmethod
    def _infer_area_order(cls, states):
        inferred = set()
        for state in list(states or []):
            text = str(state or "").strip().upper()
            if text in cls.EMPTY_STATES | cls.UNKNOWN_STATES:
                continue
            compact = re.sub(r"[\s_,;|+/]+", "", text)
            if compact and all(character.isalnum() for character in compact):
                inferred.update(compact)
        return sorted(inferred)

    @staticmethod
    def _ordered_unique(values):
        output = []
        seen = set()
        for value in list(values or []):
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            output.append(text)
        return output

    @staticmethod
    def _is_hex_color(value):
        return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", str(value or "").strip()))
