import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping

from domain.models.phytools_config import (
    PhytoolsConfig,
    phytools_ace_model,
    phytools_continuous_model,
    phytools_method_kind,
)

MISSING_TRAIT_TOKENS = {"", "NA", "N/A", "NAN", "?", "-", "NONE", "NULL"}


@dataclass
class PhytoolsRunFiles:
    workdir: Path
    tree_path: Path
    traits_path: Path
    script_path: Path
    output_json_path: Path
    stdout_log_path: Path
    stderr_log_path: Path
    manifest_path: Path
    config: PhytoolsConfig
    taxon_names: List[str]
    trait_values: Dict[str, object]
    original_trait_values: Dict[str, float]
    missing_trait_taxa: List[str]
    node_records: List[Dict[str, object]]


class PhytoolsDatasetBuilder:
    def build(self, *, tree, matrix, config: PhytoolsConfig, output_dir, run_name="phytools_run") -> PhytoolsRunFiles:
        config.validate()
        if tree is None:
            raise ValueError("phytools requires a reference/consensus tree.")
        if matrix is None:
            raise ValueError("phytools requires a trait matrix.")

        workdir = Path(output_dir) / str(run_name or "phytools_run")
        workdir.mkdir(parents=True, exist_ok=True)

        taxon_names = self._leaf_names(tree)
        row_by_name = self._row_by_taxon_name(matrix)
        missing = [name for name in taxon_names if name not in row_by_name]
        if missing:
            raise ValueError("phytools could not find matrix rows for taxa: %s" % ", ".join(sorted(missing)))

        method_kind = phytools_method_kind(config.method)
        method_key = str(config.method or "").upper()
        allow_missing_trait_values = method_key in {
            "ANC_ML_BM",
            "ANC_ML_OU",
            "ANC_ML_EB",
        }
        original_values = {}
        transformed_values = {}
        state_values = {}
        missing_trait_taxa = []
        for name in taxon_names:
            raw = str(row_by_name[name].get(config.trait_column, "") or "").strip()
            if self._is_missing_trait_value(raw):
                if method_kind == "continuous" and allow_missing_trait_values:
                    missing_trait_taxa.append(name)
                    continue
                raise ValueError(
                    "phytools trait column '%s' has an empty/missing value for taxon '%s'. "
                    "fastAnc, anc.Bayes, and ape::ace require complete observed values. "
                    "For continuous missing-tip estimation, use anc.ML (BM/OU/EB)."
                    % (config.trait_column, name)
                )
            if method_kind == "continuous":
                try:
                    value = float(raw)
                except Exception:
                    raise ValueError("phytools trait column '%s' has a non-numeric value for taxon '%s': %s" % (
                        config.trait_column,
                        name,
                        raw,
                    ))
                original_values[name] = value
                transformed_values[name] = self._transform_value(value, config.continuous_transform, name, config.trait_column)
            else:
                state_values[name] = raw

        if method_kind == "continuous" and not transformed_values:
            raise ValueError(
                "phytools trait column '%s' has no observed numeric values after missing-value filtering."
                % config.trait_column
            )
        if method_kind == "discrete" and not state_values:
            raise ValueError(
                "phytools trait column '%s' has no observed state values after missing-value filtering."
                % config.trait_column
            )

        node_records = self.build_node_records(tree)

        tree_path = workdir / "tree.nwk"
        traits_path = workdir / "traits.csv"
        script_path = workdir / "phytools_runner.R"
        output_json_path = workdir / "phytools_result.json"
        stdout_log_path = workdir / "phytools_stdout.log"
        stderr_log_path = workdir / "phytools_stderr.log"
        manifest_path = workdir / "phytools_manifest.json"

        tree_text = self._tree_to_newick(tree)
        tree_path.write_text(tree_text, encoding="utf-8")
        self._write_traits_csv(traits_path, transformed_values if method_kind == "continuous" else state_values)
        script_path.write_text(self._runner_script_text(), encoding="utf-8")

        run_files = PhytoolsRunFiles(
            workdir=workdir,
            tree_path=tree_path,
            traits_path=traits_path,
            script_path=script_path,
            output_json_path=output_json_path,
            stdout_log_path=stdout_log_path,
            stderr_log_path=stderr_log_path,
            manifest_path=manifest_path,
            config=config,
            taxon_names=taxon_names,
            trait_values=transformed_values if method_kind == "continuous" else state_values,
            original_trait_values=original_values,
            missing_trait_taxa=missing_trait_taxa,
            node_records=node_records,
        )
        self._write_manifest(run_files)
        return run_files

    def build_node_records(self, tree) -> List[Dict[str, object]]:
        taxon_count = len(self._leaf_names(tree))
        records = []
        counter = 0
        try:
            iterator = tree.traverse("postorder")
        except TypeError:
            iterator = tree.traverse()
        for node in iterator:
            if node.is_leaf():
                continue
            counter += 1
            leaf_names = [
                str(getattr(leaf, "name", "") or "").strip()
                for leaf in node.iter_leaves()
                if str(getattr(leaf, "name", "") or "").strip()
            ]
            display_id = str(taxon_count + counter)
            records.append({
                "display_node_id": display_id,
                "node_index": counter,
                "clade_key": "|".join(sorted(leaf_names)),
                "leaf_names": leaf_names,
                "terminal_span": self._terminal_span(leaf_names),
                "support": self._node_support_percent(node),
            })
        return records

    def _leaf_names(self, tree) -> List[str]:
        names = []
        for leaf in tree.iter_leaves():
            name = str(getattr(leaf, "name", "") or "").strip()
            if name:
                names.append(name)
        return names

    def _row_by_taxon_name(self, matrix) -> Dict[str, Dict[str, str]]:
        rows = {}
        for row in list(getattr(matrix, "rows", []) or []):
            name = str(row.get("Name", "") or "").strip()
            if name:
                rows[name] = row
        return rows

    def _is_missing_trait_value(self, value) -> bool:
        text = str(value or "").strip()
        return text.upper() in MISSING_TRAIT_TOKENS

    def _transform_value(self, value: float, transform: str, taxon: str, column: str) -> float:
        if transform == "none":
            return float(value)
        if value <= 0:
            raise ValueError(
                "Continuous trait transform '%s' requires positive values, but taxon '%s' has %s in column '%s'."
                % (transform, taxon, value, column)
            )
        if transform == "log":
            return float(math.log(value))
        if transform == "log10":
            return float(math.log10(value))
        raise ValueError("Unsupported continuous transform: %s" % transform)

    def _write_traits_csv(self, path: Path, values: Mapping[str, object]) -> None:
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["taxon", "value"])
            for taxon, value in values.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    out_value = "%.17g" % float(value)
                else:
                    out_value = str(value)
                writer.writerow([taxon, out_value])

    def _tree_to_newick(self, tree) -> str:
        try:
            text = tree.write(format=1)
        except TypeError:
            text = tree.write()
        text = str(text or "").strip()
        if not text.endswith(";"):
            text += ";"
        return text

    def _terminal_span(self, leaf_names: List[str]) -> str:
        if not leaf_names:
            return ""
        return "%s-%s" % (leaf_names[0], leaf_names[-1]) if len(leaf_names) > 1 else leaf_names[0]

    def _node_support_percent(self, node) -> float:
        try:
            support = float(getattr(node, "support", 100.0) or 100.0)
        except Exception:
            support = 100.0
        return support

    def _write_manifest(self, run_files: PhytoolsRunFiles) -> None:
        run_files.manifest_path.write_text(
            json.dumps(
                {
                    "tree": str(run_files.tree_path),
                    "traits": str(run_files.traits_path),
                    "output_json": str(run_files.output_json_path),
                    "method": str(run_files.config.method),
                    "method_kind": phytools_method_kind(run_files.config.method),
                    "ace_model": phytools_ace_model(run_files.config.method),
                    "continuous_model": phytools_continuous_model(run_files.config.method),
                    "trait_column": str(run_files.config.trait_column),
                    "continuous_transform": str(run_files.config.continuous_transform),
                    "missing_trait_taxa": list(run_files.missing_trait_taxa),
                    "anc_ml_maxit": int(run_files.config.anc_ml_maxit),
                    "bayes_iterations": int(run_files.config.bayes_iterations),
                    "bayes_sample_frequency": int(run_files.config.bayes_sample_frequency),
                    "bayes_burnin": int(run_files.config.bayes_burnin),
                    "seed": int(run_files.config.seed),
                    "taxa": list(run_files.taxon_names),
                    "node_count": len(run_files.node_records),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _runner_script_text(self) -> str:
        return r'''
args <- commandArgs(trailingOnly = TRUE)
get_arg <- function(flag) {
  idx <- which(args == flag)
  if (length(idx) == 0 || idx[1] >= length(args)) {
    stop(paste("Missing argument", flag))
  }
  args[idx[1] + 1]
}

tree_path <- get_arg("--tree")
traits_path <- get_arg("--traits")
out_path <- get_arg("--out")
method <- get_arg("--method")
ace_model <- get_arg("--ace_model")
anc_ml_maxit <- as.integer(get_arg("--anc_ml_maxit"))
bayes_ngen <- as.integer(get_arg("--bayes_iterations"))
bayes_sample <- as.integer(get_arg("--bayes_sample_frequency"))
bayes_burnin <- as.integer(get_arg("--bayes_burnin"))
seed <- as.integer(get_arg("--seed"))

if (!requireNamespace("ape", quietly = TRUE)) {
  stop("R package 'ape' is required for phytools analysis.")
}
if (!requireNamespace("phytools", quietly = TRUE)) {
  stop("R package 'phytools' is required for phytools analysis.")
}
if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("R package 'jsonlite' is required for phytools analysis.")
}

tree <- ape::read.tree(tree_path)
traits_df <- read.csv(traits_path, stringsAsFactors = FALSE)
raw_values <- traits_df$value
names(raw_values) <- as.character(traits_df$taxon)

missing <- setdiff(tree$tip.label, names(raw_values))
allow_missing_traits <- method %in% c("ANC_ML_BM", "ANC_ML_OU", "ANC_ML_EB")
if (length(missing) > 0 && !allow_missing_traits) {
  stop(paste("Missing trait values for taxa:", paste(missing, collapse = ", ")))
}
if (allow_missing_traits) {
  raw_values <- raw_values[names(raw_values) %in% tree$tip.label]
} else {
  raw_values <- raw_values[tree$tip.label]
}

descendant_tips <- function(node_id) {
  children <- tree$edge[tree$edge[, 1] == node_id, 2]
  tips <- c()
  for (child in children) {
    if (child <= length(tree$tip.label)) {
      tips <- c(tips, tree$tip.label[child])
    } else {
      tips <- c(tips, descendant_tips(child))
    }
  }
  tips
}

internal_nodes <- seq(length(tree$tip.label) + 1, length(tree$tip.label) + tree$Nnode)

node_summary <- function(samples) {
  samples <- as.numeric(samples)
  samples <- samples[is.finite(samples)]
  if (length(samples) == 0) {
    return(list(
      value = NA_real_,
      mean = NA_real_,
      median = NA_real_,
      lower95 = NA_real_,
      upper95 = NA_real_,
      minimum = NA_real_,
      maximum = NA_real_,
      sample_count = 0L,
      raw_samples = list()
    ))
  }
  qs <- stats::quantile(samples, probs = c(0.025, 0.5, 0.975), names = FALSE, type = 7)
  list(
    value = as.numeric(mean(samples)),
    mean = as.numeric(mean(samples)),
    median = as.numeric(qs[2]),
    lower95 = as.numeric(qs[1]),
    upper95 = as.numeric(qs[3]),
    minimum = as.numeric(min(samples)),
    maximum = as.numeric(max(samples)),
    sample_count = as.integer(length(samples)),
    raw_samples = as.list(samples)
  )
}

fastanc_nodes <- function(anc, include_ci = FALSE) {
  if (include_ci) {
    node_values <- as.numeric(anc$ace)
    names(node_values) <- names(anc$ace)
    node_vars <- as.numeric(anc$var)
    names(node_vars) <- names(anc$var)
    ci <- anc$CI95
  } else {
    node_values <- as.numeric(anc)
    names(node_values) <- names(anc)
    node_vars <- NULL
    ci <- NULL
  }
  nodes <- list()
  for (node_id in internal_nodes) {
    key <- as.character(node_id)
    if (!(key %in% names(node_values))) {
      next
    }
    leaves <- sort(descendant_tips(node_id))
    value <- as.numeric(node_values[key])
    variance <- NA_real_
    lower95 <- value
    upper95 <- value
    if (!is.null(node_vars) && key %in% names(node_vars)) {
      variance <- as.numeric(node_vars[key])
    }
    if (!is.null(ci)) {
      ci_names <- rownames(ci)
      if (!is.null(ci_names) && key %in% ci_names) {
        lower95 <- as.numeric(ci[key, 1])
        upper95 <- as.numeric(ci[key, 2])
      }
    }
    nodes[[length(nodes) + 1]] <- list(
      ape_node = as.integer(node_id),
      clade_key = paste(leaves, collapse = "|"),
      leaf_names = leaves,
      value = value,
      mean = value,
      median = value,
      lower95 = lower95,
      upper95 = upper95,
      minimum = lower95,
      maximum = upper95,
      variance = variance,
      sample_count = as.integer(1),
      raw_samples = list(value)
    )
  }
  nodes
}

if (method %in% c("FASTANC", "FASTANC_CI", "ANC_BAYES", "ANC_ML_BM", "ANC_ML_OU", "ANC_ML_EB")) {
  values <- as.numeric(raw_values)
  names(values) <- names(raw_values)
  if (!allow_missing_traits) {
    bad <- names(values)[!is.finite(values)]
    if (length(bad) > 0) {
      stop(paste("Non-finite trait values for taxa:", paste(bad, collapse = ", ")))
    }
  } else {
    values <- values[is.finite(values)]
  }
  if (method == "FASTANC") {
    anc <- phytools::fastAnc(tree, values)
    nodes <- fastanc_nodes(anc, include_ci = FALSE)
    payload <- list(
      method = "phytools.fastAnc",
      tip_count = length(tree$tip.label),
      internal_node_count = tree$Nnode,
      tip_values = as.list(values),
      nodes = nodes
    )
  } else if (method == "FASTANC_CI") {
    anc <- phytools::fastAnc(tree, values, vars = TRUE, CI = TRUE)
    nodes <- fastanc_nodes(anc, include_ci = TRUE)
    payload <- list(
      method = "phytools.fastAnc.CI95",
      tip_count = length(tree$tip.label),
      internal_node_count = tree$Nnode,
      tip_values = as.list(values),
      nodes = nodes
    )
  } else if (method == "ANC_BAYES") {
    if (seed > 0) {
      set.seed(seed)
    }
    fit <- phytools::anc.Bayes(
      tree,
      values,
      ngen = bayes_ngen,
      control = list(sample = bayes_sample, print = FALSE)
    )
    mcmc <- fit$mcmc
    if (!is.null(mcmc$gen)) {
      mcmc <- mcmc[mcmc$gen >= bayes_burnin, , drop = FALSE]
    }
    nodes <- list()
    for (node_id in internal_nodes) {
      key <- as.character(node_id)
      if (!(key %in% colnames(mcmc))) {
        next
      }
      leaves <- sort(descendant_tips(node_id))
      summary <- node_summary(mcmc[[key]])
      nodes[[length(nodes) + 1]] <- c(
        list(
          ape_node = as.integer(node_id),
          clade_key = paste(leaves, collapse = "|"),
          leaf_names = leaves
        ),
        summary
      )
    }
    payload <- list(
      method = "phytools.anc.Bayes",
      tip_count = length(tree$tip.label),
      internal_node_count = tree$Nnode,
      tip_values = as.list(values),
      bayes_iterations = as.integer(bayes_ngen),
      bayes_sample_frequency = as.integer(bayes_sample),
      bayes_burnin = as.integer(bayes_burnin),
      seed = as.integer(seed),
      nodes = nodes
    )
  } else {
    ml_model <- switch(
      method,
      ANC_ML_BM = "BM",
      ANC_ML_OU = "OU",
      ANC_ML_EB = "EB",
      "BM"
    )
    fit <- phytools::anc.ML(tree, values, maxit = anc_ml_maxit, model = ml_model)
    node_values <- as.numeric(fit$ace)
    names(node_values) <- names(fit$ace)
    nodes <- list()
    for (node_id in internal_nodes) {
      key <- as.character(node_id)
      if (!(key %in% names(node_values))) {
        next
      }
      leaves <- sort(descendant_tips(node_id))
      value <- as.numeric(node_values[key])
      nodes[[length(nodes) + 1]] <- list(
        ape_node = as.integer(node_id),
        clade_key = paste(leaves, collapse = "|"),
        leaf_names = leaves,
        value = value,
        mean = value,
        median = value,
        lower95 = value,
        upper95 = value,
        minimum = value,
        maximum = value,
        sample_count = as.integer(1),
        raw_samples = list(value)
      )
    }
    payload <- list(
      method = paste("phytools.anc.ML", ml_model, sep = "."),
      tip_count = length(tree$tip.label),
      internal_node_count = tree$Nnode,
      tip_values = as.list(values),
      anc_ml_model = ml_model,
      anc_ml_maxit = as.integer(anc_ml_maxit),
      logLik = if (!is.null(fit$logLik)) as.numeric(fit$logLik) else NA_real_,
      convergence = if (!is.null(fit$convergence)) fit$convergence else NA,
      nodes = nodes
    )
  }
} else {
  states <- as.factor(raw_values)
  names(states) <- names(raw_values)
  fit <- ape::ace(states, tree, type = "discrete", model = ace_model)
  lik <- fit$lik.anc
  state_names <- colnames(lik)
  nodes <- list()
  for (row_idx in seq_len(nrow(lik))) {
    node_id <- length(tree$tip.label) + row_idx
    leaves <- sort(descendant_tips(node_id))
    probs <- as.numeric(lik[row_idx, ])
    names(probs) <- state_names
    nodes[[length(nodes) + 1]] <- list(
      ape_node = as.integer(node_id),
      clade_key = paste(leaves, collapse = "|"),
      leaf_names = leaves,
      probabilities = as.list(probs)
    )
  }
  payload <- list(
    method = paste("ape.ace", ace_model, sep = "."),
    tip_count = length(tree$tip.label),
    internal_node_count = tree$Nnode,
    tip_values = as.list(raw_values),
    state_order = as.character(state_names),
    nodes = nodes
  )
}
jsonlite::write_json(payload, out_path, auto_unbox = TRUE, pretty = TRUE, digits = NA)
'''
