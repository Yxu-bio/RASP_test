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

format_state_label <- function(entry, area_names) {
  if (is.null(entry) || length(entry) == 0) return("_")
  flat <- unlist(entry, use.names = FALSE)
  if (length(flat) == 0 || all(is.na(flat))) return("_")
  if (is.character(entry)) return(paste(entry[nzchar(entry)], collapse = ""))
  values <- suppressWarnings(as.integer(flat))
  values <- values[!is.na(values)]
  if (length(values) == 0) return("_")
  indexes <- values + 1L
  if (all(indexes >= 1L & indexes <= length(area_names))) {
    return(paste(as.character(area_names)[indexes], collapse = ""))
  }
  paste(as.character(flat), collapse = "")
}

display_state_labels <- function(labels) {
  labels <- as.character(labels)
  labels[!nzchar(labels) | labels == "_"] <- "/"
  labels
}

stringify_bsm_table <- function(df) {
  if (is.null(df) || !is.data.frame(df)) return(data.frame())
  for (name in names(df)) {
    if (is.list(df[[name]]) && !is.data.frame(df[[name]])) {
      df[[name]] <- vapply(
        df[[name]],
        function(value) paste(as.character(unlist(value)), collapse = "|"),
        FUN.VALUE = character(1)
      )
    }
  }
  df
}

add_state_labels <- function(df, state_labels) {
  if (!is.data.frame(df) || length(state_labels) == 0) return(df)
  state_text <- function(values) {
    indexes <- suppressWarnings(as.integer(values))
    output <- rep(NA_character_, length(indexes))
    valid <- !is.na(indexes) & indexes >= 1 & indexes <= length(state_labels)
    output[valid] <- state_labels[indexes[valid]]
    output
  }
  mappings <- c(
    sampled_states_AT_nodes = "sampled_states_AT_nodes_txt",
    sampled_states_AT_brbots = "sampled_states_AT_brbots_txt",
    samp_LEFT_dcorner = "samp_LEFT_dcorner_txt",
    samp_RIGHT_dcorner = "samp_RIGHT_dcorner_txt"
  )
  for (source_name in names(mappings)) {
    if (source_name %in% names(df)) {
      df[[mappings[[source_name]]]] <- state_text(df[[source_name]])
    }
  }
  df
}

