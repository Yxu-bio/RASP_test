parse_args <- function(args) {
  out <- list()
  i <- 1
  while (i <= length(args)) {
    key <- args[[i]]
    if (!startsWith(key, "--")) stop(paste("Invalid argument:", key))
    key <- sub("^--", "", key)
    if (i == length(args)) stop(paste("Missing value for argument:", key))
    out[[key]] <- args[[i + 1]]
    i <- i + 2
  }
  out
}

must_get <- function(args, key) {
  value <- args[[key]]
  if (is.null(value) || !nzchar(as.character(value))) {
    stop(paste("Missing required argument:", key))
  }
  as.character(value)
}

write_atomic_csv <- function(df, path) {
  tmp <- paste0(path, ".tmp")
  write.csv(df, tmp, row.names = FALSE)
  if (file.exists(path)) unlink(path)
  if (!file.rename(tmp, path)) stop(paste("Could not replace:", path))
}

matrix_edges <- function(ana_means, founder_means, nummaps, method) {
  ana <- as.matrix(ana_means)
  founder <- as.matrix(founder_means)
  rows <- list()
  for (i in seq_len(nrow(ana))) {
    for (j in seq_len(ncol(ana))) {
      if (i == j) next
      ana_mean <- as.numeric(ana[i, j])
      founder_mean <- as.numeric(founder[i, j])
      total_mean <- ana_mean + founder_mean
      if (!is.finite(total_mean) || total_mean <= 0) next
      rows[[length(rows) + 1]] <- data.frame(
        source_area = rownames(ana)[[i]],
        target_area = colnames(ana)[[j]],
        anagenetic_count = ana_mean * nummaps,
        founder_count = founder_mean * nummaps,
        total_count = total_mean * nummaps,
        mean_per_map = total_mean,
        source_assignment_method = method,
        stringsAsFactors = FALSE
      )
    }
  }
  if (length(rows) == 0) return(data.frame())
  output <- do.call(rbind, rows)
  output[order(-output$total_count, output$source_area, output$target_area), ]
}

