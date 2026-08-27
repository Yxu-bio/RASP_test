import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects as pe
from matplotlib.patches import Polygon


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "runs" / "biogeobears" / "dore_bsm_1000" / "fig2b_reproduction"
GEOJSON = ROOT / "data" / "benchmarks" / "dore_ponerinae" / "Ponerinae_7_bioregions.geojson"
EDGES_CSV = RUN_DIR / "fig2b_dispersal_edges.csv"
NODES_CSV = RUN_DIR / "fig2b_node_richness.csv"
OUT_PNG = RUN_DIR / "current_bsm_network_map_dore_schematic_soft_nodes_v3.png"


REGION_BY_NAME = {
    "Nearctic": "R",
    "Neotropics": "N",
    "Afrotropics": "A",
    "Western Palearctic": "W",
    "Eastern Palearctic": "E",
    "Indomalaya": "I",
    "Australasia": "U",
}
COLORS = {
    "R": "#f3e84a",
    "N": "#f0a202",
    "A": "#245fc6",
    "W": "#315fbf",
    "E": "#e84a4a",
    "I": "#24c943",
    "U": "#7fdbe2",
}
NODE_POS = {
    "R": (-105, 39),
    "N": (-61, -25),
    "A": (22, -1),
    "W": (18, 48),
    "E": (91, 50),
    "I": (90, 17),
    "U": (124, -29),
}
LABEL_POS = {
    "R": (-122, 41),
    "N": (-78, -45),
    "A": (16, -45),
    "W": (-6, 43),
    "E": (116, 57),
    "I": (127, 14),
    "U": (147, -37),
}
ROUTES = {
    ("I", "U"): [(90, 17), (86, 2), (104, -18), (124, -29), 0.60, 15],
    ("I", "E"): [(90, 17), (96, 31), (92, 43), (91, 50), 0.63, -14],
    ("U", "I"): [(124, -29), (139, -9), (115, 8), (90, 17), 0.52, 15],
    ("A", "I"): [(22, -1), (44, 6), (67, 14), (90, 17), 0.64, -13],
    ("N", "R"): [(-61, -25), (-86, -6), (-96, 22), (-105, 39), 0.45, -14],
    ("N", "I"): [(-61, -25), (-28, 35), (50, 36), (90, 17), 0.65, 15],
    ("A", "U"): [(22, -1), (55, -34), (91, -40), (124, -29), 0.59, -15],
    ("I", "A"): [(90, 17), (73, 8), (48, 2), (22, -1), 0.50, 13],
    ("N", "A"): [(-61, -25), (-39, -12), (-8, -7), (22, -1), 0.45, 12],
    ("I", "N"): [(90, 17), (54, 42), (-16, 34), (-61, -25), 0.41, -15],
    ("N", "U"): [(-61, -25), (-20, -50), (81, -51), (124, -29), 0.70, -15],
    ("A", "N"): [(22, -1), (0, -16), (-34, -22), (-61, -25), 0.49, -13],
    ("A", "W"): [(22, -1), (19, 17), (15, 36), (18, 48), 0.55, -13],
    ("U", "E"): [(124, -29), (132, 10), (114, 39), (91, 50), 0.61, 14],
    ("I", "W"): [(90, 17), (72, 36), (43, 47), (18, 48), 0.55, 13],
    ("U", "A"): [(124, -29), (90, -35), (55, -20), (22, -1), 0.55, 14],
}


def read_inputs():
    with GEOJSON.open("r", encoding="utf-8") as handle:
        geojson = json.load(handle)
    with EDGES_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        edges = []
        for row in csv.DictReader(handle):
            row["mean_per_map"] = float(row["mean_per_map"])
            if row["mean_per_map"] >= 5:
                edges.append(row)
    with NODES_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        nodes = {
            row["area"]: {"name": row["name"], "richness": float(row["richness"])}
            for row in csv.DictReader(handle)
        }
    return geojson, edges, nodes


def fallback_route(source, target):
    p0 = np.array(NODE_POS[source], dtype=float)
    p3 = np.array(NODE_POS[target], dtype=float)
    middle = (p0 + p3) / 2
    delta = p3 - p0
    length = np.linalg.norm(delta) or 1.0
    normal = np.array([-delta[1], delta[0]]) / length
    bend = 22 if source < target else -22
    p1 = p0 + (middle - p0) * 0.65 + normal * bend
    p2 = p3 + (middle - p3) * 0.65 + normal * bend
    return [tuple(p0), tuple(p1), tuple(p2), tuple(p3), 0.52, 13]


