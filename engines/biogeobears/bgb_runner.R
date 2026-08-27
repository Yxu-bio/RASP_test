parse_args <- function(args) {
  out <- list()
  i <- 1
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) stop(paste("Invalid arg:", key))
    key <- sub("^--", "", key)
    if (i == length(args)) stop(paste("Missing value for arg:", key))
    out[[key]] <- args[[i + 1]]
    i <- i + 2
  }
  out
}

argv <- parse_args(commandArgs(trailingOnly = TRUE))

if (!is.null(argv[["lib"]]) && nzchar(argv[["lib"]])) {
  private_libs <- strsplit(argv[["lib"]], ";", fixed = TRUE)[[1]]
  private_libs <- private_libs[nzchar(private_libs)]
  private_libs <- vapply(
    private_libs,
    function(path) normalizePath(path, winslash = "/", mustWork = FALSE),
    FUN.VALUE = character(1)
  )
  for (private_lib in private_libs) {
    dir.create(private_lib, recursive = TRUE, showWarnings = FALSE)
  }
  .libPaths(c(private_libs, .Library))
}

suppressPackageStartupMessages(library(BioGeoBEARS))
suppressPackageStartupMessages(library(ape))
suppressPackageStartupMessages(library(jsonlite))

must_get <- function(x, key) {
  if (is.null(x[[key]]) || x[[key]] == "") {
    stop(paste("Missing required argument:", key))
  }
  x[[key]]
}

bool_value <- function(x) {
  lx <- tolower(as.character(x))
  lx %in% c("1", "true", "t", "yes", "y")
}

safe_read_json <- function(path) {
  if (!file.exists(path)) {
    stop(paste("JSON file not found:", path))
  }
  jsonlite::fromJSON(path, simplifyVector = FALSE)
}

extract_candidate <- function(obj, candidates) {
  for (nm in candidates) {
    val <- NULL

    if (is.list(obj) && !is.null(obj[[nm]])) {
      val <- obj[[nm]]
    }

    if (!is.null(val)) {
      return(val)
    }

    if (is.list(obj) && !is.null(obj$outputs) && is.list(obj$outputs) && !is.null(obj$outputs[[nm]])) {
      return(obj$outputs[[nm]])
    }

    if (is.list(obj) && !is.null(obj$inputs) && is.list(obj$inputs) && !is.null(obj$inputs[[nm]])) {
      return(obj$inputs[[nm]])
    }
  }

  NULL
}

unwrap_prob_object <- function(x) {
  if (is.null(x)) {
    return(NULL)
  }

  if (is.matrix(x) || is.data.frame(x)) {
    return(x)
  }

  if (is.list(x)) {
    # 先找直接就是 matrix/data.frame 的子元素
    for (nm in names(x)) {
      cand <- x[[nm]]
      if (is.matrix(cand) || is.data.frame(cand)) {
        return(cand)
      }
    }

    # 再递归找单元素 list
    if (length(x) == 1) {
      return(unwrap_prob_object(x[[1]]))
    }
  }

  x
}

normalize_ids <- function(x) {
  if (is.null(x)) {
    return(NULL)
  }

  out <- as.character(x)
  has_tail_num <- grepl("(\\d+)$", out)
  out[has_tail_num] <- sub("^.*?(\\d+)$", "\\1", out[has_tail_num])
  out
}

format_state_label_from_entry <- function(entry, area_names = NULL) {
  if (is.null(entry)) {
    return("_")
  }

  if (length(entry) == 0) {
    return("_")
  }

  flat_entry <- unlist(entry, use.names = FALSE)
  if (length(flat_entry) > 0 && all(is.na(flat_entry))) {
    return("_")
  }

  if (is.character(entry)) {
    vals <- entry[nzchar(entry)]
    if (length(vals) == 0) {
      return("_")
    }
    return(paste(vals, collapse = ""))
  }

  if (!is.null(area_names) && (is.numeric(entry) || is.integer(entry))) {
    vals <- as.integer(entry)
    vals <- vals[!is.na(vals)]
    if (length(vals) == 0) {
      return("_")
    }
    idx <- vals + 1
    area_names <- as.character(area_names)
    if (all(idx >= 1 & idx <= length(area_names))) {
      return(paste(area_names[idx], collapse = ""))
    }
  }

  if (is.list(entry)) {
    vals <- unlist(entry, use.names = FALSE)
    if (!is.null(area_names)) {
      nums <- suppressWarnings(as.integer(vals))
      if (length(nums) > 0 && !any(is.na(nums))) {
        idx <- nums + 1
        area_names <- as.character(area_names)
        if (all(idx >= 1 & idx <= length(area_names))) {
          return(paste(area_names[idx], collapse = ""))
        }
      }
    }
    vals <- as.character(vals)
    vals <- vals[nzchar(vals)]
    if (length(vals) == 0) {
      return("_")
    }
    return(paste(vals, collapse = ""))
  }

  vals <- as.character(entry)
  vals <- vals[nzchar(vals)]
  if (length(vals) == 0) {
    return("_")
  }
  paste(vals, collapse = "")
}

build_bgb_state_labels <- function(area_names, max_range_size, include_null_range) {
  area_names <- as.character(area_names)
  max_range_size <- min(as.integer(max_range_size), length(area_names))

  out <- character(0)

  if (isTRUE(include_null_range)) {
    out <- c(out, "_")
  }

  if (max_range_size <= 0) {
    return(out)
  }

  for (k in seq_len(max_range_size)) {
    combos <- combn(area_names, k, simplify = FALSE)
    labels <- vapply(combos, function(x) paste(x, collapse = ""), FUN.VALUE = character(1))
    out <- c(out, labels)
  }

  out
}

