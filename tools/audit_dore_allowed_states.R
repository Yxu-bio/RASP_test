args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4) {
  stop("Usage: audit_dore_allowed_states.R <site-library> <areas.json> <tree> <geog>")
}

site_library <- normalizePath(args[[1]], winslash = "/", mustWork = TRUE)
areas_json <- normalizePath(args[[2]], winslash = "/", mustWork = TRUE)
tree_path <- normalizePath(args[[3]], winslash = "/", mustWork = TRUE)
geog_path <- normalizePath(args[[4]], winslash = "/", mustWork = TRUE)
.libPaths(c(site_library, .Library))

suppressPackageStartupMessages(library(BioGeoBEARS))
suppressPackageStartupMessages(library(jsonlite))

meta <- jsonlite::fromJSON(areas_json, simplifyVector = TRUE)
base_dir <- dirname(areas_json)
area_names <- as.character(meta$area_names)
max_range_size <- as.integer(meta$max_range_size)
include_null_range <- isTRUE(meta$include_null_range)
adjacency_path <- normalizePath(file.path(base_dir, meta$areas_adjacency_filename), winslash = "/", mustWork = TRUE)
time_path <- normalizePath(file.path(base_dir, meta$timeperiods_filename), winslash = "/", mustWork = TRUE)

state_label <- function(state) {
  if (length(state) == 1 && is.na(state[[1]])) return("_")
  paste(area_names[as.integer(state) + 1], collapse = "")
}

all_states <- cladoRcpp::rcpp_areas_list_to_states_list(
  areas = area_names,
  maxareas = max_range_size,
  include_null_range = include_null_range
)
all_labels <- vapply(all_states, state_label, FUN.VALUE = character(1))

paper_allowed_labels <- function(adjacency_df) {
  row.names(adjacency_df) <- names(adjacency_df)
  adjacency_df <- adjacency_df[area_names, area_names]
  allowed_pairs <- character(0)
  if (length(area_names) > 1) {
    for (i in seq_len(length(area_names) - 1)) {
      for (j in seq.int(i + 1, length(area_names))) {
        if (isTRUE(as.logical(adjacency_df[i, j]))) {
          allowed_pairs <- c(allowed_pairs, paste0(area_names[[i]], area_names[[j]]))
        }
      }
    }
  }
  valid <- c(if (include_null_range) "_" else character(0), area_names, allowed_pairs)
  higher <- all_labels[nchar(all_labels) > 2]
  for (label in higher) {
    focal <- strsplit(label, "", fixed = TRUE)[[1]]
    nested <- apply(combn(focal, 2), 2, paste, collapse = "")
    nested <- nested[nested %in% allowed_pairs]
    covered <- unique(strsplit(paste(nested, collapse = ""), "", fixed = TRUE)[[1]])
    if (all(focal %in% covered)) valid <- c(valid, label)
  }
  unique(valid[order(match(valid, all_labels))])
}

runobj <- define_BioGeoBEARS_run()
runobj$trfn <- tree_path
runobj$geogfn <- geog_path
runobj$max_range_size <- max_range_size
runobj$include_null_range <- include_null_range
runobj$timesfn <- time_path
runobj$areas_adjacency_fn <- adjacency_path
runobj$states_list <- all_states
runobj <- readfiles_BioGeoBEARS_run(runobj)

adjacency_lists <- BioGeoBEARS:::read_areas_adjacency_fn(areas_adjacency_fn = adjacency_path)
period_count <- length(adjacency_lists)
period_rows <- vector("list", period_count)
native_all_equal <- TRUE
configured_all_equal <- !is.null(meta$allowed_ranges_by_period) && length(meta$allowed_ranges_by_period) == period_count

for (period_index in seq_len(period_count)) {
  expected <- paper_allowed_labels(adjacency_lists[[period_index]])
  native_states <- BioGeoBEARS:::prune_states_list_by_adjacency(
    all_states,
    adjacency_lists[[period_index]]
  )
  native <- vapply(native_states, state_label, FUN.VALUE = character(1))
  native_missing <- setdiff(expected, native)
  native_extra <- setdiff(native, expected)
  native_equal <- length(native_missing) == 0 && length(native_extra) == 0
  native_all_equal <- native_all_equal && native_equal
  configured <- character(0)
  if (!is.null(meta$allowed_ranges_by_period) && length(meta$allowed_ranges_by_period) >= period_index) {
    configured <- as.character(unlist(meta$allowed_ranges_by_period[[period_index]], use.names = FALSE))
  }
  configured_missing <- setdiff(expected, configured)
  configured_extra <- setdiff(configured, expected)
  configured_equal <- length(configured_missing) == 0 && length(configured_extra) == 0
  configured_all_equal <- configured_all_equal && configured_equal
  period_rows[[period_index]] <- list(
    period = period_index,
    expected_count = length(expected),
    native_adjacency_count = length(native),
    native_adjacency_equal = native_equal,
    native_missing = native_missing,
    native_extra = native_extra,
    configured_count = length(configured),
    configured_equal = configured_equal,
    configured_missing = configured_missing,
    configured_extra = configured_extra,
    expected_states = expected,
    native_adjacency_states = native,
    configured_states = configured
  )
}

payload <- list(
  format = "rasp5_dore_allowed_state_audit",
  version = 1,
  native_adjacency_all_equal = native_all_equal,
  configured_all_equal = configured_all_equal,
  period_state_lists_only = isTRUE(meta$period_state_lists_only),
  period_count = period_count,
  area_names = area_names,
  max_range_size = max_range_size,
  include_null_range = include_null_range,
  periods = period_rows
)
cat(jsonlite::toJSON(payload, auto_unbox = TRUE, pretty = TRUE, null = "null"))