def bezier(points, t):
    p0, p1, p2, p3 = [np.array(point, dtype=float) for point in points[:4]]
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3


def text_color(hex_color):
    import matplotlib.colors as mc

    r, g, b = mc.to_rgb(hex_color)
    return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 0.56 else "white"


def draw_map(ax, geojson):
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        code = REGION_BY_NAME.get(props.get("display_name") or props.get("name"), "")
        color = COLORS.get(code, props.get("color") or "#dddddd")
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "Polygon":
            polygons = [geometry.get("coordinates") or []]
        elif geometry.get("type") == "MultiPolygon":
            polygons = geometry.get("coordinates") or []
        else:
            polygons = []
        for polygon in polygons:
            if not polygon or len(polygon[0]) < 3:
                continue
            ax.add_patch(
                Polygon(
                    np.asarray(polygon[0], dtype=float),
                    closed=True,
                    facecolor=color,
                    edgecolor="#222222",
                    linewidth=0.34,
                    alpha=0.47,
                    zorder=0,
                )
            )
            for hole in polygon[1:]:
                if len(hole) >= 3:
                    ax.add_patch(
                        Polygon(
                            np.asarray(hole, dtype=float),
                            closed=True,
                            facecolor="#f8f9f7",
                            edgecolor="none",
                            zorder=0.1,
                        )
                    )