as_meta_vector <- function(x) {
  if (is.null(x)) {
    return(character(0))
  }
  vals <- as.character(unlist(x, use.names = FALSE))
  vals[vals == "/"] <- "_"
  vals[nzchar(vals)]
}

meta_path <- function(meta, key, base_dir) {
  value <- meta[[key]]
  if (is.null(value) || !nzchar(as.character(value))) {
    return(NULL)
  }
  path <- as.character(value)
  if (!grepl("^([A-Za-z]:)?[/\\\\]", path)) {
    path <- file.path(base_dir, path)
  }
  normalizePath(path, winslash = "/", mustWork = FALSE)
}

file_md5_key <- function(path) {
  if (is.null(path) || !nzchar(as.character(path)) || !file.exists(path)) {
    return("")
  }
  paste(as.character(tools::md5sum(path)), collapse = "")
}

vector_key <- function(x, sort_values = FALSE) {
  values <- as.character(unlist(x, use.names = FALSE))
  values <- values[nzchar(values)]
  if (sort_values) {
    values <- sort(values)
  }
  paste(values, collapse = ",")
}

build_bgb_cache_key <- function(
  model_name,
  treefile,
  geogfile,
  areas_meta,
  areas_base_dir,
  max_range_size,
  include_null_range,
  null_range_mode
) {
  timeperiods_path <- meta_path(areas_meta, "timeperiods_filename", areas_base_dir)
  dispersal_multipliers_path <- meta_path(areas_meta, "dispersal_multipliers_filename", areas_base_dir)
  areas_allowed_path <- meta_path(areas_meta, "areas_allowed_filename", areas_base_dir)
  areas_adjacency_path <- meta_path(areas_meta, "areas_adjacency_filename", areas_base_dir)
  distances_path <- meta_path(areas_meta, "distances_filename", areas_base_dir)

  paste(
    toupper(as.character(model_name)),
    file_md5_key(treefile),
    file_md5_key(geogfile),
    vector_key(areas_meta$area_names),
    as.character(max_range_size),
    as.character(include_null_range),
    as.character(null_range_mode),
    vector_key(areas_meta$include_ranges, sort_values = TRUE),
    vector_key(areas_meta$exclude_ranges, sort_values = TRUE),
    as.character(areas_meta$time_matrix_kind),
    file_md5_key(timeperiods_path),
    file_md5_key(dispersal_multipliers_path),
    file_md5_key(areas_allowed_path),
    file_md5_key(areas_adjacency_path),
    file_md5_key(distances_path),
    sep = "|"
  )
}

range_label_for_state <- function(state, area_names) {
  format_state_label_from_entry(state, area_names = area_names)
}

display_state_label <- function(label) {
  label <- as.character(label)
  if (length(label) == 0 || is.na(label[[1]]) || !nzchar(label[[1]]) || label[[1]] == "_") {
    return("/")
  }
  label[[1]]
}

display_state_labels <- function(labels) {
  if (length(labels) == 0) {
    return(character(0))
  }
  vapply(labels, display_state_label, FUN.VALUE = character(1), USE.NAMES = FALSE)
}

normalize_null_range_mode <- function(mode, requested_include_null_range) {
  if (is.null(mode) || length(mode) == 0 || is.na(mode[[1]])) {
    mode <- ""
  }
  value <- tolower(gsub("[ -]+", "_", as.character(mode[[1]])))
  aliases <- list(
    include_null_range = "include",
    include_null = "include",
    official = "include",
    dec = "include",
    "true" = "include",
    "1" = "include",
    exclude_null_range = "exclude",
    exclude_null = "exclude",
    no_null = "exclude",
    dec_star = "exclude",
    "dec*" = "exclude",
    "false" = "exclude",
    "0" = "exclude"
  )
  if (value %in% names(aliases)) {
    value <- aliases[[value]]
  }
  if (value %in% c("include", "exclude")) {
    return(value)
  }
  if (isTRUE(requested_include_null_range)) {
    return("include")
  }
  "exclude"
}

engine_include_null_range <- function(null_range_mode) {
  identical(null_range_mode, "include")
}

resolve_bgb_cores <- function(requested_cores) {
  cores <- suppressWarnings(as.integer(requested_cores))
  if (length(cores) == 0 || is.na(cores) || cores < 1) {
    cores <- 1L
  }
  if (cores > 1 && !requireNamespace("snow", quietly = TRUE)) {
    warning("BioGeoBEARS requested multiple cores, but R package 'snow' is not installed; using 1 core.")
    return(1L)
  }
  cores
}

apply_state_label_display <- function(labels) {
  display_state_labels(labels)
}

display_state_labels_from_states <- function(states_list, area_names) {
  labels <- vapply(
    states_list,
    range_label_for_state,
    FUN.VALUE = character(1),
    area_names = area_names
  )
  apply_state_label_display(labels)
}