write_bsm_tables_csv <- function(tables, path, state_labels = character(0)) {
  if (file.exists(path)) unlink(path)
  wrote_header <- FALSE
  row_count <- 0L
  for (i in seq_along(tables)) {
    df <- stringify_bsm_table(tables[[i]])
    if (is.data.frame(df) && nrow(df) > 0) {
      df$sample_id <- i
      df <- add_state_labels(df, state_labels)
      write.table(
        df,
        file = path,
        sep = ",",
        row.names = FALSE,
        col.names = !wrote_header,
        append = wrote_header,
        quote = TRUE,
        qmethod = "double"
      )
      wrote_header <- TRUE
      row_count <- row_count + nrow(df)
    }
  }
  if (!wrote_header) {
    write.csv(data.frame(sample_id = integer()), path, row.names = FALSE)
  }
  row_count
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
if (!is.null(args[["lib"]]) && nzchar(as.character(args[["lib"]]))) {
  private_libs <- strsplit(as.character(args[["lib"]]), ";", fixed = TRUE)[[1]]
  private_libs <- private_libs[nzchar(private_libs)]
  .libPaths(c(private_libs, .Library))
}

suppressPackageStartupMessages(library(BioGeoBEARS))
suppressPackageStartupMessages(library(jsonlite))

inputs_path <- normalizePath(must_get(args, "inputs"), winslash = "/", mustWork = TRUE)
outdir <- normalizePath(must_get(args, "outdir"), winslash = "/", mustWork = FALSE)
nummaps <- max(1L, as.integer(must_get(args, "nummaps")))
seed <- as.integer(must_get(args, "seed"))
maxnum_maps_to_try <- max(1L, as.integer(must_get(args, "maxnum-maps-to-try")))
maxtries_per_branch <- max(1L, as.integer(must_get(args, "maxtries-per-branch")))

dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
load(inputs_path)
if (!exists("stochastic_mapping_inputs_list", inherits = FALSE)) {
  stop("The RData file does not contain stochastic_mapping_inputs_list.")
}
if (!is.list(stochastic_mapping_inputs_list) || length(stochastic_mapping_inputs_list) == 0) {
  stop("stochastic_mapping_inputs_list is empty or invalid.")
}
res <- stochastic_mapping_inputs_list[[1]]$res
if (is.null(res) || is.null(res$inputs)) {
  stop("The saved stochastic mapping inputs do not contain the fitted BioGeoBEARS result.")
}

state_labels <- character(0)
bsm_areanames <- character(0)
try({
  returned_mats <- get_Qmat_COOmat_from_BioGeoBEARS_run_object(
    BioGeoBEARS_run_object = res$inputs
  )
  bsm_areanames <- as.character(returned_mats$areanames)
  state_labels <- vapply(
    returned_mats$ranges_list,
    format_state_label,
    FUN.VALUE = character(1),
    area_names = returned_mats$areanames
  )
  state_labels <- display_state_labels(state_labels)
}, silent = TRUE)

file.copy(inputs_path, file.path(outdir, "BSM_inputs_file.Rdata"), overwrite = TRUE)
started <- Sys.time()
cat("Reusing fitted BioGeoBEARS result from:", inputs_path, "\n")
cat("Requested stochastic maps:", nummaps, "\n")

bsm_output <- runBSM(
  res,
  stochastic_mapping_inputs_list = stochastic_mapping_inputs_list,
  maxnum_maps_to_try = maxnum_maps_to_try,
  nummaps_goal = nummaps,
  maxtries_per_branch = maxtries_per_branch,
  save_after_every_try = TRUE,
  savedir = outdir,
  seedval = seed,
  wait_before_save = 0.01,
  master_nodenum_toPrint = 0
)

if (length(bsm_areanames) == 0) {
  stop("Could not determine BioGeoBEARS area names for BSM source-area assignment.")
}
source_assignment_seed <- seed
set.seed(source_assignment_seed)
source_assignment_warnings <- character(0)
source_assigned <- withCallingHandlers(
  simulate_source_areas_ana_clado(
    res = res,
    clado_events_tables = bsm_output$RES_clado_events_tables,
    ana_events_tables = bsm_output$RES_ana_events_tables,
    areanames = bsm_areanames
  ),
  warning = function(w) {
    source_assignment_warnings <<- c(source_assignment_warnings, conditionMessage(w))
    invokeRestart("muffleWarning")
  }
)
bsm_output$RES_clado_events_tables <- source_assigned$clado_events_tables
bsm_output$RES_ana_events_tables <- source_assigned$ana_events_tables
rm(source_assigned)
invisible(gc())
RES_clado_events_tables <- bsm_output$RES_clado_events_tables
RES_ana_events_tables <- bsm_output$RES_ana_events_tables
save(RES_clado_events_tables, file = file.path(outdir, "RES_clado_events_tables.Rdata"))
save(RES_ana_events_tables, file = file.path(outdir, "RES_ana_events_tables.Rdata"))

clado_rows <- write_bsm_tables_csv(
  bsm_output$RES_clado_events_tables,
  file.path(outdir, "bsm_clado_events.csv"),
  state_labels
)
ana_rows <- write_bsm_tables_csv(
  bsm_output$RES_ana_events_tables,
  file.path(outdir, "bsm_ana_events.csv"),
  state_labels
)

jsonlite::write_json(
  list(
    format = "rasp5_biogeobears_bsm_summary",
    version = 1,
    nummaps = nummaps,
    seed = seed,
    maxnum_maps_to_try = maxnum_maps_to_try,
    maxtries_per_branch = maxtries_per_branch,
    source_assignment_method = "biogeobears_probabilistic_unique_source",
    source_assignment_seed = source_assignment_seed,
    source_assignment_function = "BioGeoBEARS::simulate_source_areas_ana_clado",
    source_assignment_warning_count = length(source_assignment_warnings),
    source_assignment_warnings = unique(source_assignment_warnings),
    area_names = bsm_areanames,
    clado_rows = clado_rows,
    ana_rows = ana_rows,
    state_labels = state_labels,
    clado_csv = file.path(outdir, "bsm_clado_events.csv"),
    ana_csv = file.path(outdir, "bsm_ana_events.csv"),
    reused_fitted_result = TRUE,
    source_bsm_inputs = inputs_path,
    elapsed_seconds = as.numeric(difftime(Sys.time(), started, units = "secs"))
  ),
  file.path(outdir, "bsm_summary.json"),
  auto_unbox = TRUE,
  pretty = TRUE,
  digits = NA
)
cat("\nReusable BSM run completed in", round(as.numeric(difftime(Sys.time(), started, units = "secs")), 3), "seconds.\n")
