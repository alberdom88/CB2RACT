# Explainable Machine Learning Reveals the Molecular Determinants of CB2R Functional Modulation

Structure-based classification of cannabinoid receptor 2 (CB2R) ligands as
**agonists** or **antagonists** from protein–ligand interaction fingerprints
(SIFt).

Compounds are docked into two CB2R conformations, the best-scoring pose is
converted into a 176-bit interaction fingerprint, and an ensemble of 50 LibSVM
models — each trained on a different class-balanced subsample of the training
set — votes on the functional class. Because every descriptor is a specific
interaction with a specific residue, the model can be read back in structural
terms: the bits that drive a prediction point to the residues that distinguish
agonism from antagonism.

```
 ligands (SDF/MAE)
        │
        │  1. Glide docking into 6KPC_grid (agonist-bound) and 5ZTY_grid (antagonist-bound)
        ▼
 docked poses ──► best pose per compound
        │
        │  2. $SCHRODINGER/run interaction_fingerprints.py
        ▼
 fingerprint CSV (Title + 176 bits)
        │
        │  3. ./pipeline.sh  →  build_knime_input.py → KNIME (50 × LibSVM) → merge_predictions.py
        ▼
 predictions CSV (Title, prediction, probability)
```

## Repository contents

| File | Role |
|------|------|
| `pipeline.sh` | Orchestrates step 3 end to end |
| `build_knime_input.py` | Keeps `Title` + the 176 reference bits, in reference order |
| `model_cli.knwf` | KNIME workflow: 50 balanced LibSVM models + consensus |
| `merge_predictions.py` | Attaches compound names, maps labels, reports probabilities |
| `interaction_fingerprints.py` | Generates the SIFt CSV from docked poses |
| `6KPC_grid` | Glide grid, agonist-bound CB2R |
| `5ZTY_grid` | Glide grid, antagonist-bound CB2R |
| `TS_BESTDS_x_wf.csv` | Training set: `LABEL` (`a`/`i`) + the same 176 bits |

## Requirements

Tested with **KNIME Analytics Platform 5.2.6**.

- **KNIME 5.2.6**, with these extensions installed:
  - *KNIME Weka Data Mining Integration (3.7)* — provides the `LibSVM (3.7)` and
    `Weka Predictor (3.7)` nodes
  - *KNIME Optimization* — provides `Parameter Optimization Loop Start`
- **Schrödinger Suite** with a Glide licence (steps 1 and 2)
- **Python 3** with **pandas** (`build_knime_input.py`); `merge_predictions.py`
  uses only the standard library
- **Bash** 4 or newer

## Setup

Define the following environment variables once per shell session:

```bash
export KNIME=/path/to/knime_5.2.6/knime          # KNIME executable
export TS_BESTDS=/path/to/TS_BESTDS_x_wf.csv     # training set
export WORKFLOW=/path/to/model_cli.knwf          # KNIME workflow
export SCRIPT_DIR=/path/to/repo                  # directory holding the two .py scripts
```

`KNIME` and `TS_BESTDS` are mandatory. `WORKFLOW` and `SCRIPT_DIR` default to
the directory containing `pipeline.sh`, so they can be omitted when the
repository is kept intact.

Optional:

```bash
export PYTHON=python3.11   # interpreter to use (default: python3)
export KNIME_XMX=16g       # JVM heap for KNIME (default: KNIME decides)
```

Make the pipeline executable after cloning:

```bash
chmod +x pipeline.sh
```

## Usage

### 1. Docking with Glide

Dock the compound library into both CB2R conformations, using the two grids
provided in this repository:

- `6KPC_grid` — agonist-bound CB2R ([PDB 6KPC](https://www.rcsb.org/structure/6KPC), X-ray, 3.2 Å)
- `5ZTY_grid` — antagonist-bound CB2R ([PDB 5ZTY](https://www.rcsb.org/structure/5ZTY), CB2R–AM10257, X-ray, 2.8 Å)

Ligands must be prepared beforehand (LigPrep or equivalent: correct
protonation at physiological pH, ring conformers, stereochemistry).

```bash
# one Glide job per grid
$SCHRODINGER/glide dock_6KPC.in -OVERWRITE -HOST localhost:8 -WAIT
$SCHRODINGER/glide dock_5ZTY.in -OVERWRITE -HOST localhost:8 -WAIT
```

A minimal `dock_6KPC.in` looks like this (adjust precision, sampling and pose
count to your protocol):

```
GRIDFILE   /path/to/6KPC_grid.zip
LIGANDFILE /path/to/ligands_prepared.maegz
PRECISION  SP
POSE_OUTTYPE ligandlib_sd
```

### 2. Best pose and interaction fingerprints

Keep, for each compound, the single pose with the best docking score across
both dockings — one row per compound. For example:

```bash
$SCHRODINGER/utilities/glide_sort -r best_poses.maegz -best_by_title \
    dock_6KPC_lib.maegz dock_5ZTY_lib.maegz
```

Then generate the interaction fingerprints as CSV:

```bash
$SCHRODINGER/run interaction_fingerprints.py best_poses.maegz -o fingerprints.csv
```

Run the script with `--help` for the options it accepts.

The resulting CSV must contain a `Title` column (the compound identifier) and
the 176 fingerprint bits, named `A<residue>_<interaction type>` — for example
`A117_aromatic` or `A258_hydrophobic`. Any additional column (docking score,
pose number, and so on) is dropped automatically in step 3. The expected
176-bit layout is hard-coded in `build_knime_input.py` and matches the
training set; a missing bit stops the run with a list of what is absent.

### 3. Prediction pipeline

```bash
./pipeline.sh fingerprints.csv predictions.csv
```

The output argument is optional: omitting it writes
`<input>_predictions.csv` next to the input file.

The pipeline runs the three stages in sequence and reports progress. Relative
paths are resolved to absolute ones, because KNIME in batch mode requires
them. Intermediate files (the KNIME query set and the raw prediction table)
are written to a private temporary directory that is removed on exit, whether
the run succeeds or fails; pass `--keep-temp` to retain them for inspection.

Expect the KNIME stage to dominate the runtime: 50 SVM models are trained from
scratch on every run, since the ensemble is rebuilt rather than loaded from
disk.

## Output

A CSV file with one row per compound, in the same order as the input:

| Column | Content |
|--------|---------|
| `Title` | Compound identifier, taken from the input fingerprint CSV |
| `prediction` | `agonist` (internal label `a`) or `antagonist` (internal label `i`) |
| `probability` | Probability of the predicted class, in `[0, 1]` |

```csv
Title,prediction,probability
AGO_EC50_CHEMBL391412,agonist,0.6242728629739845
AGO_EC50_CHEMBL5564027,agonist,0.6883123907066034
AGO_EC50_CHEMBL5406251,agonist,0.7907197073103851
```

## Citation

If you use this code, please cite:

> *Explainable Machine Learning Reveals the Molecular Determinants of CB2R
> Functional Modulation* — reference to be completed on publication.