build_configured_states_list <- function(area_names, max_range_size, include_null_range, include_ranges, exclude_ranges) {
  area_names <- as.character(area_names)
  states <- cladoRcpp::rcpp_areas_list_to_states_list(
    areas = area_names,
    maxareas = max_range_size,
    include_null_range = include_null_range
  )

  labels <- vapply(
    states,
    range_label_for_state,
    FUN.VALUE = character(1),
    area_names = area_names
  )

  include_ranges <- as_meta_vector(include_ranges)
  exclude_ranges <- as_meta_vector(exclude_ranges)

  keep <- rep(TRUE, length(labels))
  if (length(include_ranges) > 0) {
    keep <- labels %in% include_ranges
  }
  if (length(exclude_ranges) > 0) {
    keep <- keep & !(labels %in% exclude_ranges)
  }

  if (!any(keep)) {
    stop("Range constraints removed all BioGeoBEARS states.")
  }

  states[keep]
}

base_model_for_j_model <- function(model_name) {
  model_name <- toupper(as.character(model_name))
  if (model_name == "DECJ") {
    return("DEC")
  }
  if (model_name == "DIVALIKEJ") {
    return("DIVALIKE")
  }
  if (model_name == "BAYAREALIKEJ") {
    return("BAYAREALIKE")
  }
  NULL
}

extract_param_estimate <- function(res, param_name) {
  value <- tryCatch(
    res$outputs@params_table[param_name, "est"],
    error = function(e) NA_real_
  )
  value <- suppressWarnings(as.numeric(value))
  if (length(value) == 0 || is.na(value[[1]])) {
    stop(paste("Cannot extract BioGeoBEARS parameter estimate:", param_name))
  }
  value[[1]]
}

extract_bgb_loglik <- function(res) {
  value <- tryCatch(
    get_LnL_from_BioGeoBEARS_results_object(res),
    error = function(e) NA_real_
  )
  value <- suppressWarnings(as.numeric(value))
  if (length(value) > 0 && !is.na(value[[1]])) {
    return(value[[1]])
  }

  value <- tryCatch(
    res$outputs@total_loglik,
    error = function(e) NA_real_
  )
  value <- suppressWarnings(as.numeric(value))
  if (length(value) > 0 && !is.na(value[[1]])) {
    return(value[[1]])
  }

  NA_real_
}

clamp_numeric <- function(value, lower, upper) {
  min(max(as.numeric(value), lower), upper)
}

nested_start_from_base_result <- function(model_name, base_model, base_res) {
  dstart <- extract_param_estimate(base_res, "d")
  estart <- extract_param_estimate(base_res, "e")

  if (toupper(as.character(model_name)) == "BAYAREALIKEJ") {
    dstart <- clamp_numeric(dstart, 0.0000001, 4.9999999)
    estart <- clamp_numeric(estart, 0.0000001, 4.9999999)
  }

  list(
    base_model = base_model,
    dstart = dstart,
    estart = estart,
    jstart = 0.0001,
    base_loglik = extract_bgb_loglik(base_res)
  )
}

apply_nested_j_start <- function(runobj, nested_start) {
  if (is.null(nested_start)) {
    return(runobj)
  }

  runobj$BioGeoBEARS_model_object@params_table["d", "init"] <- nested_start$dstart
  runobj$BioGeoBEARS_model_object@params_table["d", "est"] <- nested_start$dstart
  runobj$BioGeoBEARS_model_object@params_table["e", "init"] <- nested_start$estart
  runobj$BioGeoBEARS_model_object@params_table["e", "est"] <- nested_start$estart
  runobj$BioGeoBEARS_model_object@params_table["j", "init"] <- nested_start$jstart
  runobj$BioGeoBEARS_model_object@params_table["j", "est"] <- nested_start$jstart
  runobj
}