source_assigned_event_rows <- function(ana_tables, clado_tables) {
  rows <- list()
  for (sample_id in seq_along(ana_tables)) {
    df <- ana_tables[[sample_id]]
    keep <- !is.na(df$event_type) & df$event_type %in% c("d", "a") &
      !is.na(df$ana_dispersal_from) & nzchar(as.character(df$ana_dispersal_from)) &
      !is.na(df$dispersal_to) & nzchar(as.character(df$dispersal_to))
    if (any(keep)) {
      rows[[length(rows) + 1]] <- data.frame(
        sample_id = sample_id,
        event_kind = "anagenetic",
        source_area = as.character(df$ana_dispersal_from[keep]),
        target_area = as.character(df$dispersal_to[keep]),
        stringsAsFactors = FALSE
      )
    }
  }
  for (sample_id in seq_along(clado_tables)) {
    df <- clado_tables[[sample_id]]
    keep <- !is.na(df$clado_event_type) & df$clado_event_type == "founder (j)" &
      !is.na(df$clado_dispersal_from) & nzchar(as.character(df$clado_dispersal_from)) &
      !is.na(df$clado_dispersal_to) & nzchar(as.character(df$clado_dispersal_to))
    if (any(keep)) {
      rows[[length(rows) + 1]] <- data.frame(
        sample_id = sample_id,
        event_kind = "founder",
        source_area = as.character(df$clado_dispersal_from[keep]),
        target_area = as.character(df$clado_dispersal_to[keep]),
        stringsAsFactors = FALSE
      )
    }
  }
  if (length(rows) == 0) {
    return(data.frame(
      sample_id = integer(), event_kind = character(),
      source_area = character(), target_area = character()
    ))
  }
  do.call(rbind, rows)
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
if (!is.null(args[["lib"]]) && nzchar(as.character(args[["lib"]]))) {
  private_libs <- strsplit(as.character(args[["lib"]]), ";", fixed = TRUE)[[1]]
  private_libs <- private_libs[nzchar(private_libs)]
  .libPaths(c(private_libs, .Library))
}

suppressPackageStartupMessages(library(BioGeoBEARS))
suppressPackageStartupMessages(library(jsonlite))

bsm_dir <- normalizePath(must_get(args, "bsm-dir"), winslash = "/", mustWork = TRUE)
seed <- as.integer(must_get(args, "seed"))
inputs_path <- file.path(bsm_dir, "BSM_inputs_file.Rdata")
ana_path <- file.path(bsm_dir, "RES_ana_events_tables.Rdata")
clado_path <- file.path(bsm_dir, "RES_clado_events_tables.Rdata")
if (!file.exists(inputs_path) || !file.exists(ana_path) || !file.exists(clado_path)) {
  stop("The BSM directory must contain BSM_inputs_file.Rdata and both final event-table RData files.")
}

load(inputs_path)
load(ana_path)
load(clado_path)
res <- stochastic_mapping_inputs_list[[1]]$res
returned_mats <- get_Qmat_COOmat_from_BioGeoBEARS_run_object(res$inputs)
areanames <- as.character(returned_mats$areanames)
raw_tables_have_source_assignments <- (
  length(RES_ana_events_tables) > 0 &&
  length(RES_clado_events_tables) > 0 &&
  all(vapply(
    RES_ana_events_tables,
    function(df) "ana_dispersal_from" %in% names(df),
    FUN.VALUE = logical(1)
  )) &&
  all(vapply(
    RES_clado_events_tables,
    function(df) "clado_dispersal_from" %in% names(df),
    FUN.VALUE = logical(1)
  ))
)

source_assignment_warnings <- character(0)
source_assignment_performed <- FALSE
if (!raw_tables_have_source_assignments) {
  set.seed(seed)
  source_assigned <- withCallingHandlers(
    simulate_source_areas_ana_clado(
      res = res,
      clado_events_tables = RES_clado_events_tables,
      ana_events_tables = RES_ana_events_tables,
      areanames = areanames
    ),
    warning = function(w) {
      source_assignment_warnings <<- c(source_assignment_warnings, conditionMessage(w))
      invokeRestart("muffleWarning")
    }
  )
  RES_clado_events_tables <- source_assigned$clado_events_tables
  RES_ana_events_tables <- source_assigned$ana_events_tables
  source_assignment_performed <- TRUE
}

counts <- count_ana_clado_events(
  clado_events_tables = RES_clado_events_tables,
  ana_events_tables = RES_ana_events_tables,
  areanames = areanames,
  actual_names = areanames
)
nummaps <- length(RES_ana_events_tables)
method <- "biogeobears_probabilistic_unique_source"
edge_rows <- matrix_edges(
  counts$ana_dispersals_counts_fromto_means,
  counts$founder_counts_fromto_means,
  nummaps,
  method
)
source_event_rows <- source_assigned_event_rows(
  RES_ana_events_tables,
  RES_clado_events_tables
)
source_event_path <- file.path(bsm_dir, "bsm_source_assigned_dispersal_events.csv")
write_atomic_csv(source_event_rows, source_event_path)
write_atomic_csv(edge_rows, file.path(bsm_dir, "bsm_dore_reference_edges.csv"))
save(counts, file = file.path(bsm_dir, "bsm_dore_reference_counts.Rdata"))

summary_path <- file.path(bsm_dir, "bsm_summary.json")
summary <- if (file.exists(summary_path)) jsonlite::fromJSON(summary_path, simplifyVector = FALSE) else list()
summary$format <- "rasp5_biogeobears_bsm_summary"
summary$version <- 1
summary$nummaps <- nummaps
summary$source_assignment_method <- method
summary$source_assignment_seed <- seed
summary$source_assignment_function <- "BioGeoBEARS::simulate_source_areas_ana_clado"
summary$source_assignment_warning_count <- length(source_assignment_warnings)
summary$source_assignment_warnings <- unique(source_assignment_warnings)
summary$area_names <- areanames
summary$source_assignment_event_csv <- source_event_path
summary$source_assignments_present_in_loaded_tables <- raw_tables_have_source_assignments
summary$source_assignment_performed_by_postprocessor <- source_assignment_performed
summary$dore_reference_count_function <- "BioGeoBEARS::count_ana_clado_events"
summary$dore_reference_edges_csv <- file.path(bsm_dir, "bsm_dore_reference_edges.csv")
jsonlite::write_json(summary, summary_path, auto_unbox = TRUE, pretty = TRUE, digits = NA)

cat("Source-area assignment and Dore reference counts completed.\n")
cat("Maps:", nummaps, "\n")
cat("Source-assigned dispersal events:", nrow(source_event_rows), "\n")
cat("Edges:", nrow(edge_rows), "\n")
cat("Output:", file.path(bsm_dir, "bsm_dore_reference_edges.csv"), "\n")
