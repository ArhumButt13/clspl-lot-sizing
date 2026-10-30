# Multi-Level Capacitated Lot-Sizing with Linked Lot Sizes (CLSPL)

Python + Gurobi implementation of the multi-level Capacitated Lot-Sizing Problem with Linked Lot Sizes, using the Inventory-and-Lot-Size formulation of Suerie & Stadtler (2003). Developed for the Management Science course at Europa-Universität Viadrina (Summer Semester 2026).

## What it does

Decides production quantities, inventory, new setups, and carried-over setups for every item and period, minimizing total holding + setup cost across a multi-level bill of materials.

Implemented equations: (1), (16), (3)–(7), (10)–(15).

## Project structure

```
src/
  data_reader.py   # parses and validates the .dat instance files
  model.py         # builds and solves the Gurobi model, exports results
output/            # result CSVs per instance + results_summary.csv
instances/         # place the course .dat files here (not included)
```

## Requirements

- Python 3.12
- Gurobi 13.0.2 with a valid license (free academic license available from Gurobi)

```
pip install -r requirements.txt
```

## Usage

1. Put the four instance files in `instances/`:
   `A6_G001545_MLCLS.dat`, `B6_G511541_MLCLS.dat`, `C20_K805132_MLCLS.dat`, `D20_G819321_MLCLS.dat`
2. Run:
   ```
   python src/model.py
   ```
3. Results are written to `output/` (and LP files to `model_debug/`).

## Data handling

- Supplied initial inventories are used; final inventory is constrained to zero.
- No initial setup state is supplied, so `W[j,1] = 0`.
- Each item is assigned to exactly one resource (positive production-capacity entry).
- Big-M is computed per item and period as available capacity ÷ unit capacity requirement.
- Overtime data are read but not used (outside the selected equations).
- D20: the last demand row has 16 instead of 20 entries, all zero. Four trailing zeros are added. Padding is only applied when every supplied entry is zero; otherwise an error is raised.

## Results (900 s time limit, 8 threads)

| Instance | Items | Periods | Status | Objective | Best bound | MIP gap | Runtime |
|---|---|---|---|---|---|---|---|
| A6 | 10 | 6 | Optimal | 8,820.999 | 8,820.999 | 0.00% | 0.405 s |
| B6 | 10 | 6 | Optimal | 8,887.332 | 8,887.332 | 0.00% | 0.389 s |
| C20 | 40 | 20 | Feasible incumbent (time limit) | 70,620.003 | 33,079.663 | 53.1582% | 900.060 s |
| D20 | 40 | 20 | Feasible incumbent (time limit) | 261,518.260 | 155,128.163 | 40.6817% | 900.123 s |

A6 and B6 are proven optimal. C20 and D20 are feasible incumbents at the time limit and are **not** proven optimal.

Environment: Windows 11, Intel Core i5-1135G7, Python 3.12, Gurobi 13.0.2.

## Reference

Suerie, C., & Stadtler, H. (2003). The capacitated lot-sizing problem with linked lot sizes. *Management Science*, 49(8), 1039–1054.

## Authors

Muhammad Arhum Butt, Ali Shayan Maqsood — Group 4, supervised by Prof. Dr. Christian Almeder.

## Note

The instance data files and assignment document are course materials and are not included in this repository.