configure_bgb_model <- function(runobj, model_name, nested_start = NULL) {
  model_name <- toupper(as.character(model_name))

  # 所有模型先统一回到无 J 状态
  runobj$BioGeoBEARS_model_object@params_table["j", "type"] <- "fixed"
  runobj$BioGeoBEARS_model_object@params_table["j", "init"] <- 0.0
  runobj$BioGeoBEARS_model_object@params_table["j", "est"] <- 0.0

  if (model_name == "DEC") {
    return(runobj)
  }

  if (model_name == "DECJ") {
    runobj$BioGeoBEARS_model_object@params_table["j", "type"] <- "free"
    runobj <- apply_nested_j_start(runobj, nested_start)
    return(runobj)
  }

  if (model_name %in% c("DIVALIKE", "DIVALIKEJ")) {
    runobj$BioGeoBEARS_model_object@params_table["s", "type"] <- "fixed"
    runobj$BioGeoBEARS_model_object@params_table["s", "init"] <- 0.0
    runobj$BioGeoBEARS_model_object@params_table["s", "est"] <- 0.0

    runobj$BioGeoBEARS_model_object@params_table["ysv", "type"] <- "2-j"
    runobj$BioGeoBEARS_model_object@params_table["ys", "type"] <- "ysv*1/2"
    runobj$BioGeoBEARS_model_object@params_table["y", "type"] <- "ysv*1/2"
    runobj$BioGeoBEARS_model_object@params_table["v", "type"] <- "ysv*1/2"

    runobj$BioGeoBEARS_model_object@params_table["mx01v", "type"] <- "fixed"
    runobj$BioGeoBEARS_model_object@params_table["mx01v", "init"] <- 0.5
    runobj$BioGeoBEARS_model_object@params_table["mx01v", "est"] <- 0.5

    if (model_name == "DIVALIKEJ") {
      runobj$BioGeoBEARS_model_object@params_table["j", "type"] <- "free"
      runobj$BioGeoBEARS_model_object@params_table["j", "min"] <- 0.00001
      runobj$BioGeoBEARS_model_object@params_table["j", "max"] <- 1.99999
      runobj <- apply_nested_j_start(runobj, nested_start)
    }

    return(runobj)
  }

  if (model_name %in% c("BAYAREALIKE", "BAYAREALIKEJ")) {
    runobj$BioGeoBEARS_model_object@params_table["s", "type"] <- "fixed"
    runobj$BioGeoBEARS_model_object@params_table["s", "init"] <- 0.0
    runobj$BioGeoBEARS_model_object@params_table["s", "est"] <- 0.0

    runobj$BioGeoBEARS_model_object@params_table["v", "type"] <- "fixed"
    runobj$BioGeoBEARS_model_object@params_table["v", "init"] <- 0.0
    runobj$BioGeoBEARS_model_object@params_table["v", "est"] <- 0.0

    runobj$BioGeoBEARS_model_object@params_table["ysv", "type"] <- "1-j"
    runobj$BioGeoBEARS_model_object@params_table["ys", "type"] <- "ysv*1/1"
    runobj$BioGeoBEARS_model_object@params_table["y", "type"] <- "1-j"

    runobj$BioGeoBEARS_model_object@params_table["mx01y", "type"] <- "fixed"
    runobj$BioGeoBEARS_model_object@params_table["mx01y", "init"] <- 0.9999
    runobj$BioGeoBEARS_model_object@params_table["mx01y", "est"] <- 0.9999

    if (model_name == "BAYAREALIKEJ") {
      runobj$BioGeoBEARS_model_object@params_table["j", "type"] <- "free"
      runobj$BioGeoBEARS_model_object@params_table["j", "min"] <- 0.00001
      runobj$BioGeoBEARS_model_object@params_table["j", "max"] <- 0.99999
      runobj$BioGeoBEARS_model_object@params_table["d", "min"] <- 0.0000001
      runobj$BioGeoBEARS_model_object@params_table["d", "max"] <- 4.9999999
      runobj$BioGeoBEARS_model_object@params_table["e", "min"] <- 0.0000001
      runobj$BioGeoBEARS_model_object@params_table["e", "max"] <- 4.9999999
      runobj <- apply_nested_j_start(runobj, nested_start)
    }

    return(runobj)
  }

  stop(paste("Unsupported BioGeoBEARS model for v1:", model_name))
}

run_configured_bgb_optimization <- function(runobj, model_name, nested_start_cache = NULL, cache_key = NULL) {
  model_name <- toupper(as.character(model_name))
  base_model <- base_model_for_j_model(model_name)
  nested_start <- NULL

  if (!is.null(base_model)) {
    base_cache_key <- NULL
    base_reused <- FALSE
    if (!is.null(nested_start_cache) && !is.null(cache_key)) {
      base_cache_key <- paste(cache_key, base_model, sep = "||")
    }

    if (!is.null(base_cache_key) && exists(base_cache_key, envir = nested_start_cache, inherits = FALSE)) {
      base_res <- get(base_cache_key, envir = nested_start_cache, inherits = FALSE)
      base_reused <- TRUE
    } else {
      base_runobj <- configure_bgb_model(runobj, base_model)
      check_BioGeoBEARS_run(base_runobj)
      base_res <- bears_optim_run(base_runobj)
      if (!is.null(base_cache_key)) {
        assign(base_cache_key, base_res, envir = nested_start_cache)
      }
    }

    nested_start <- nested_start_from_base_result(model_name, base_model, base_res)
    nested_start$base_reused <- base_reused
  }

  final_runobj <- configure_bgb_model(runobj, model_name, nested_start = nested_start)
  check_BioGeoBEARS_run(final_runobj)
  final_res <- bears_optim_run(final_runobj)

  if (!is.null(nested_start_cache) && !is.null(cache_key) && is.null(base_model)) {
    assign(paste(cache_key, model_name, sep = "||"), final_res, envir = nested_start_cache)
  }

  list(
    runobj = final_runobj,
    res = final_res,
    nested_start = nested_start
  )
}

extract_state_labels <- function(res, runobj, n_states, area_names = NULL) {
  candidates <- list(
    extract_candidate(res, c("states_list", "states_list_old", "states_list_new")),
    extract_candidate(runobj, c("states_list", "states_list_old", "states_list_new"))
  )

  for (cand in candidates) {
    if (is.null(cand)) {
      next
    }

    if (is.list(cand) && length(cand) == n_states) {
      labs <- vapply(cand, format_state_label_from_entry, FUN.VALUE = character(1), area_names = area_names)
      return(labs)
    }
  }

  character(0)
}

