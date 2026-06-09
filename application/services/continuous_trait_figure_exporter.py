import math
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path


class ContinuousTraitPublicationFigureExporter:
    """Export a paper-style multi-panel summary for continuous-trait ASR."""

    def export(self, result, file_path: str, method_name: str = "") -> None:
        if result is None or type(result).__name__ != "ContinuousTraitResult":
            raise ValueError("Publication-style continuous figure is only available for continuous-trait results.")

        if self._should_force_subprocess():
            self._export_in_subprocess(result, file_path, method_name, None)
            return

        try:
            plt, np, LinearSegmentedColormap = self._import_plotting_dependencies()
        except Exception as exc:
            if not self._is_subprocess_export():
                self._export_in_subprocess(result, file_path, method_name, exc)
                return
            raise self._plotting_import_error(exc) from exc

        tree_image = self._render_tree_image(result)
        trait_name = str(getattr(result, "trait_name", "") or "Trait")
        method_label = str(method_name or getattr(result, "model_name", "") or "Continuous ASR")
        plot_scale = str(getattr(result, "trait_plot_scale", "analysis") or "analysis")
        display_scale = str(getattr(result, "trait_display_scale", "analysis") or "analysis")
        transform = str(getattr(result, "trait_transform", "none") or "none")
        analysis_scale_label = self._scale_label(plot_scale, transform)
        display_scale_label = self._display_axis_label(display_scale, transform)

        fig = plt.figure(figsize=(14.5, 9.2), dpi=220)
        gs = fig.add_gridspec(
            3,
            2,
            height_ratios=[0.16, 2.88, 1.12],
            width_ratios=[1.35, 1.0],
            left=0.06,
            right=0.975,
            top=0.965,
            bottom=0.075,
            hspace=0.24,
            wspace=0.16,
        )

        ax_title = fig.add_subplot(gs[0, :])
        ax_tree = fig.add_subplot(gs[1, :])
        ax_scatter = fig.add_subplot(gs[2, 0])
        ax_dist = fig.add_subplot(gs[2, 1])

        self._draw_title_panel(ax_title, method_label, trait_name, analysis_scale_label, display_scale_label)
        self._draw_tree_panel(ax_tree, tree_image)
        self._draw_colorbar(ax_tree, result, trait_name, plot_scale, display_scale, transform, LinearSegmentedColormap, np)
        self._draw_tip_time_panel(ax_scatter, result, trait_name, plot_scale, display_scale, transform, display_scale_label, np)
        self._draw_distribution_panel(ax_dist, result, trait_name, plot_scale, display_scale, transform, display_scale_label, np)

        fig.savefig(str(file_path), dpi=220, bbox_inches="tight", pad_inches=0.08)
        plt.close(fig)

    def _import_plotting_dependencies(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.image as _mpimg  # noqa: F401
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.colors import LinearSegmentedColormap
        return plt, np, LinearSegmentedColormap

    def _plotting_import_error(self, exc: Exception) -> RuntimeError:
        return RuntimeError(
            "matplotlib/numpy are required to export the publication-style figure. "
            "Import error: %s" % exc
        )

    def _is_subprocess_export(self) -> bool:
        return bool(os.environ.get("RASP_CONTINUOUS_EXPORT_CHILD"))

    def _should_force_subprocess(self) -> bool:
        return bool(os.environ.get("RASP_CONTINUOUS_EXPORT_FORCE_SUBPROCESS")) and not self._is_subprocess_export()

    def _export_in_subprocess(self, result, file_path: str, method_name: str, import_error) -> None:
        project_root = Path(__file__).resolve().parents[2]
        tmp = tempfile.NamedTemporaryFile(prefix="rasp_continuous_export_", suffix=".pkl", delete=False)
        tmp_path = tmp.name
        try:
            with tmp:
                pickle.dump(result, tmp, protocol=pickle.HIGHEST_PROTOCOL)

            script = (
                "import os, pickle, sys\n"
                "from pathlib import Path\n"
                "project_root = Path(sys.argv[1])\n"
                "pickle_path = sys.argv[2]\n"
                "output_path = sys.argv[3]\n"
                "method_name = sys.argv[4]\n"
                "sys.path.insert(0, str(project_root))\n"
                "from app.bootstrap import ApplicationBootstrap\n"
                "bootstrap = ApplicationBootstrap()\n"
                "bootstrap.inject_conda_dll_paths()\n"
                "bootstrap.inject_vendor_packages()\n"
                "os.environ['RASP_CONTINUOUS_EXPORT_CHILD'] = '1'\n"
                "from application.services.continuous_trait_figure_exporter import ContinuousTraitPublicationFigureExporter\n"
                "with open(pickle_path, 'rb') as handle:\n"
                "    result = pickle.load(handle)\n"
                "ContinuousTraitPublicationFigureExporter().export(result, output_path, method_name=method_name)\n"
            )
            env = self._clean_export_subprocess_env()
            env["RASP_CONTINUOUS_EXPORT_CHILD"] = "1"
            env.pop("RASP_CONTINUOUS_EXPORT_FORCE_SUBPROCESS", None)
            completed = subprocess.run(
                [sys.executable, "-c", script, str(project_root), tmp_path, str(file_path), str(method_name or "")],
                cwd=str(project_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            if completed.returncode != 0:
                detail_parts = []
                if import_error is not None:
                    detail_parts.append("GUI import error: %s" % import_error)
                if completed.stderr:
                    detail_parts.append("Subprocess stderr: %s" % completed.stderr.strip())
                if completed.stdout:
                    detail_parts.append("Subprocess stdout: %s" % completed.stdout.strip())
                detail = "\n".join(detail_parts) or "continuous figure export subprocess failed"
                raise RuntimeError(detail)
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            detail = "GUI import error: %s\nSubprocess export failed: %s" % (import_error, exc)
            raise RuntimeError(detail) from exc
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def _clean_export_subprocess_env(self) -> dict:
        env = dict(os.environ)
        prefix = Path(sys.prefix)
        blocked = {
            str(prefix / "Library" / "bin").lower(),
        }
        path_parts = []
        for part in str(env.get("PATH", "") or "").split(os.pathsep):
            if not part:
                continue
            try:
                normalised = str(Path(part)).lower()
            except Exception:
                normalised = str(part).lower()
            if normalised in blocked:
                continue
            path_parts.append(part)
        dlls = str(prefix / "DLLs")
        if Path(dlls).exists() and dlls not in path_parts:
            path_parts.insert(0, dlls)
        env["PATH"] = os.pathsep.join(path_parts)
        return env

    def _render_tree_image(self, result):
        from visualization.renderers.continuous_trait_result_renderer import ContinuousTraitResultRenderer

        renderer = ContinuousTraitResultRenderer()
        renderer.set_tree(getattr(result, "reference_tree", None))
        renderer.set_result(result)
        renderer.set_circular_enabled(True)
        renderer.set_circular_arc(205, 130)

        tmp = tempfile.NamedTemporaryFile(prefix="rasp_continuous_tree_", suffix=".png", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            renderer.export_tree_png(tmp_path)
            import matplotlib.image as mpimg
            return self._crop_image(mpimg.imread(tmp_path))
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    def _crop_image(self, image):
        try:
            import numpy as np
        except Exception:
            return image
        arr = np.asarray(image)
        if arr.ndim < 2:
            return image
        if arr.ndim == 2:
            mask = arr < 0.98
        else:
            rgb = arr[:, :, :3]
            mask = np.any(rgb < 0.97, axis=2)
            if arr.shape[2] >= 4:
                mask = mask | (arr[:, :, 3] < 0.98)
        if not mask.any():
            return image
        ys, xs = np.where(mask)
        pad = 18
        y0 = max(0, int(ys.min()) - pad)
        y1 = min(arr.shape[0], int(ys.max()) + pad + 1)
        x0 = max(0, int(xs.min()) - pad)
        x1 = min(arr.shape[1], int(xs.max()) + pad + 1)
        if y1 <= y0 or x1 <= x0:
            return image
        return arr[y0:y1, x0:x1]

    def _draw_title_panel(self, ax, method_label, trait_name, analysis_scale_label, display_scale_label):
        ax.set_axis_off()
        ax.text(0.0, 0.5, "A", transform=ax.transAxes, fontsize=16, fontweight="bold", va="center", ha="left")
        ax.text(
            0.035,
            0.5,
            "%s: ancestral state reconstruction of %s (%s analysis; labels %s)"
            % (method_label, trait_name, analysis_scale_label, display_scale_label),
            transform=ax.transAxes,
            fontsize=9.5,
            va="center",
            ha="left",
            color="#222222",
        )

    def _draw_tree_panel(self, ax, image):
        ax.imshow(image)
        ax.set_anchor("C")
        ax.set_axis_off()

    def _draw_colorbar(self, ax, result, trait_name, plot_scale, display_scale, transform, cmap_factory, np):
        colors = self._palette_colors(result)
        cmap = cmap_factory.from_list("rasp_continuous_trait", colors)
        vmin = float(getattr(result, "color_scale_min", 0.0) or 0.0)
        vmax = float(getattr(result, "color_scale_max", vmin + 1.0) or (vmin + 1.0))
        if vmax <= vmin:
            vmax = vmin + 1.0
        cax = ax.inset_axes([0.735, 0.08, 0.18, 0.05], transform=ax.transAxes)
        cax.set_facecolor((1.0, 1.0, 1.0, 0.86))
        gradient = np.linspace(0.0, 1.0, 256).reshape(1, -1)
        cax.imshow(gradient, aspect="auto", cmap=cmap)
        cax.set_yticks([])
        tick_positions = [0, 128, 255]
        tick_values = [vmin, (vmin + vmax) / 2.0, vmax]
        tick_labels = [
            self._format_value(self._display_value(value, plot_scale, display_scale, transform))
            for value in tick_values
        ]
        cax.set_xticks(tick_positions)
        cax.set_xticklabels(tick_labels, fontsize=7)
        cax.set_title("%s" % trait_name, fontsize=7, pad=1)
        for spine in cax.spines.values():
            spine.set_visible(True)
            spine.set_color("#ffffff")

    def _draw_tip_time_panel(self, ax, result, trait_name, plot_scale, display_scale, transform, display_scale_label, np):
        if self._draw_publication_time_panel(ax, result, trait_name, plot_scale, display_scale, transform, np):
            return

        rows = self._tip_depth_value_rows(result)
        ax.text(-0.08, 1.02, "B", transform=ax.transAxes, fontsize=16, fontweight="bold", va="bottom")
        if not rows:
            ax.text(0.5, 0.5, "No tip values", ha="center", va="center")
            ax.set_axis_off()
            return

        xs = np.array([row[0] for row in rows], dtype=float)
        ys = np.array([row[1] for row in rows], dtype=float)
        colors = [row[2] for row in rows]
        ax.scatter(xs, ys, s=18, c=colors, edgecolors="none", alpha=0.78, label="Tips")

        show_binned_trend = bool(
            getattr(result, "model_statistics", {}).get("show_binned_tip_trend", False)
        )
        if show_binned_trend and len(xs) >= 6:
            order = np.argsort(xs)
            xs_sorted = xs[order]
            ys_sorted = ys[order]
            bins = min(14, max(5, int(math.sqrt(len(xs)))))
            edges = np.linspace(float(xs_sorted.min()), float(xs_sorted.max()), bins + 1)
            cx = []
            cy = []
            lo = []
            hi = []
            for start, end in zip(edges[:-1], edges[1:]):
                mask = (xs_sorted >= start) & (xs_sorted <= end)
                if not mask.any():
                    continue
                values = ys_sorted[mask]
                cx.append((start + end) / 2.0)
                cy.append(float(np.mean(values)))
                lo.append(float(np.percentile(values, 10)))
                hi.append(float(np.percentile(values, 90)))
            if cx:
                ax.plot(cx, cy, color="#c95768", linewidth=2.2, label="Binned mean")
                ax.fill_between(cx, lo, hi, color="#c95768", alpha=0.16, linewidth=0)

        ax.set_xlabel("Root-to-tip distance")
        ax.set_ylabel(self._axis_title(trait_name, display_scale, transform))
        self._set_display_axis_ticks(ax, "y", ys, plot_scale, display_scale, transform)
        self._disable_axis_offset(ax)
        ax.grid(True, color="#e3e3e3", linewidth=0.6)
        ax.tick_params(labelsize=8)
        ax.legend(frameon=False, loc="best", fontsize=7)

    def _draw_publication_time_panel(self, ax, result, trait_name, plot_scale, display_scale, transform, np):
        time_series = self._figure_time_series(result)
        occurrences = self._figure_occurrences(result, plot_scale)
        if not time_series and not occurrences:
            return False

        ax.text(-0.08, 1.02, "B", transform=ax.transAxes, fontsize=16, fontweight="bold", va="bottom")
        self._draw_time_bands(ax, result)

        occurrence_values = []
        if occurrences:
            palette = self._group_palette(result)
            seen_groups = set()
            for row in occurrences:
                age = row.get("age")
                value = row.get("value")
                if not self._is_finite(age) or not self._is_finite(value):
                    continue
                group = str(row.get("group", "") or "Occurrences")
                color = palette.get(group, "#6d6ab1")
                label = self._pretty_group_label(group) if group not in seen_groups else None
                seen_groups.add(group)
                ax.scatter(
                    [float(age)],
                    [float(value)],
                    s=16,
                    c=[color],
                    edgecolors="white",
                    linewidths=0.25,
                    alpha=0.78,
                    label=label,
                    zorder=3,
                )
                occurrence_values.append(float(value))

        plotted_primary = False
        if time_series:
            xs = np.array(time_series.get("x", []) or [], dtype=float)
            ys = np.array(time_series.get("y", []) or [], dtype=float)
            clean = np.isfinite(xs) & np.isfinite(ys)
            xs = xs[clean]
            ys = ys[clean]
            lower = self._series_array(time_series.get("lower"), clean, np)
            upper = self._series_array(time_series.get("upper"), clean, np)
            if xs.size > 0 and ys.size > 0:
                if occurrences:
                    ax2 = ax.twinx()
                    target_ax = ax2
                    color = str(time_series.get("color", "") or "#c95768")
                    label = str(time_series.get("label", "") or "Gradual split disparity")
                    target_ax.set_ylabel(str(time_series.get("y_label", "") or "Disparity"), fontsize=8, color=color)
                    target_ax.tick_params(axis="y", labelsize=8, colors=color)
                    for spine in target_ax.spines.values():
                        spine.set_edgecolor("#dddddd")
                else:
                    target_ax = ax
                    color = str(time_series.get("color", "") or "#c95768")
                    label = str(time_series.get("label", "") or "Gradual split")
                    plotted_primary = True
                target_ax.plot(xs, ys, color=color, linewidth=2.1, label=label, zorder=4)
                if lower is not None and upper is not None and lower.size == ys.size and upper.size == ys.size:
                    target_ax.fill_between(xs, lower, upper, color=color, alpha=0.16, linewidth=0, zorder=2)
                limits = self._time_series_axis_limits(time_series, ys, lower, upper)
                if limits is not None:
                    target_ax.set_ylim(limits[0], limits[1])
                if occurrences:
                    lines, labels = target_ax.get_legend_handles_labels()
                    if lines:
                        ax.legend(lines, labels, frameon=False, loc="upper right", fontsize=7)

        x_values = []
        x_values.extend([float(row.get("age")) for row in occurrences if self._is_finite(row.get("age"))])
        if time_series:
            x_values.extend([float(v) for v in time_series.get("x", []) or [] if self._is_finite(v)])
        if x_values:
            xmin = min(x_values)
            xmax = max(x_values)
            pad = (xmax - xmin) * 0.025 if xmax > xmin else 1.0
            ax.set_xlim(xmax + pad, xmin - pad)

        ax.set_xlabel(str((time_series or {}).get("x_label", "") or "Age (Ma)"))
        if occurrences:
            ax.set_ylabel(self._axis_title(trait_name, display_scale, transform))
            self._set_display_axis_ticks(ax, "y", occurrence_values, plot_scale, display_scale, transform)
        elif plotted_primary:
            ax.set_ylabel(str((time_series or {}).get("y_label", "") or "Value"))
        ax.grid(True, color="#e3e3e3", linewidth=0.6)
        ax.tick_params(labelsize=8)
        self._disable_axis_offset(ax)
        if occurrences:
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(handles, labels, frameon=False, loc="upper left", fontsize=7)
        return True

    def _draw_time_bands(self, ax, result):
        bands = self._figure_time_bands(result)
        for band in bands:
            start = band.get("start")
            end = band.get("end")
            if not self._is_finite(start) or not self._is_finite(end):
                continue
            color = str(band.get("color", "") or "#dddddd")
            alpha = float(band.get("alpha", 0.16) or 0.16)
            ax.axvspan(float(start), float(end), color=color, alpha=alpha, linewidth=0, zorder=0)
            label = str(band.get("label", "") or "").strip()
            if label:
                midpoint = (float(start) + float(end)) / 2.0
                ax.text(
                    midpoint,
                    0.02,
                    label,
                    transform=ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    fontsize=6.5,
                    color="#666666",
                    zorder=5,
                )

    def _series_array(self, values, clean_mask, np):
        if values is None:
            return None
        try:
            arr = np.array(values, dtype=float)
        except Exception:
            return None
        if arr.size != clean_mask.size:
            return None
        arr = arr[clean_mask]
        if not np.isfinite(arr).all():
            return None
        return arr

    def _time_series_axis_limits(self, time_series, ys, lower, upper):
        explicit = self._explicit_axis_limits(time_series)
        if explicit is not None:
            return explicit

        values = [float(value) for value in list(ys) if self._is_finite(value)]
        if lower is not None:
            values.extend([float(value) for value in list(lower) if self._is_finite(value)])
        if upper is not None:
            values.extend([float(value) for value in list(upper) if self._is_finite(value)])
        if not values:
            return None

        y_label = str(time_series.get("y_label", "") or "").lower()
        label = str(time_series.get("label", "") or "").lower()
        kind = str(time_series.get("kind", time_series.get("type", "")) or "").lower()
        if "disparity" in y_label or "disparity" in label or "disparity" in kind:
            ymax = max(values)
            if ymax <= 0.0:
                return (0.0, 1.0)
            return (0.0, self._nice_positive_axis_max(ymax))
        return None

    def _explicit_axis_limits(self, time_series):
        for key in ("y_limits", "y_range", "axis_limits", "range"):
            raw = time_series.get(key)
            if isinstance(raw, (list, tuple)) and len(raw) >= 2:
                low = raw[0]
                high = raw[1]
                if self._is_finite(low) and self._is_finite(high) and float(high) > float(low):
                    return (float(low), float(high))

        low = self._first_finite_value(
            time_series,
            ("y_min", "ymin", "axis_min", "y_axis_min", "range_min", "lower_limit"),
        )
        high = self._first_finite_value(
            time_series,
            ("y_max", "ymax", "axis_max", "y_axis_max", "range_max", "upper_limit"),
        )
        if low is not None and high is not None and high > low:
            return (low, high)
        return None

    def _first_finite_value(self, data, keys):
        for key in keys:
            value = data.get(key)
            if self._is_finite(value):
                return float(value)
        return None

    def _nice_positive_axis_max(self, value):
        value = float(value)
        for candidate in (0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0):
            if value <= candidate:
                return candidate
        exponent = math.floor(math.log10(value))
        base = 10.0 ** exponent
        for multiplier in (1.0, 2.0, 5.0, 10.0):
            candidate = multiplier * base
            if value <= candidate:
                return candidate
        return value * 1.05

    def _draw_distribution_panel(self, ax, result, trait_name, plot_scale, display_scale, transform, display_scale_label, np):
        if self._draw_grouped_distribution_panel(ax, result, trait_name, plot_scale, display_scale, transform, np):
            return

        ax.text(-0.08, 1.02, "C", transform=ax.transAxes, fontsize=16, fontweight="bold", va="bottom")
        tip_values = list(self._plot_tip_values(result).values())
        node_values = list(self._plot_node_values(result).values())
        series = [
            ("Tip values", tip_values, "#6d6ab1"),
            ("Internal nodes", node_values, "#e07a5f"),
        ]
        all_values = [float(v) for _, values, _ in series for v in values if self._is_finite(v)]
        if not all_values:
            ax.text(0.5, 0.5, "No values", ha="center", va="center")
            ax.set_axis_off()
            return

        xmin = min(all_values)
        xmax = max(all_values)
        if xmax <= xmin:
            xmax = xmin + 1.0
        bins = np.linspace(xmin, xmax, 36)
        y_offsets = [1.0, 0.0]
        for (label, values, color), offset in zip(series, y_offsets):
            clean = np.array([float(v) for v in values if self._is_finite(v)], dtype=float)
            if clean.size <= 0:
                continue
            hist, edges = np.histogram(clean, bins=bins, density=True)
            hist = self._smooth(hist, np)
            if hist.max() > 0:
                hist = hist / hist.max() * 0.62
            centers = (edges[:-1] + edges[1:]) / 2.0
            ax.fill_between(centers, offset, offset + hist, color=color, alpha=0.68, linewidth=0)
            ax.plot(centers, offset + hist, color=color, linewidth=1.2)
            ax.text(xmin, offset + 0.08, label, fontsize=8, ha="left", va="bottom", color="#333333")
            median = float(np.median(clean))
            ax.plot([median, median], [offset, offset + 0.55], color=color, linewidth=1.0, alpha=0.9)

        ax.set_xlabel(self._axis_title(trait_name, display_scale, transform))
        self._set_display_axis_ticks(ax, "x", all_values, plot_scale, display_scale, transform)
        ax.set_yticks([])
        ax.grid(True, axis="x", color="#e5e5e5", linewidth=0.6)
        ax.tick_params(labelsize=8)
        self._disable_axis_offset(ax)
        ax.set_ylim(-0.05, 1.78)

    def _draw_grouped_distribution_panel(self, ax, result, trait_name, plot_scale, display_scale, transform, np):
        groups = self._figure_group_values(result)
        if not groups:
            return False
        ax.text(-0.08, 1.02, "C", transform=ax.transAxes, fontsize=16, fontweight="bold", va="bottom")

        order = self._figure_group_order(result, groups)
        palette = self._group_palette(result)
        all_values = []
        clean_groups = []
        for group in order:
            clean = [float(v) for v in groups.get(group, []) if self._is_finite(v)]
            if not clean:
                continue
            clean_groups.append((group, clean))
            all_values.extend(clean)
        if not clean_groups or not all_values:
            ax.text(0.5, 0.5, "No grouped values", ha="center", va="center")
            ax.set_axis_off()
            return True

        xmin = min(all_values)
        xmax = max(all_values)
        if xmax <= xmin:
            xmax = xmin + 1.0
        xpad = (xmax - xmin) * 0.12
        label_x = xmin - xpad * 0.82
        bins = np.linspace(xmin, xmax, 42)
        spacing = 0.82
        for index, (group, values) in enumerate(reversed(clean_groups)):
            offset = index * spacing
            color = palette.get(group, "#6d6ab1")
            arr = np.array(values, dtype=float)
            hist, edges = np.histogram(arr, bins=bins, density=True)
            hist = self._smooth(hist, np)
            if hist.max() > 0:
                hist = hist / hist.max() * 0.62
            centers = (edges[:-1] + edges[1:]) / 2.0
            ax.fill_between(centers, offset, offset + hist, color=color, alpha=0.70, linewidth=0)
            ax.plot(centers, offset + hist, color=color, linewidth=1.1)
            ax.text(
                label_x,
                offset + 0.07,
                self._pretty_group_label(group),
                fontsize=7,
                ha="left",
                va="bottom",
                color="#333333",
                clip_on=False,
            )
            median = float(np.median(arr))
            ax.plot([median, median], [offset, offset + 0.52], color=color, linewidth=0.9, alpha=0.85)

        ax.set_xlabel(self._axis_title(trait_name, display_scale, transform))
        self._set_display_axis_ticks(ax, "x", all_values, plot_scale, display_scale, transform)
        ax.set_yticks([])
        ax.grid(True, axis="x", color="#e5e5e5", linewidth=0.6)
        ax.tick_params(labelsize=8)
        ax.set_xlim(xmin - xpad, xmax + xpad)
        self._disable_axis_offset(ax)
        ax.set_ylim(-0.18, max(0.9, (len(clean_groups) - 1) * spacing + 0.86))
        return True

    def _disable_axis_offset(self, ax) -> None:
        try:
            ax.ticklabel_format(axis="both", style="plain", useOffset=False)
        except Exception:
            pass
        try:
            ax.xaxis.get_major_formatter().set_useOffset(False)
            ax.yaxis.get_major_formatter().set_useOffset(False)
        except Exception:
            pass

    def _set_display_axis_ticks(self, ax, axis, values, plot_scale, display_scale, transform):
        if values is None:
            values = []
        clean = [float(value) for value in list(values) if self._is_finite(value)]
        if not clean:
            return
        if display_scale == plot_scale:
            return
        vmin = min(clean)
        vmax = max(clean)
        if vmax <= vmin:
            return
        ticks = self._nice_analysis_ticks(vmin, vmax, transform)
        if not ticks:
            ticks = [vmin, (vmin + vmax) / 2.0, vmax]
        labels = [
            self._format_value(self._display_value(value, plot_scale, display_scale, transform))
            for value in ticks
        ]
        if axis == "x":
            ax.set_xticks(ticks)
            ax.set_xticklabels(labels)
        else:
            ax.set_yticks(ticks)
            ax.set_yticklabels(labels)

    def _nice_analysis_ticks(self, vmin, vmax, transform):
        if transform == "log10":
            start = int(math.floor(vmin))
            end = int(math.ceil(vmax))
            ticks = [float(power) for power in range(start, end + 1) if vmin <= float(power) <= vmax]
            if len(ticks) >= 2:
                return ticks
        if transform == "log":
            start = int(math.floor(vmin))
            end = int(math.ceil(vmax))
            ticks = [float(power) for power in range(start, end + 1) if vmin <= float(power) <= vmax]
            if len(ticks) >= 2:
                return ticks
        count = 4
        return [vmin + (vmax - vmin) * i / float(count - 1) for i in range(count)]

    def _figure_time_series(self, result):
        data = self._metadata_value(result, "figure_time_series", "publication_time_series", "publication_disparity")
        if not isinstance(data, dict):
            return {}
        x_values = self._list_from_keys(data, ["x", "time", "times", "age", "ages"])
        y_values = self._list_from_keys(data, ["y", "median", "value", "values", "disparity"])
        if not x_values or not y_values:
            return {}
        length = min(len(x_values), len(y_values))
        if length <= 0:
            return {}
        output = dict(data)
        clean_indices = [
            index for index in range(length)
            if self._is_finite(x_values[index]) and self._is_finite(y_values[index])
        ]
        output["x"] = [float(x_values[index]) for index in clean_indices]
        output["y"] = [float(y_values[index]) for index in clean_indices]
        for key in ["lower", "upper"]:
            values = self._list_from_keys(data, [key, key + "95", key + "_95", key + "_ci"])
            if values and len(values) >= length:
                aligned = [values[index] for index in clean_indices]
                if aligned and all(self._is_finite(value) for value in aligned):
                    output[key] = [float(value) for value in aligned]
        return output if output["x"] and output["y"] else {}

    def _figure_occurrences(self, result, plot_scale):
        rows = self._metadata_value(result, "figure_occurrences", "publication_occurrences")
        if not isinstance(rows, (list, tuple)):
            rows = []
        output = []
        tip_values = self._plot_tip_values(result)
        groups = self._figure_taxon_groups(result)
        for row in rows:
            if not isinstance(row, dict):
                continue
            taxon = str(row.get("taxon", row.get("name", "")) or "").strip()
            age = row.get("age", row.get("time", row.get("midpoint")))
            value = row.get("value")
            if value is None and taxon in tip_values:
                value = tip_values[taxon]
            if not self._is_finite(age) or not self._is_finite(value):
                continue
            output.append({
                "taxon": taxon,
                "age": float(age),
                "value": float(value),
                "group": str(row.get("group", "") or groups.get(taxon, "") or "Occurrences"),
            })
        if output:
            return output

        # If only taxon group metadata exists, build occurrence-like points from
        # optional taxon ages. This keeps the API forgiving for imported datasets.
        ages = self._metadata_value(result, "figure_taxon_ages", "publication_taxon_ages")
        if not isinstance(ages, dict):
            return []
        for taxon, value in tip_values.items():
            age = ages.get(taxon)
            if not self._is_finite(age):
                continue
            output.append({
                "taxon": taxon,
                "age": float(age),
                "value": float(value),
                "group": str(groups.get(taxon, "") or "Occurrences"),
            })
        return output

    def _figure_time_bands(self, result):
        bands = self._metadata_value(result, "figure_time_bands", "publication_time_bands")
        return list(bands) if isinstance(bands, (list, tuple)) else []

    def _figure_group_values(self, result):
        explicit_groups = self._figure_groups(result)
        if explicit_groups:
            values = self._plot_tip_values(result)
            output = {}
            for group in explicit_groups:
                if group.get("show_in_distribution") is False:
                    continue
                name = str(group.get("name", "") or "").strip()
                if not name:
                    continue
                taxa = self._group_taxa(group)
                clean = []
                for taxon in taxa:
                    if taxon in values and self._is_finite(values[taxon]):
                        clean.append(float(values[taxon]))
                if clean:
                    output[name] = clean
            if output:
                return output

        groups = self._metadata_value(result, "figure_group_values", "publication_group_values")
        if isinstance(groups, dict) and groups:
            return {
                str(group): [float(v) for v in values if self._is_finite(v)]
                for group, values in groups.items()
                if isinstance(values, (list, tuple))
            }
        taxon_groups = self._figure_taxon_groups(result)
        if not taxon_groups:
            return {}
        values = self._plot_tip_values(result)
        output = {}
        for taxon, group in taxon_groups.items():
            if taxon not in values:
                continue
            output.setdefault(str(group), []).append(float(values[taxon]))
        return output

    def _figure_taxon_groups(self, result):
        explicit_groups = self._figure_groups(result)
        if explicit_groups:
            output = {}
            for group in explicit_groups:
                if group.get("show_in_distribution") is False:
                    continue
                name = str(group.get("name", "") or "").strip()
                if not name:
                    continue
                for taxon in self._group_taxa(group):
                    output.setdefault(str(taxon), name)
            if output:
                return output

        groups = self._metadata_value(result, "figure_taxon_groups", "publication_taxon_groups")
        if not isinstance(groups, dict):
            return {}
        return {
            str(taxon).strip(): str(group).strip()
            for taxon, group in groups.items()
            if str(taxon).strip() and str(group).strip()
        }

    def _figure_group_order(self, result, groups):
        explicit_groups = self._figure_groups(result)
        if explicit_groups:
            cleaned = []
            for group in explicit_groups:
                if group.get("show_in_distribution") is False:
                    continue
                name = str(group.get("name", "") or "").strip()
                if name and name in groups and name not in cleaned:
                    cleaned.append(name)
            for group in groups.keys():
                if group not in cleaned:
                    cleaned.append(group)
            if cleaned:
                return cleaned

        order = self._metadata_value(result, "figure_group_order", "publication_group_order")
        if isinstance(order, (list, tuple)):
            cleaned = [str(item) for item in order if str(item) in groups]
            for group in groups.keys():
                if group not in cleaned:
                    cleaned.append(group)
            return cleaned
        return self._standardised_group_order(list(groups.keys()))

    def _group_palette(self, result):
        raw = self._metadata_value(result, "figure_group_colors", "publication_group_colors")
        if isinstance(raw, dict):
            colors = {str(k): str(v) for k, v in raw.items() if str(v).strip()}
        else:
            colors = {}
        for group in self._figure_groups(result):
            name = str(group.get("name", "") or "").strip()
            color = str(group.get("color", "") or "").strip()
            if name and color:
                colors[name] = color
        fallback = ["#6d6ab1", "#78b7c5", "#88c999", "#e07a5f", "#c95768", "#a17c6b", "#7f7f7f"]
        group_map = {}
        group_map.update(self._figure_group_values(result) or {})
        group_map.update(self._groups_from_occurrences(result) or {})
        groups = self._figure_group_order(result, group_map)
        for index, group in enumerate(groups):
            colors.setdefault(group, self._standard_group_color(group) or fallback[index % len(fallback)])
        return colors

    def _standardised_group_order(self, groups):
        priority = [
            "Amniotes total group",
            "Ancestral regime",
            "Dissorophoidea [Including Amphibamiformes]",
            "Dissorophoidea",
        ]
        output = []
        for name in priority:
            if name in groups and name not in output:
                output.append(name)
        for name in groups:
            if name not in output:
                output.append(name)
        return output

    def _standard_group_color(self, group):
        normalised = str(group or "").strip().lower()
        known = {
            "amniotes total group": "#7b6bb3",
            "ancestral regime": "#60b8e6",
            "dissorophoidea": "#78b97a",
            "dissorophoidea [including amphibamiformes]": "#78b97a",
            "dissorophoidea including amphibamiformes": "#78b97a",
        }
        return known.get(normalised)

    def _groups_from_occurrences(self, result):
        groups = {}
        rows = self._metadata_value(result, "figure_occurrences", "publication_occurrences")
        if isinstance(rows, (list, tuple)):
            for row in rows:
                if isinstance(row, dict):
                    group = str(row.get("group", "") or "Occurrences")
                    groups.setdefault(group, [])
        return groups

    def _figure_groups(self, result):
        groups = self._metadata_value(result, "figure_groups", "publication_groups")
        if not isinstance(groups, (list, tuple)):
            return []
        output = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            name = str(group.get("name", "") or "").strip()
            clade_key = str(group.get("clade_key", "") or "").strip()
            taxa = self._group_taxa(group)
            if not name or (not clade_key and not taxa):
                continue
            cleaned = dict(group)
            cleaned["name"] = name
            cleaned["clade_key"] = clade_key
            cleaned["taxa"] = taxa
            output.append(cleaned)
        return output

    def _group_taxa(self, group):
        taxa = group.get("taxa")
        if not isinstance(taxa, (list, tuple)):
            clade_key = str(group.get("clade_key", "") or "").strip()
            taxa = clade_key.split("|") if clade_key else []
        return [
            str(taxon).strip()
            for taxon in taxa
            if str(taxon).strip()
        ]

    def _metadata_value(self, result, *keys):
        stats = dict(getattr(result, "model_statistics", {}) or {})
        for key in keys:
            if hasattr(result, key):
                value = getattr(result, key)
                if value:
                    return value
            value = stats.get(key)
            if value:
                return value
        return None

    def _list_from_keys(self, data, keys):
        for key in keys:
            value = data.get(key)
            if isinstance(value, (list, tuple)):
                return list(value)
        return []

    def _pretty_group_label(self, group):
        return str(group or "").replace("_", " ")

    def _tip_depth_value_rows(self, result):
        tree = getattr(result, "reference_tree", None)
        values = self._plot_tip_values(result)
        if tree is None or not values:
            return []
        palette = self._value_color_function(result)
        rows = []
        for leaf in self._iter_leaves(tree):
            name = str(getattr(leaf, "name", "") or "").strip()
            if name not in values:
                continue
            depth = self._node_depth(leaf)
            value = float(values[name])
            rows.append((depth, value, palette(value)))
        return rows

    def _plot_tip_values(self, result):
        data = dict(getattr(result, "plot_tip_values", {}) or {}) or dict(getattr(result, "tip_values", {}) or {})
        return {str(k): float(v) for k, v in data.items() if self._is_finite(v)}

    def _plot_node_values(self, result):
        data = dict(getattr(result, "plot_node_values", {}) or {})
        if not data:
            data = {}
            for key, node in dict(getattr(result, "node_results", {}) or {}).items():
                try:
                    data[str(key)] = float(getattr(node, "mean", 0.0) or 0.0)
                except Exception:
                    pass
        return {str(k): float(v) for k, v in data.items() if self._is_finite(v)}

    def _value_color_function(self, result):
        colors = self._palette_colors(result)
        vmin = float(getattr(result, "color_scale_min", 0.0) or 0.0)
        vmax = float(getattr(result, "color_scale_max", vmin + 1.0) or (vmin + 1.0))
        if vmax <= vmin:
            vmax = vmin + 1.0

        def color_for(value):
            t = (float(value) - vmin) / (vmax - vmin)
            t = max(0.0, min(1.0, t))
            scaled = t * (len(colors) - 1)
            idx = int(math.floor(scaled))
            if idx >= len(colors) - 1:
                return colors[-1]
            frac = scaled - idx
            return self._mix_hex(colors[idx], colors[idx + 1], frac)
        return color_for

    def _palette_colors(self, result):
        order = list(getattr(result, "state_order", []) or [])
        color_map = dict(getattr(result, "state_colors", {}) or {})
        colors = [str(color_map.get(label, "") or "").strip() for label in order]
        colors = [color for color in colors if color]
        return colors or ["#440154", "#414487", "#2A788E", "#22A884", "#7AD151", "#FDE725"]

    def _display_value(self, value, plot_scale, display_scale, transform):
        number = float(value)
        if display_scale == plot_scale:
            return number
        if display_scale != "original":
            if plot_scale == "original" and transform == "log" and number > 0.0:
                return math.log(number)
            if plot_scale == "original" and transform == "log10" and number > 0.0:
                return math.log10(number)
            return number
        if plot_scale == "original":
            return number
        try:
            if transform == "log":
                output = math.exp(number)
            elif transform == "log10":
                output = 10.0 ** number
            else:
                output = number
        except (OverflowError, ValueError):
            return float("nan")
        return output if math.isfinite(output) else float("nan")

    def _scale_label(self, scale, transform):
        scale = str(scale or "analysis")
        transform = str(transform or "none")
        if scale == "original" and transform != "none":
            return "original scale"
        if transform == "log":
            return "ln"
        if transform == "log10":
            return "log10"
        return "raw"

    def _display_axis_label(self, display_scale, transform):
        display_scale = str(display_scale or "analysis")
        transform = str(transform or "none")
        if display_scale == "original" and transform != "none":
            return "original scale, back-transformed"
        return self._scale_label("analysis", transform)

    def _axis_title(self, trait_name, display_scale, transform):
        display_scale = str(display_scale or "analysis")
        transform = str(transform or "none")
        if display_scale == "original" and transform != "none":
            return str(trait_name or "Trait")
        return "%s (%s)" % (str(trait_name or "Trait"), self._scale_label("analysis", transform))

    def _format_value(self, value):
        number = float(value)
        if abs(number) >= 1000 or (abs(number) > 0 and abs(number) < 0.01):
            return "%.2g" % number
        return "%.4g" % number

    def _smooth(self, values, np):
        arr = np.array(values, dtype=float)
        if arr.size < 5:
            return arr
        kernel = np.array([1.0, 2.0, 3.0, 2.0, 1.0], dtype=float)
        kernel = kernel / kernel.sum()
        return np.convolve(arr, kernel, mode="same")

    def _node_depth(self, node):
        depth = 0.0
        current = node
        while current is not None:
            try:
                depth += float(getattr(current, "dist", 0.0) or 0.0)
            except Exception:
                pass
            current = getattr(current, "up", None)
        return depth

    def _iter_leaves(self, tree):
        try:
            return list(tree.iter_leaves())
        except Exception:
            try:
                return list(tree.get_leaves())
            except Exception:
                return []

    def _mix_hex(self, left, right, frac):
        l = self._hex_to_rgb(left)
        r = self._hex_to_rgb(right)
        vals = [
            int(round(l[i] * (1.0 - frac) + r[i] * frac))
            for i in range(3)
        ]
        return "#%02x%02x%02x" % tuple(vals)

    def _hex_to_rgb(self, value):
        text = str(value or "#808080").strip()
        if text.startswith("#"):
            text = text[1:]
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        if len(text) != 6:
            return (128, 128, 128)
        try:
            return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return (128, 128, 128)

    def _is_finite(self, value):
        try:
            return math.isfinite(float(value))
        except Exception:
            return False
