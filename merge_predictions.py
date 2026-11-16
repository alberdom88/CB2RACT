#!/usr/bin/env python3
"""Merge a KNIME query set with the ensemble prediction table it produced.

The KNIME workflow reads the query CSV without row IDs, so KNIME generates the
keys Row0, Row1, ... in file order. The prediction table keeps those keys in
its "RowID_Arr[0]" column, which is how a prediction is matched back to the
compound it belongs to: Row<N> is the N-th data row of the query CSV (0-based).

Output columns:
    Title        compound identifier taken from the query CSV
    prediction   "agonist" for label a, "antagonist" for label i
    probability  probability of the predicted class: P(a) for a, 1 - P(a) for i

Example:
    python3 merge_predictions.py test_knime.csv test_knime_out.csv results.csv
"""

import argparse
import csv
import re
import sys

LABEL_NAMES = {"a": "agonist", "i": "antagonist"}
ROW_KEY_RE = re.compile(r"^Row(\d+)$")


def die(message):
    sys.exit(f"error: {message}")


def find_column(fieldnames, wanted, description):
    """Return the exact column name, matching case-insensitively as a fallback."""
    if wanted in fieldnames:
        return wanted
    lowered = {name.lower(): name for name in fieldnames}
    if wanted.lower() in lowered:
        return lowered[wanted.lower()]
    die(f"{description} column {wanted!r} not found. Columns present: {', '.join(fieldnames)}")


def read_titles(path, id_column):
    """Read the query CSV and return its identifiers in file order."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            die(f"{path} is empty")
        column = find_column(reader.fieldnames, id_column, "identifier")
        titles = []
        for line, row in enumerate(reader, start=2):
            value = (row.get(column) or "").strip()
            if not value:
                die(f"{path} line {line}: empty {column!r}")
            titles.append(value)
    if not titles:
        die(f"{path} contains no data rows")
    return titles


def read_predictions(path, key_column, label_column, prob_column):
    """Read the KNIME prediction table, keyed by the row index it refers to."""
    predictions = {}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            die(f"{path} is empty")
        key_col = find_column(reader.fieldnames, key_column, "row key")
        label_col = find_column(reader.fieldnames, label_column, "prediction")
        prob_col = find_column(reader.fieldnames, prob_column, "probability")

        for line, row in enumerate(reader, start=2):
            key = (row.get(key_col) or "").strip()
            if not key:
                continue  # trailing blank line
            match = ROW_KEY_RE.match(key)
            if match is None:
                die(f"{path} line {line}: row key {key!r} is not of the form Row<N>")
            index = int(match.group(1))
            if index in predictions:
                die(f"{path} line {line}: row key {key!r} appears more than once")

            label = (row.get(label_col) or "").strip().strip('"')
            if label not in LABEL_NAMES:
                die(f"{path} line {line}: unexpected label {label!r}, "
                    f"expected one of {', '.join(sorted(LABEL_NAMES))}")

            raw_prob = (row.get(prob_col) or "").strip()
            try:
                prob_a = float(raw_prob)
            except ValueError:
                die(f"{path} line {line}: probability {raw_prob!r} is not a number")
            if not 0.0 <= prob_a <= 1.0:
                die(f"{path} line {line}: probability {prob_a} is outside [0, 1]")

            predictions[index] = (label, prob_a)
    if not predictions:
        die(f"{path} contains no predictions")
    return predictions


def main():
    parser = argparse.ArgumentParser(
        description="Merge a KNIME query set with its ensemble predictions.")
    parser.add_argument("query_csv", help="query set given to the workflow (has the Title column)")
    parser.add_argument("predictions_csv", help="prediction table written by the workflow")
    parser.add_argument("output_csv", help="CSV file to write")
    parser.add_argument("--id-column", default="Title",
                        help="identifier column in the query set (default: Title)")
    parser.add_argument("--key-column", default="RowID_Arr[0]",
                        help="row key column in the prediction table (default: RowID_Arr[0])")
    parser.add_argument("--label-column", default="Mode(Prediction (LABEL))",
                        help="predicted label column (default: Mode(Prediction (LABEL)))")
    parser.add_argument("--prob-column", default="Mean(P (LABEL=a))",
                        help="P(a) column (default: Mean(P (LABEL=a)))")
    parser.add_argument("--decimals", type=int, default=None,
                        help="round the probability to this many decimals "
                             "(default: keep full precision)")
    parser.add_argument("--allow-missing", action="store_true",
                        help="skip compounds without a prediction instead of failing")
    args = parser.parse_args()

    titles = read_titles(args.query_csv, args.id_column)
    predictions = read_predictions(args.predictions_csv, args.key_column,
                                   args.label_column, args.prob_column)

    unknown = sorted(i for i in predictions if i >= len(titles))
    if unknown:
        die(f"{args.predictions_csv} refers to row(s) "
            f"{', '.join('Row%d' % i for i in unknown[:5])}"
            f"{' ...' if len(unknown) > 5 else ''}, but {args.query_csv} has only "
            f"{len(titles)} data row(s). The two files do not belong to the same run.")

    missing = [i for i in range(len(titles)) if i not in predictions]
    if missing and not args.allow_missing:
        die(f"no prediction for {len(missing)} compound(s), first missing: "
            f"{titles[missing[0]]} (Row{missing[0]}). "
            f"Re-run with --allow-missing to skip them.")

    written = 0
    with open(args.output_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Title", "prediction", "probability"])
        for index, title in enumerate(titles):
            if index not in predictions:
                continue
            label, prob_a = predictions[index]
            # probability of the class that was actually predicted
            probability = prob_a if label == "a" else 1.0 - prob_a
            if args.decimals is not None:
                probability = round(probability, args.decimals)
            writer.writerow([title, LABEL_NAMES[label], probability])
            written += 1

    print(f"wrote {written} row(s) to {args.output_csv}")
    if missing:
        print(f"skipped {len(missing)} compound(s) without a prediction", file=sys.stderr)


if __name__ == "__main__":
    main()