normalize_prob_matrix <- function(mat, internal_nodes) {
  mat <- unwrap_prob_object(mat)

  m <- tryCatch(as.matrix(mat), error = function(e) NULL)
  if (is.null(m)) {
    stop("Cannot convert ancestral probability object to matrix.")
  }

  internal_chr <- as.character(internal_nodes)
  total_nodes <- max(internal_nodes)

  rn <- rownames(m)
  cn <- colnames(m)

  rn_norm <- normalize_ids(rn)
  cn_norm <- normalize_ids(cn)

  # 情况 1：行名里直接能匹配内部节点号
  if (!is.null(rn_norm) && all(internal_chr %in% rn_norm)) {
    idx <- match(internal_chr, rn_norm)
    nm <- m[idx, , drop = FALSE]
    rownames(nm) <- internal_chr
    return(nm)
  }

  # 情况 2：列名里能匹配内部节点号
  if (!is.null(cn_norm) && all(internal_chr %in% cn_norm)) {
    idx <- match(internal_chr, cn_norm)
    nm <- t(m[, idx, drop = FALSE])
    rownames(nm) <- internal_chr
    return(nm)
  }

  # 情况 3：矩阵包含所有节点（tips + internals）作为行
  if (nrow(m) >= total_nodes) {
    nm <- m[internal_nodes, , drop = FALSE]
    rownames(nm) <- internal_chr
    return(nm)
  }

  # 情况 4：矩阵包含所有节点作为列
  if (ncol(m) >= total_nodes) {
    nm <- t(m[, internal_nodes, drop = FALSE])
    rownames(nm) <- internal_chr
    return(nm)
  }

  # 情况 5：矩阵只有内部节点行
  if (nrow(m) == length(internal_nodes)) {
    rownames(m) <- internal_chr
    return(m)
  }

  # 情况 6：矩阵只有内部节点列
  if (ncol(m) == length(internal_nodes)) {
    nm <- t(m)
    rownames(nm) <- internal_chr
    return(nm)
  }

  stop("Cannot align ancestral probability matrix with internal nodes.")
}

normalize_rows_to_one <- function(m) {
  m <- as.matrix(m)
  for (i in seq_len(nrow(m))) {
    s <- sum(as.numeric(m[i, ]), na.rm = TRUE)
    if (s > 0) {
      m[i, ] <- as.numeric(m[i, ]) / s
    }
  }
  m
}

build_child_map <- function(tr) {
  split(tr$edge[, 2], tr$edge[, 1])
}

get_desc_tips <- function(tr, child_map, node) {
  n_tips <- length(tr$tip.label)
  if (node <= n_tips) {
    return(tr$tip.label[[node]])
  }

  kids <- child_map[[as.character(node)]]
  if (is.null(kids) || length(kids) == 0) {
    return(character(0))
  }

  out <- character(0)
  for (k in kids) {
    out <- c(out, get_desc_tips(tr, child_map, k))
  }
  out
}

extract_optim_summary <- function(res) {
  out <- list()

  for (nm in c("optim_result", "total_loglik", "LnL", "lnL")) {
    val <- extract_candidate(res, c(nm))
    if (!is.null(val)) {
      out[[nm]] <- val
    }
  }

  # 抽常见参数
  param_cands <- extract_candidate(res, c("params", "optim_result"))
  if (!is.null(param_cands)) {
    out[["param_object"]] <- param_cands
  }

  out
}

make_node_results <- function(tr, child_map, internal_nodes, top_mat, bottom_mat, state_labels) {
  node_results <- list()

  for (node in internal_nodes) {
    node_chr <- as.character(node)
    desc_tips <- sort(get_desc_tips(tr, child_map, node))
    clade_key <- paste(desc_tips, collapse = "|")

    probs_top <- as.numeric(top_mat[node_chr, , drop = TRUE])
    probs_bottom <- as.numeric(bottom_mat[node_chr, , drop = TRUE])

    names(probs_top) <- state_labels
    names(probs_bottom) <- state_labels

    top_probabilities <- as.list(as.numeric(probs_top))
    names(top_probabilities) <- state_labels
    bottom_probabilities <- as.list(as.numeric(probs_bottom))
    names(bottom_probabilities) <- state_labels

    ord <- order(probs_top, decreasing = TRUE)
    probs_top <- probs_top[ord]
    probs_bottom <- probs_bottom[ord]

    states <- list()
    for (j in seq_along(probs_top)) {
      p <- as.numeric(probs_top[[j]])
      if (is.na(p) || p <= 0) {
        next
      }
      states[[length(states) + 1]] <- list(
        label = names(probs_top)[[j]],
        prob = p,
        prob_percent = 100.0 * p,
        bottom_prob = as.numeric(probs_bottom[[j]])
      )
    }

    node_results[[length(node_results) + 1]] <- list(
      number = node_chr,
      clade_key = clade_key,
      display_node_id = node_chr,
      supporting_tree_count = 1,
      total_tree_count = 1,
      top_probabilities = top_probabilities,
      bottom_probabilities = bottom_probabilities,
      states = states
    )
  }

  node_results
}

append_progress <- function(progress_path, job_id, status, message = "") {
  if (is.null(progress_path) || !nzchar(as.character(progress_path))) {
    return(invisible(NULL))
  }
  line <- paste(
    as.character(job_id),
    as.character(status),
    gsub("[\r\n\t]+", " ", as.character(message)),
    sep = "\t"
  )
  cat(line, "\n", file = progress_path, append = TRUE)
  invisible(NULL)
}

stringify_bsm_table <- function(df) {
  if (is.null(df) || !is.data.frame(df)) {
    return(data.frame())
  }
  for (nm in names(df)) {
    if (is.list(df[[nm]]) && !is.data.frame(df[[nm]])) {
      df[[nm]] <- vapply(
        df[[nm]],
        function(x) paste(as.character(unlist(x)), collapse = "|"),
        FUN.VALUE = character(1)
      )
    }
  }
  df
}

rbind_bsm_tables <- function(tables) {
  pieces <- list()
  for (i in seq_along(tables)) {
    df <- stringify_bsm_table(tables[[i]])
    if (!is.null(df) && is.data.frame(df) && nrow(df) > 0) {
      df$sample_id <- i
      pieces[[length(pieces) + 1]] <- df
    }
  }
  if (length(pieces) == 0) {
    return(data.frame(sample_id = integer()))
  }
  do.call(rbind, pieces)
}