def render():
    geojson, edges, nodes = read_inputs()
    figure, ax = plt.subplots(figsize=(16, 7.7), dpi=180)
    figure.subplots_adjust(top=0.88, left=0.01, right=0.995, bottom=0.02)
    figure.suptitle(
        "BSM dispersal network preview, separated schematic lanes\n"
        "Dore 7 bioregions, DEC+J BSM 1000 maps, threshold mean_per_map >= 5",
        fontsize=15,
        weight="bold",
        y=0.985,
    )
    ax.set_facecolor("#f8f9f7")
    draw_map(ax, geojson)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-62, 78)
    ax.set_aspect("equal")
    ax.axis("off")

    figure.canvas.draw()
    transform = ax.transData
    inverse = ax.transData.inverted()
    max_mean = max(edge["mean_per_map"] for edge in edges) or 1.0
    max_richness = max(node["richness"] for node in nodes.values()) or 1.0
    node_radius_px = {
        code: 13 + 24 * math.sqrt(node["richness"] / max_richness)
        for code, node in nodes.items()
    }

    def sample_curve(points, n=260):
        ts = np.linspace(0, 1, n)
        return ts, np.vstack([bezier(points, t) for t in ts])

    def clip_points(points, target):
        ts, sampled = sample_curve(points)
        target_px = transform.transform(np.array(points[3], dtype=float))
        sampled_px = transform.transform(sampled)
        radius = node_radius_px.get(target, 22) + 8
        distance = np.sqrt(((sampled_px - target_px) ** 2).sum(axis=1))
        indexes = np.where(distance > radius)[0]
        index = indexes[-1] if len(indexes) else len(sampled) - 3
        index = max(3, min(index, len(sampled) - 1))
        return ts[: index + 1], sampled[: index + 1]

    def split_line_and_arrow(points, width):
        if len(points) < 4:
            return points, None
        points_px = transform.transform(points)
        head_length = max(18.0, 4.4 * width)
        distance = 0.0
        tip_px = points_px[-1]
        for index in range(len(points_px) - 1, 0, -1):
            current_px = points_px[index]
            previous_px = points_px[index - 1]
            segment = current_px - previous_px
            segment_length = np.linalg.norm(segment)
            if segment_length < 1e-6:
                continue
            if distance + segment_length >= head_length:
                remaining = head_length - distance
                fraction_from_current = remaining / segment_length
                base_px = current_px - segment * fraction_from_current
                base_data = inverse.transform(base_px)
                line_points = np.vstack([points[:index], base_data])
                return line_points, (base_px, tip_px)
            distance += segment_length
        base_px = points_px[0]
        return np.vstack([inverse.transform(base_px), points[-1]]), (base_px, tip_px)

    def draw_arrow_head(arrow_geometry, color, width):
        if arrow_geometry is None:
            return
        base_px, tip_px = arrow_geometry
        direction = tip_px - base_px
        length = np.linalg.norm(direction)
        if length < 1e-6:
            return
        unit = direction / length
        normal = np.array([-unit[1], unit[0]])
        head_width = max(13.0, 2.8 * width)
        triangle = inverse.transform(
            np.vstack(
                [
                    tip_px,
                    base_px + normal * head_width * 0.5,
                    base_px - normal * head_width * 0.5,
                ]
            )
        )
        ax.add_patch(
            Polygon(
                triangle,
                closed=True,
                facecolor=color,
                edgecolor="none",
                linewidth=0,
                alpha=0.98,
                zorder=12,
            )
        )

    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        points = ROUTES.get((source, target), fallback_route(source, target))
        _ts, sampled = clip_points(points, target)
        color = COLORS.get(source, "#6699cc")
        mean = edge["mean_per_map"]
        width = 1.6 + 8.0 * math.sqrt(mean / max_mean)
        line_points, arrow_geometry = split_line_and_arrow(sampled, width)
        ax.plot(
            line_points[:, 0],
            line_points[:, 1],
            color="white",
            linewidth=width + 1.5,
            alpha=0.34,
            solid_capstyle="butt",
            zorder=4,
        )
        ax.plot(
            line_points[:, 0],
            line_points[:, 1],
            color=color,
            linewidth=width,
            alpha=0.86,
            solid_capstyle="butt",
            zorder=5,
            path_effects=[
                pe.Stroke(linewidth=width + 0.9, foreground=(0, 0, 0, 0.13)),
                pe.Normal(),
            ],
        )
        draw_arrow_head(arrow_geometry, color, width)

        index = max(1, min(len(sampled) - 2, int(points[4] * (len(sampled) - 1))))
        tangent = transform.transform(sampled[index + 1]) - transform.transform(sampled[index - 1])
        tangent_length = np.linalg.norm(tangent) or 1.0
        normal = np.array([-tangent[1], tangent[0]]) / tangent_length
        label_xy = inverse.transform(transform.transform(sampled[index]) + normal * float(points[5]))
        ax.text(
            label_xy[0],
            label_xy[1],
            str(int(round(mean))),
            ha="center",
            va="center",
            fontsize=8.5,
            weight="bold",
            color=text_color(color),
            zorder=11,
            bbox=dict(boxstyle="round,pad=0.13", facecolor=color, edgecolor="none", alpha=0.94),
        )

    for code, node in nodes.items():
        x, y = NODE_POS[code]
        radius_points = node_radius_px[code] * 72.0 / figure.dpi
        size = math.pi * radius_points * radius_points
        ax.scatter(
            [x],
            [y],
            s=size,
            color=COLORS.get(code, "#cccccc"),
            alpha=0.43,
            edgecolor=(0, 0, 0, 0.45),
            linewidth=1.2,
            zorder=12,
        )
        ax.text(
            x,
            y,
            str(int(round(node["richness"]))),
            ha="center",
            va="center",
            fontsize=11,
            weight="bold",
            color="black",
            zorder=14,
        )

    for code, (x, y) in LABEL_POS.items():
        node = nodes[code]
        ax.text(
            x,
            y + 2.6,
            code,
            ha="center",
            va="center",
            fontsize=8,
            weight="bold",
            color="#222222",
            zorder=15,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.72, pad=0.45),
        )
        ax.text(
            x,
            y - 0.5,
            node["name"],
            ha="center",
            va="center",
            fontsize=8.6,
            weight="bold",
            color="#222222",
            zorder=15,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.72, pad=0.45),
        )

    ax.text(-170, -36, "Dispersal events", fontsize=10, weight="bold", color="#333333")
    for y, value in [(-44, 5), (-50, 25), (-57, 75)]:
        width = 1.6 + 8 * math.sqrt(value / max_mean)
        ax.annotate(
            "",
            xy=(-145, y),
            xytext=(-170, y),
            arrowprops=dict(arrowstyle="-|>", lw=width, color="#555555", shrinkA=0, shrinkB=0),
            zorder=20,
        )
        ax.text(-137, y, str(value), fontsize=9.3, va="center")
    ax.text(
        -170,
        -65,
        "Node number = species richness\n"
        "Arrow color = source bioregion\n"
        "Edge labels = mean events/map, rounded",
        fontsize=8,
        color="#444444",
        va="top",
    )

    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(str(OUT_PNG), dpi=180, bbox_inches="tight", pad_inches=0.08)
    print(OUT_PNG)


if __name__ == "__main__":
    render()
