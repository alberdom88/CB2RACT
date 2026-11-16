#!/usr/bin/env bash
#
# End-to-end CB2 agonist/antagonist prediction pipeline.
#
#   1. build_knime_input.py : SIFt CSV -> KNIME query set (Title + 176 bits)
#   2. KNIME batch          : ensemble of 50 LibSVM models -> raw predictions
#   3. merge_predictions.py : raw predictions -> Title / prediction / probability
#
# Intermediate files live in a private temporary directory that is removed on
# exit, whether the run succeeds or fails.
#
# Usage:
#   export KNIME=/home/alberdom/knime/knime_5.2.6/knime
#   export TS_BESTDS=/data/cb2/TS_BESTDS_x_wf.csv
#   ./pipeline.sh input_sift.csv [results.csv]
#
# Environment variables:
#   KNIME       (required) KNIME executable
#   TS_BESTDS   (required) training set CSV
#   WORKFLOW    workflow file         (default: model_cli.knwf next to this script)
#   PYTHON      python interpreter    (default: python3)
#   SCRIPT_DIR  where the two .py live (default: directory of this script)
#   KNIME_XMX   JVM heap for KNIME    (default: unset, KNIME decides)

set -euo pipefail

usage() {
    sed -n '3,25p' "$0" | sed 's/^#\s\?//'
    exit "${1:-1}"
}

die() {
    printf 'pipeline: error: %s\n' "$*" >&2
    exit 1
}

step() {
    printf '\n=== [%s/3] %s\n' "$1" "$2"
}

# Absolute path for a file that may not exist yet (KNIME needs absolute paths).
# $2 is a label used in the error message.
abspath() {
    local dir base
    dir=$(dirname -- "$1")
    base=$(basename -- "$1")
    cd -- "$dir" 2>/dev/null || die "${2:-path}: directory not found: $dir"
    printf '%s/%s\n' "$(pwd -P)" "$base"
}

# ---------------------------------------------------------------- arguments
case "${1:-}" in
    -h|--help) usage 0 ;;
    "")        usage 1 ;;
esac

KEEP_TEMP=0
ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --keep-temp) KEEP_TEMP=1 ;;
        -h|--help)   usage 0 ;;
        -*)          die "unknown option: $1" ;;
        *)           ARGS+=("$1") ;;
    esac
    shift
done

[ "${#ARGS[@]}" -ge 1 ] || usage 1
[ "${#ARGS[@]}" -le 2 ] || die "too many arguments (expected input [output])"

INPUT=$(abspath "${ARGS[0]}" "input")
[ -f "$INPUT" ] || die "input file not found: $INPUT"

if [ "${#ARGS[@]}" -eq 2 ]; then
    OUTPUT=$(abspath "${ARGS[1]}" "output")
else
    stem=${INPUT%.csv}
    OUTPUT="${stem}_predictions.csv"
fi
[ "$INPUT" != "$OUTPUT" ] || die "input and output are the same file"

# ------------------------------------------------------------- environment
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPT_DIR=${SCRIPT_DIR:-$HERE}
WORKFLOW=${WORKFLOW:-$HERE/model_cli.knwf}
PYTHON=${PYTHON:-python3}

[ -n "${KNIME:-}" ]     || die "KNIME is not set (path to the KNIME executable)"
[ -n "${TS_BESTDS:-}" ] || die "TS_BESTDS is not set (path to TS_BESTDS_x_wf.csv)"
[ -x "$KNIME" ]         || die "KNIME is not executable: $KNIME"

TRAINING=$(abspath "$TS_BESTDS" "TS_BESTDS")
[ -f "$TRAINING" ] || die "training set not found: $TRAINING"

WORKFLOW=$(abspath "$WORKFLOW" "WORKFLOW")
[ -f "$WORKFLOW" ] || die "workflow not found: $WORKFLOW (set WORKFLOW=...)"

BUILD_SCRIPT="$SCRIPT_DIR/build_knime_input.py"
MERGE_SCRIPT="$SCRIPT_DIR/merge_predictions.py"
for script in "$BUILD_SCRIPT" "$MERGE_SCRIPT"; do
    [ -f "$script" ] || die "script not found: $script (set SCRIPT_DIR=...)"
done
command -v "$PYTHON" >/dev/null 2>&1 || die "python interpreter not found: $PYTHON"

mkdir -p -- "$(dirname -- "$OUTPUT")" || die "cannot create output directory"

# ------------------------------------------------------- temporary workspace
TMPDIR_RUN=$(mktemp -d "${TMPDIR:-/tmp}/cb2_pipeline.XXXXXXXX") \
    || die "cannot create temporary directory"

cleanup() {
    local status=$?
    if [ "$KEEP_TEMP" -eq 1 ]; then
        printf '\nintermediate files kept in %s\n' "$TMPDIR_RUN"
    else
        rm -rf -- "$TMPDIR_RUN"
    fi
    return $status
}
trap cleanup EXIT

QUERY="$TMPDIR_RUN/query_knime.csv"
RAW_PRED="$TMPDIR_RUN/predictions_raw.csv"
WORKSPACE="$TMPDIR_RUN/knime_workspace"

printf 'input    : %s\n' "$INPUT"
printf 'training : %s\n' "$TRAINING"
printf 'workflow : %s\n' "$WORKFLOW"
printf 'output   : %s\n' "$OUTPUT"

# ------------------------------------------------------------------ step 1
step 1 "Building the KNIME query set"
"$PYTHON" "$BUILD_SCRIPT" "$INPUT" -o "$QUERY" \
    || die "build_knime_input.py failed"
[ -s "$QUERY" ] || die "build_knime_input.py produced no query set"

# ------------------------------------------------------------------ step 2
step 2 "Running the KNIME workflow (50 LibSVM models, this takes a while)"
knime_args=(
    -nosplash
    -consoleLog
    --launcher.suppressErrors
    -application org.knime.product.KNIME_BATCH_APPLICATION
    -data "$WORKSPACE"
    -reset
    -nosave
    -failonloaderror
    "-workflowFile=$WORKFLOW"
    "-workflow.variable=input_csv,$QUERY,String"
    "-workflow.variable=training_csv,$TRAINING,String"
    "-workflow.variable=output_csv,$RAW_PRED,String"
)
if [ -n "${KNIME_XMX:-}" ]; then
    knime_args+=(-vmargs "-Xmx${KNIME_XMX}")
fi

if ! "$KNIME" "${knime_args[@]}"; then
    die "KNIME exited with an error (see the log above)"
fi
[ -s "$RAW_PRED" ] || die "KNIME did not write any predictions to $RAW_PRED"

# ------------------------------------------------------------------ step 3
step 3 "Merging predictions with compound names"
"$PYTHON" "$MERGE_SCRIPT" "$QUERY" "$RAW_PRED" "$OUTPUT" \
    || die "merge_predictions.py failed"
[ -s "$OUTPUT" ] || die "no output written to $OUTPUT"

# ----------------------------------------------------------------- summary
rows=$(( $(wc -l < "$OUTPUT") - 1 ))
printf '\n%s\n' "----------------------------------------------"
printf 'DONE\n'
printf 'Compounds predicted : %s\n' "$rows"
printf 'Output file         : %s\n' "$OUTPUT"