add_bsm_state_labels <- function(df, state_labels) {
  if (is.null(df) || !is.data.frame(df) || length(state_labels) == 0) {
    return(df)
  }
  state_text <- function(values) {
    indices <- suppressWarnings(as.integer(values))
    out <- rep(NA_character_, length(indices))
    valid <- !is.na(indices) & indices >= 1 & indices <= length(state_labels)
    out[valid] <- state_labels[indices[valid]]
    out
  }
  if ("sampled_states_AT_nodes" %in% names(df)) {
    df$sampled_states_AT_nodes_txt <- state_text(df$sampled_states_AT_nodes)
  }
  if ("sampled_states_AT_brbots" %in% names(df)) {
    df$sampled_states_AT_brbots_txt <- state_text(df$sampled_states_AT_brbots)
  }
  if ("samp_LEFT_dcorner" %in% names(df)) {
    df$samp_LEFT_dcorner_txt <- state_text(df$samp_LEFT_dcorner)
  }
  if ("samp_RIGHT_dcorner" %in% names(df)) {
    df$samp_RIGHT_dcorner_txt <- state_text(df$samp_RIGHT_dcorner)
  }
  df
}

write_bsm_event_tables <- function(bsm_output, outdir, state_labels = character(0)) {
  dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
  RES_clado_events_tables <- bsm_output$RES_clado_events_tables
  RES_ana_events_tables <- bsm_output$RES_ana_events_tables

  save(RES_clado_events_tables, file = file.path(outdir, "RES_clado_events_tables.Rdata"))
  save(RES_ana_events_tables, file = file.path(outdir, "RES_ana_events_tables.Rdata"))

  all_clado <- add_bsm_state_labels(rbind_bsm_tables(RES_clado_events_tables), state_labels)
  all_ana <- add_bsm_state_labels(rbind_bsm_tables(RES_ana_events_tables), state_labels)

  write.csv(all_clado, file = file.path(outdir, "bsm_clado_events.csv"), row.names = FALSE)
  write.csv(all_ana, file = file.path(outdir, "bsm_ana_events.csv"), row.names = FALSE)
  invisible(list(clado_rows = nrow(all_clado), ana_rows = nrow(all_ana)))
}

run_bsm_if_requested <- function(args, res) {
  if (is.null(args[["bsm_outdir"]]) || !nzchar(as.character(args[["bsm_outdir"]]))) {
    return(invisible(NULL))
  }

  bsm_outdir <- normalizePath(as.character(args[["bsm_outdir"]]), winslash = "/", mustWork = FALSE)
  bsm_nummaps <- as.integer(ifelse(is.null(args[["bsm_nummaps"]]), 100, args[["bsm_nummaps"]]))
  bsm_nummaps <- max(1, bsm_nummaps)
  bsm_seed <- as.integer(ifelse(is.null(args[["bsm_seed"]]), 12345, args[["bsm_seed"]]))
  bsm_maxnum_maps_to_try <- as.integer(ifelse(
    is.null(args[["bsm_maxnum_maps_to_try"]]),
    bsm_nummaps,
    args[["bsm_maxnum_maps_to_try"]]
  ))
  bsm_maxnum_maps_to_try <- max(1, bsm_maxnum_maps_to_try)
  bsm_maxtries <- as.integer(ifelse(is.null(args[["bsm_maxtries_per_branch"]]), 40000, args[["bsm_maxtries_per_branch"]]))
  bsm_maxtries <- max(1, bsm_maxtries)

  dir.create(bsm_outdir, recursive = TRUE, showWarnings = FALSE)
  stochastic_mapping_inputs_list <- get_inputs_for_stochastic_mapping(res = res)
  bsm_state_labels <- character(0)
  try({
    returned_mats <- get_Qmat_COOmat_from_BioGeoBEARS_run_object(
      BioGeoBEARS_run_object = res$inputs
    )
    bsm_state_labels <- vapply(
      returned_mats$ranges_list,
      range_label_for_state,
      FUN.VALUE = character(1),
      area_names = returned_mats$areanames
    )
    bsm_state_labels <- apply_state_label_display(bsm_state_labels)
  }, silent = TRUE)
  save(stochastic_mapping_inputs_list, file = file.path(bsm_outdir, "BSM_inputs_file.Rdata"))

  bsm_output <- runBSM(
    res,
    stochastic_mapping_inputs_list = stochastic_mapping_inputs_list,
    maxnum_maps_to_try = bsm_maxnum_maps_to_try,
    nummaps_goal = bsm_nummaps,
    maxtries_per_branch = bsm_maxtries,
    save_after_every_try = TRUE,
    savedir = bsm_outdir,
    seedval = bsm_seed,
    wait_before_save = 0.01,
    master_nodenum_toPrint = 0
  )

  summary <- write_bsm_event_tables(bsm_output, bsm_outdir, state_labels = bsm_state_labels)
  jsonlite::write_json(
    list(
      nummaps = bsm_nummaps,
      seed = bsm_seed,
      maxnum_maps_to_try = bsm_maxnum_maps_to_try,
      maxtries_per_branch = bsm_maxtries,
      clado_rows = summary$clado_rows,
      ana_rows = summary$ana_rows,
      state_labels = bsm_state_labels,
      clado_csv = file.path(bsm_outdir, "bsm_clado_events.csv"),
      ana_csv = file.path(bsm_outdir, "bsm_ana_events.csv")
    ),
    file.path(bsm_outdir, "bsm_summary.json"),
    auto_unbox = TRUE,
    pretty = TRUE,
    digits = NA
  )
  invisible(bsm_output)
}

