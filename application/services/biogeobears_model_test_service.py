import json
import math

from domain.models.biogeobears_model_test_result import (
    BioGeoBEARSModelTestResult,
    BioGeoBEARSModelTestLRTEntry,
    BioGeoBEARSModelTestRow,
)


class BioGeoBEARSModelTestService:
    MODEL_NAMES = [
        "DEC",
        "DECJ",
        "DIVALIKE",
        "DIVALIKEJ",
        "BAYAREALIKE",
        "BAYAREALIKEJ",
    ]

    DISPLAY_NAMES = {
        "DEC": "BioGeoBEARS-DEC",
        "DECJ": "BioGeoBEARS-DEC+J",
        "DIVALIKE": "BioGeoBEARS-DIVALIKE",
        "DIVALIKEJ": "BioGeoBEARS-DIVALIKE+J",
        "BAYAREALIKE": "BioGeoBEARS-BAYAREALIKE",
        "BAYAREALIKEJ": "BioGeoBEARS-BAYAREALIKE+J",
    }

    def __init__(self, biogeobears_service):
        self.biogeobears_service = biogeobears_service

    def analyze(
        self,
        *,
        tree,
        matrix,
        config,
        run_name_prefix="bgb_model_test",
        progress_callback=None,
    ):
        if config is None:
            raise ValueError("BioGeoBEARS model-test config is required.")

        config_kwargs = config.engine_kwargs()
        max_range_size = config_kwargs["max_range_size"]
        include_null_range = config_kwargs["include_null_range"]
        null_range_mode = config_kwargs["null_range_mode"]
        cores = config_kwargs["cores"]
        include_ranges = config_kwargs["include_ranges"]
        exclude_ranges = config_kwargs["exclude_ranges"]
        period_times = config_kwargs["period_times"]
        time_matrix_kind = config_kwargs["time_matrix_kind"]
        period_matrices = config_kwargs["period_matrices"]
        root_age = config_kwargs["root_age"]
        test_j_models = config_kwargs["test_j_models"]

        model_names = self._model_names_for_test(test_j_models)

        result = BioGeoBEARSModelTestResult()
        result.result_note = (
            "BioGeoBEARS model test: %s. Models are run in one Rscript batch, "
            "matching legacy RASP model-test execution."
        ) % ", ".join([self.DISPLAY_NAMES.get(name, name) for name in model_names])

        run_files_by_model = {}
        for model_name in model_names:
            run_files_by_model[model_name] = self.biogeobears_service.build_run_files(
                tree=tree,
                matrix=matrix,
                model_name=model_name,
                run_name="%s_%s" % (run_name_prefix, model_name.lower()),
                max_range_size=max_range_size,
                include_null_range=include_null_range,
                null_range_mode=null_range_mode,
                cores=cores,
                include_ranges=include_ranges,
                exclude_ranges=exclude_ranges,
                period_times=period_times,
                time_matrix_kind=time_matrix_kind,
                period_matrices=period_matrices,
                root_age=root_age,
                scale_tree_to_root_age=True,
            )
            output_path = run_files_by_model[model_name].output_json_path
            if output_path.exists():
                output_path.unlink()

        completed = [0]

        def on_batch_progress(job_id, status, message):
            completed[0] += 1
            if progress_callback is not None:
                progress_callback(
                    completed[0],
                    len(model_names),
                    "%s %s %s" % (job_id, status, message or ""),
                )

        batch_workdir = self.biogeobears_service.work_root / ("%s_batch" % run_name_prefix)
        batch_output = self.biogeobears_service.run_batch(
            [run_files_by_model[model_name] for model_name in model_names],
            batch_workdir=batch_workdir,
            batch_name=run_name_prefix,
            job_ids=model_names,
            progress_callback=on_batch_progress,
        )

        result.result_note += " batch_workdir=%s" % batch_workdir
        failure_messages = self._read_batch_failures(getattr(batch_output, "summary_path", None))

        for model_name in model_names:
            display_name = self.DISPLAY_NAMES.get(model_name, model_name)
            if not bool(include_null_range):
                display_name = "%s (no null range)" % display_name
            row = BioGeoBEARSModelTestRow(
                model_name=model_name,
                display_name=display_name,
            )

            try:
                run_files = run_files_by_model[model_name]
                if model_name in failure_messages and not run_files.output_json_path.exists():
                    raise RuntimeError(failure_messages[model_name])
                model_result = self.biogeobears_service.parse_run_files(
                    tree=tree,
                    run_files=run_files,
                )

                stats = dict(getattr(model_result, "model_statistics", {}) or {})
                log_likelihood = stats.get("log_likelihood", None)
                num_params = stats.get("num_params", None)
                sample_size = stats.get("sample_size", None)

                row.success = True
                row.log_likelihood = float(log_likelihood) if log_likelihood is not None else None
                row.num_params = int(num_params) if num_params is not None else None
                row.sample_size = int(sample_size) if sample_size is not None else None

                row.workdir = self._extract_workdir_from_note(getattr(model_result, "result_note", ""))
                row.output_json_path = str(run_files.output_json_path)
                result.model_results[model_name] = model_result

                self._fill_information_criteria(row)

            except Exception as exc:
                row.success = False
                row.error_message = str(exc)

            result.rows.append(row)

        self._finish_ranking(result)
        self._fill_lrt_tests(result)
        result.teststable_path = str(self._write_teststable(result, batch_workdir))
        return result

    def _model_names_for_test(self, test_j_models):
        if bool(test_j_models):
            return list(self.MODEL_NAMES)
        return ["DEC", "DIVALIKE", "BAYAREALIKE"]

    def _read_batch_failures(self, summary_path):
        if summary_path is None:
            return {}
        try:
            path = str(summary_path)
            data = json.loads(open(path, "r", encoding="utf-8").read())
        except Exception:
            return {}
        out = {}
        for item in list(data.get("failures", []) or []):
            model_name = str(item.get("id", "") or "").strip()
            message = str(item.get("message", "") or "").strip()
            if model_name and message:
                out[model_name] = message
        return out

    def _extract_workdir_from_note(self, text):
        text = str(text or "")
        marker = "workdir="
        if marker not in text:
            return ""
        return text.split(marker, 1)[1].strip()

    def _fill_information_criteria(self, row):
        if row.log_likelihood is None or row.num_params is None:
            return

        k = int(row.num_params)
        ln_l = float(row.log_likelihood)

        row.aic = 2.0 * k - 2.0 * ln_l

        n = row.sample_size
        if n is not None and n > (k + 1):
            row.aicc = row.aic + (2.0 * k * (k + 1.0)) / float(n - k - 1)

    def _finish_ranking(self, result):
        success_rows = [
            row for row in result.rows
            if row.success and row.aic is not None
        ]

        result.effective_model_count = len(success_rows)
        result.failed_model_count = len(result.rows) - len(success_rows)

        if not success_rows:
            result.criterion_used = "AIC"
            result.warnings.append("所有 BioGeoBEARS 模型均未成功完成。")
            return

        min_aic = min(row.aic for row in success_rows)
        for row in success_rows:
            row.delta_aic = row.aic - min_aic

        aicc_rows = [
            row for row in success_rows
            if row.aicc is not None
        ]

        if len(aicc_rows) == len(success_rows):
            result.criterion_used = "AICc"
            min_aicc = min(row.aicc for row in success_rows)
            for row in success_rows:
                row.delta_aicc = row.aicc - min_aicc

            self._fill_weights(success_rows, criterion="aicc")
            best = min(success_rows, key=lambda x: x.aicc)
        else:
            result.criterion_used = "AIC"
            self._fill_weights(success_rows, criterion="aic")
            best = min(success_rows, key=lambda x: x.aic)
            result.warnings.append("部分模型无法计算 AICc，模型权重已基于 AIC 计算。")

        result.best_model_name = best.model_name
        result.best_display_name = best.display_name

    def _fill_weights(self, rows, criterion):
        values = []
        for row in rows:
            value = getattr(row, criterion)
            values.append(float(value))

        min_value = min(values)
        rel_likes = [math.exp(-0.5 * (value - min_value)) for value in values]
        total = sum(rel_likes)

        if total <= 0:
            return

        for row, rel in zip(rows, rel_likes):
            row.weight = rel / total

    def _fill_lrt_tests(self, result):
        row_by_model = {row.model_name: row for row in list(result.rows or [])}
        pairs = [
            ("DECJ", "DEC"),
            ("DIVALIKEJ", "DIVALIKE"),
            ("BAYAREALIKEJ", "BAYAREALIKE"),
        ]

        entries = []
        for alt_name, null_name in pairs:
            alt = row_by_model.get(alt_name)
            null = row_by_model.get(null_name)
            if alt is None or null is None:
                continue

            entry = BioGeoBEARSModelTestLRTEntry(
                alt_model_name=alt_name,
                null_model_name=null_name,
                alt_display_name=alt.display_name,
                null_display_name=null.display_name,
            )

            try:
                if not alt.success:
                    raise RuntimeError("%s failed: %s" % (alt.display_name, alt.error_message))
                if not null.success:
                    raise RuntimeError("%s failed: %s" % (null.display_name, null.error_message))
                if alt.log_likelihood is None or null.log_likelihood is None:
                    raise RuntimeError("Missing log-likelihood for LRT.")
                if alt.num_params is None or null.num_params is None:
                    raise RuntimeError("Missing parameter count for LRT.")

                df = int(alt.num_params) - int(null.num_params)
                if df <= 0:
                    raise RuntimeError("Alternative model does not have more parameters than null model.")

                lrt = 2.0 * (float(alt.log_likelihood) - float(null.log_likelihood))
                if lrt < 0:
                    result.warnings.append(
                        "LRT warning: %s has lower lnL than %s; statistic was clipped to 0."
                        % (alt.display_name, null.display_name)
                    )
                lrt_for_p = max(0.0, lrt)

                entry.success = True
                entry.alt_log_likelihood = float(alt.log_likelihood)
                entry.null_log_likelihood = float(null.log_likelihood)
                entry.alt_num_params = int(alt.num_params)
                entry.null_num_params = int(null.num_params)
                entry.lrt_statistic = lrt
                entry.df = df
                entry.p_value = self._chi_square_survival(lrt_for_p, df)
            except Exception as exc:
                entry.success = False
                entry.error_message = str(exc)

            entries.append(entry)

        result.lrt_entries = entries

    def _chi_square_survival(self, statistic, df):
        statistic = max(0.0, float(statistic))
        df = int(df)
        if df == 1:
            return math.erfc(math.sqrt(statistic / 2.0))

        # The legacy BioGeoBEARS comparisons here are 1 df (+J adds one
        # parameter). Keep a guarded fallback for unexpected future pairs.
        try:
            from scipy.stats import chi2
            return float(chi2.sf(statistic, df))
        except Exception:
            return None

    def _write_teststable(self, result, batch_workdir):
        path = batch_workdir / "teststable.txt"
        lines = [
            "\t".join([
                "alt",
                "null",
                "LnL_alt",
                "LnL_null",
                "numparams_alt",
                "numparams_null",
                "df",
                "LRT",
                "p_value",
                "success",
                "error",
            ])
        ]
        for entry in list(getattr(result, "lrt_entries", []) or []):
            values = [
                entry.alt_display_name,
                entry.null_display_name,
                self._table_float(entry.alt_log_likelihood),
                self._table_float(entry.null_log_likelihood),
                "" if entry.alt_num_params is None else str(entry.alt_num_params),
                "" if entry.null_num_params is None else str(entry.null_num_params),
                "" if entry.df is None else str(entry.df),
                self._table_float(entry.lrt_statistic),
                self._table_float(entry.p_value),
                "TRUE" if entry.success else "FALSE",
                str(entry.error_message or "").replace("\t", " ").replace("\n", " "),
            ]
            lines.append("\t".join(values))

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _table_float(self, value):
        if value is None:
            return ""
        try:
            return "%.10g" % float(value)
        except Exception:
            return ""