run_bgb_job <- function(args, nested_start_cache = NULL) {

treefile <- must_get(args, "tree")
geogfile <- must_get(args, "geog")
areas_json <- must_get(args, "areas")
model_name <- toupper(must_get(args, "model"))
max_range_size <- as.integer(must_get(args, "max_range_size"))
requested_include_null_range <- bool_value(must_get(args, "include_null_range"))
out_json <- must_get(args, "out")

if (!(model_name %in% c("DEC", "DECJ", "DIVALIKE", "DIVALIKEJ", "BAYAREALIKE", "BAYAREALIKEJ"))) {
  stop(paste("Unsupported BioGeoBEARS model for v1:", model_name))
}

areas_meta <- safe_read_json(areas_json)
areas_base_dir <- dirname(normalizePath(areas_json, winslash = "/", mustWork = FALSE))
null_range_mode_source <- args[["null_range_mode"]]
if (is.null(null_range_mode_source) || !nzchar(as.character(null_range_mode_source))) {
  null_range_mode_source <- areas_meta$null_range_mode
}
null_range_mode <- normalize_null_range_mode(null_range_mode_source, requested_include_null_range)
include_null_range <- engine_include_null_range(null_range_mode)
job_cache_key <- build_bgb_cache_key(
  model_name = "",
  treefile = treefile,
  geogfile = geogfile,
  areas_meta = areas_meta,
  areas_base_dir = areas_base_dir,
  max_range_size = max_range_size,
  include_null_range = include_null_range,
  null_range_mode = null_range_mode
)

runobj <- define_BioGeoBEARS_run()
runobj$trfn <- treefile
runobj$geogfn <- geogfile
runobj$max_range_size <- max_range_size
runobj$min_branchlength <- 0.000001
runobj$include_null_range <- include_null_range

timeperiods_path <- meta_path(areas_meta, "timeperiods_filename", areas_base_dir)
dispersal_multipliers_path <- meta_path(areas_meta, "dispersal_multipliers_filename", areas_base_dir)
areas_allowed_path <- meta_path(areas_meta, "areas_allowed_filename", areas_base_dir)
areas_adjacency_path <- meta_path(areas_meta, "areas_adjacency_filename", areas_base_dir)
distances_path <- meta_path(areas_meta, "distances_filename", areas_base_dir)

if (!is.null(timeperiods_path) && file.exists(timeperiods_path)) {
  runobj$timesfn <- timeperiods_path
}
if (!is.null(dispersal_multipliers_path) && file.exists(dispersal_multipliers_path)) {
  runobj$dispersal_multipliers_fn <- dispersal_multipliers_path
}
if (!is.null(areas_allowed_path) && file.exists(areas_allowed_path)) {
  runobj$areas_allowed_fn <- areas_allowed_path
}
if (!is.null(areas_adjacency_path) && file.exists(areas_adjacency_path)) {
  runobj$areas_adjacency_fn <- areas_adjacency_path
}
if (!is.null(distances_path) && file.exists(distances_path)) {
  runobj$distsfn <- distances_path
}

runobj$states_list <- build_configured_states_list(
  area_names = areas_meta$area_names,
  max_range_size = max_range_size,
  include_null_range = include_null_range,
  include_ranges = areas_meta$include_ranges,
  exclude_ranges = areas_meta$exclude_ranges
)

runobj$use_optimx <- TRUE
requested_cores <- max(1, as.integer(ifelse(is.null(areas_meta$cores), 1, areas_meta$cores)))
runobj$num_cores_to_use <- resolve_bgb_cores(requested_cores)
runobj$force_sparse <- FALSE
runobj$speedup <- TRUE
runobj$calc_ancprobs <- TRUE

runobj <- readfiles_BioGeoBEARS_run(runobj)
if (!is.null(timeperiods_path) && file.exists(timeperiods_path)) {
  runobj <- section_the_tree(inputs = runobj, make_master_table = TRUE, plot_pieces = FALSE)
}
runobj$return_condlikes_table <- TRUE
runobj$calc_TTL_loglike_from_condlikes_table <- TRUE
runobj$calc_ancprobs <- TRUE

optimization <- run_configured_bgb_optimization(
  runobj,
  model_name,
  nested_start_cache = nested_start_cache,
  cache_key = job_cache_key
)
runobj <- optimization$runobj
res <- optimization$res
nested_start <- optimization$nested_start

run_bsm_if_requested(args, res)

top_raw <- extract_candidate(
  res,
  c("ML_marginal_prob_each_state_at_branch_top_AT_node")
)
bottom_raw <- extract_candidate(
  res,
  c("ML_marginal_prob_each_state_at_branch_bottom_below_node")
)

top_raw <- unwrap_prob_object(top_raw)
bottom_raw <- unwrap_prob_object(bottom_raw)

tr <- read.tree(treefile)
internal_nodes <- seq.int(length(tr$tip.label) + 1, length(tr$tip.label) + tr$Nnode)
child_map <- build_child_map(tr)

if (is.null(top_raw)) {
  stop("BioGeoBEARS result does not contain top ancestral probability matrix.")
}
if (is.null(bottom_raw)) {
  stop("BioGeoBEARS result does not contain bottom ancestral probability matrix.")
}



top_mat <- normalize_prob_matrix(top_raw, internal_nodes)
bottom_mat <- normalize_prob_matrix(bottom_raw, internal_nodes)

top_mat <- normalize_rows_to_one(top_mat)
bottom_mat <- normalize_rows_to_one(bottom_mat)

n_states <- ncol(top_mat)

state_labels <- character(0)
if (is.list(runobj$states_list) && length(runobj$states_list) == n_states) {
  state_labels <- display_state_labels_from_states(
    runobj$states_list,
    areas_meta$area_names
  )
}

if (length(state_labels) != n_states) {
  state_labels <- apply_state_label_display(
    extract_state_labels(res, runobj, n_states, area_names = areas_meta$area_names)
  )
}

if (length(state_labels) != n_states && !is.null(colnames(top_mat))) {
  matrix_labels <- as.character(colnames(top_mat))
  generic_labels <- grepl("^(V)?[0-9]+$|^state_[0-9]+$", matrix_labels)
  if (length(matrix_labels) == n_states && any(nzchar(matrix_labels)) && !all(generic_labels)) {
    state_labels <- apply_state_label_display(matrix_labels)
  }
}

if (length(state_labels) != n_states) {
  configured_labels <- build_bgb_state_labels(
    area_names = areas_meta$area_names,
    max_range_size = max_range_size,
    include_null_range = include_null_range
  )
  if (length(configured_labels) == n_states) {
    state_labels <- apply_state_label_display(configured_labels)
  }
}

if (length(state_labels) != n_states) {
  state_labels <- paste0("state_", seq_len(n_states))
}

colnames(top_mat) <- state_labels
colnames(bottom_mat) <- state_labels

payload <- list(
  attributes = list(
    model_name = model_name,
    treefile = treefile,
    geogfile = geogfile,
    area_names = areas_meta$area_names,
    max_range_size = max_range_size,
    include_null_range = include_null_range,
    requested_include_null_range = requested_include_null_range,
    null_range_mode = null_range_mode,
    include_ranges = areas_meta$include_ranges,
    exclude_ranges = areas_meta$exclude_ranges,
    requested_cores = requested_cores,
    cores_fallback_to_one = requested_cores > runobj$num_cores_to_use,
    cores = runobj$num_cores_to_use,
    time_matrix_kind = areas_meta$time_matrix_kind,
    timeperiods_filename = areas_meta$timeperiods_filename,
    dispersal_multipliers_filename = areas_meta$dispersal_multipliers_filename,
    areas_allowed_filename = areas_meta$areas_allowed_filename,
    areas_adjacency_filename = areas_meta$areas_adjacency_filename,
    distances_filename = areas_meta$distances_filename,
    tip_count = length(tr$tip.label),
    internal_node_count = tr$Nnode,
    j_parameter_mode = runobj$BioGeoBEARS_model_object@params_table["j", "type"],
    j_parameter_init = runobj$BioGeoBEARS_model_object@params_table["j", "init"],
    j_parameter_est = runobj$BioGeoBEARS_model_object@params_table["j", "est"],
    nested_start_used = !is.null(nested_start),
    nested_base_model = if (!is.null(nested_start)) nested_start$base_model else "",
    nested_dstart = if (!is.null(nested_start)) nested_start$dstart else NA_real_,
    nested_estart = if (!is.null(nested_start)) nested_start$estart else NA_real_,
    nested_jstart = if (!is.null(nested_start)) nested_start$jstart else NA_real_,
    nested_base_loglik = if (!is.null(nested_start)) nested_start$base_loglik else NA_real_,
    nested_base_reused = if (!is.null(nested_start)) isTRUE(nested_start$base_reused) else FALSE
  ),
  optim_summary = extract_optim_summary(res),
  node_results = make_node_results(
    tr = tr,
    child_map = child_map,
    internal_nodes = internal_nodes,
    top_mat = top_mat,
    bottom_mat = bottom_mat,
    state_labels = state_labels
  )
)

jsonlite::write_json(payload, out_json, auto_unbox = TRUE, pretty = TRUE, digits = NA)
invisible(payload)
}

run_bgb_batch <- function(batch_json, progress_path = NULL) {
  manifest <- safe_read_json(batch_json)
  jobs <- manifest$jobs
  if (is.null(jobs) || length(jobs) == 0) {
    stop("Batch manifest does not contain jobs.")
  }

  failures <- list()
  nested_start_cache <- new.env(parent = emptyenv())
  for (i in seq_along(jobs)) {
    job <- jobs[[i]]
    job_id <- if (!is.null(job$id) && nzchar(as.character(job$id))) as.character(job$id) else as.character(i)
    append_progress(progress_path, job_id, "STARTED")
    tryCatch(
      {
        run_bgb_job(job, nested_start_cache = nested_start_cache)
        append_progress(progress_path, job_id, "DONE")
      },
      error = function(e) {
        msg <- conditionMessage(e)
        append_progress(progress_path, job_id, "ERROR", msg)
        failures[[length(failures) + 1]] <<- list(id = job_id, message = msg)
      }
    )
  }

  if (!is.null(manifest$summary) && nzchar(as.character(manifest$summary))) {
    jsonlite::write_json(
      list(total = length(jobs), failed = length(failures), failures = failures),
      as.character(manifest$summary),
      auto_unbox = TRUE,
      pretty = TRUE,
      digits = NA
    )
  }
  invisible(length(failures))
}

if (!is.null(argv[["batch"]]) && nzchar(as.character(argv[["batch"]]))) {
  run_bgb_batch(argv[["batch"]], argv[["progress"]])
} else {
  run_bgb_job(argv)
}
