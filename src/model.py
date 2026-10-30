"""
model.py
========

Group 4 - CLSPL Project (Suerie & Stadtler, 2003)

Multi-level Capacitated Lot-Sizing Problem with Linked Lot Sizes.
Inventory & Lot-size formulation as required by the professor:

    Equation (1):       objective (holding cost + setup cost)
    Equation (16):      multi-level inventory balance
    Equations (3)-(7):  capacity, setup forcing, domains, boundary conditions
    Equations (10)-(15): linked-lot constraints

This file solves all four provided test instances in a single run, exports
detailed CSV results per instance and a combined summary, and handles
infeasibility, time limits, and restricted-licence rejections robustly.
"""

import csv
import sys
import traceback
from pathlib import Path
from typing import Dict, Tuple, List, Optional

import gurobipy as gp
from gurobipy import GRB, GurobiError

from data_reader import read_instance


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Numerical clean-up threshold for CSV output. Any value with |v| below this
# is exported as exactly 0.0 (eliminates the cosmetic -0.000 artefacts).
ZERO_TOL: float = 1e-6

# Maximum solver runtime per instance, in seconds (professor allows 15 min).
TIME_LIMIT_SECONDS: int = 900

# The four required instance files, in the order required by the assignment.
INSTANCE_FILES: List[str] = [
    "A6_G001545_MLCLS.dat",
    "B6_G511541_MLCLS.dat",
    "C20_K805132_MLCLS.dat",
    "D20_G819321_MLCLS.dat",
]


# ---------------------------------------------------------------------------
# Helpers and status mapping
# ---------------------------------------------------------------------------

# Start of AI-generated code unmodified
def clean(value: float) -> float:
    """Return the value, snapping near-zero numbers to exactly 0.0.

    This eliminates cosmetic '-0.000' values that arise from solver
    floating-point noise on binary variables.
    """
    if value is None:
        return 0.0
    if abs(value) < ZERO_TOL:
        return 0.0
    return float(value)


def gurobi_status_name(status_code: int) -> str:
    """Translate a Gurobi status code into a readable name for the summary."""
    mapping = {
        GRB.LOADED: "LOADED",
        GRB.OPTIMAL: "OPTIMAL",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        GRB.UNBOUNDED: "UNBOUNDED",
        GRB.CUTOFF: "CUTOFF",
        GRB.ITERATION_LIMIT: "ITERATION_LIMIT",
        GRB.NODE_LIMIT: "NODE_LIMIT",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.SOLUTION_LIMIT: "SOLUTION_LIMIT",
        GRB.INTERRUPTED: "INTERRUPTED",
        GRB.NUMERIC: "NUMERIC",
        GRB.SUBOPTIMAL: "SUBOPTIMAL",
        GRB.INPROGRESS: "INPROGRESS",
        GRB.USER_OBJ_LIMIT: "USER_OBJ_LIMIT",
    }
    return mapping.get(status_code, f"UNKNOWN_{status_code}")


def instance_stub(instance_file_name: str) -> str:
    """Return the short identifier used as a prefix for output files.

    Example: 'A6_G001545_MLCLS.dat' -> 'A6_G001545'.
    """
    base = Path(instance_file_name).stem  # remove '.dat'
    if base.endswith("_MLCLS"):
        base = base[: -len("_MLCLS")]
    return base
# End of AI-generated code unmodified


# ---------------------------------------------------------------------------
# Data-integrity checks for the parsed instance
# ---------------------------------------------------------------------------


def _normalise_demand(
    demand_matrix: List[List[float]],
    expected_periods: int,
    expected_items: int,
) -> List[List[float]]:
    """
    Return a copy of the external-demand matrix in which short rows are
    safely padded with zeros, BUT ONLY when the existing values in that
    row are all zero.

    Rationale: in one supplied data file (D20) the last demand row was
    truncated to 16 zero values instead of the expected 20. Because all
    supplied values are zero, padding the row with more zeros cannot
    change the optimisation problem in any way - the missing entries are
    unambiguously zero. We refuse to silently pad a short row that
    contains any nonzero values, because in that case data is genuinely
    missing and the user must fix the input file.

    Raises ValueError if:
        - the number of demand rows does not equal expected_items, or
        - a short row contains nonzero values, or
        - a row is longer than expected_periods.
    """
    if len(demand_matrix) != expected_items:
        raise ValueError(
            f"External demand has {len(demand_matrix)} rows but the instance "
            f"declares {expected_items} items."
        )

    out: List[List[float]] = []
    for j, row in enumerate(demand_matrix):
        if len(row) == expected_periods:
            out.append(list(row))
        elif len(row) > expected_periods:
            raise ValueError(
                f"External demand row {j + 1} has {len(row)} columns, "
                f"more than the declared T = {expected_periods} periods."
            )
        else:
            # row is shorter than expected_periods
            if any(abs(v) > ZERO_TOL for v in row):
                raise ValueError(
                    f"External demand row {j + 1} has only {len(row)} "
                    f"columns (expected {expected_periods}) and contains "
                    f"nonzero values: {row}. Cannot safely pad - please "
                    f"fix the input file."
                )
            missing = expected_periods - len(row)
            print(
                f"  WARNING: external-demand row {j + 1} has only "
                f"{len(row)} columns (expected {expected_periods}); all "
                f"supplied values are zero, padding {missing} trailing "
                f"zero(s)."
            )
            out.append(list(row) + [0.0] * missing)

    return out


def _check_matrix_shape(
    matrix: List[List[float]],
    expected_rows: int,
    expected_cols: int,
    name: str,
) -> None:
    """
    Verify that `matrix` has exactly expected_rows x expected_cols. This
    is a strict check (no padding) used for matrices where a wrong shape
    would silently change the optimisation model - BOM, capacity limits,
    production-capacity, and setup-capacity.

    Raises ValueError on any mismatch.
    """
    if len(matrix) != expected_rows:
        raise ValueError(
            f"Matrix '{name}' has {len(matrix)} rows but expected "
            f"{expected_rows}."
        )
    for i, row in enumerate(matrix):
        if len(row) != expected_cols:
            raise ValueError(
                f"Matrix '{name}' row {i + 1} has {len(row)} columns "
                f"but expected {expected_cols}. Cannot safely continue - "
                f"please fix the input file."
            )




def find_item_resources(instance: dict) -> Dict[int, int]:
    """
    Determine which resource produces each item.

    The production-capacity matrix has one row per resource and one column
    per item. A positive entry means the item uses that resource.
    The CLSPL formulation assumes each item is assigned to exactly one
    resource.
    """
    number_of_items = instance["items"]
    number_of_resources = instance["resources"]

    item_resource: Dict[int, int] = {}

    for j in range(number_of_items):
        assigned_resources = [
            m
            for m in range(number_of_resources)
            if instance["production_capacity"][m][j] > 0
        ]

        if len(assigned_resources) != 1:
            raise ValueError(
                f"Item {j + 1} must belong to exactly one resource, "
                f"but it belongs to {len(assigned_resources)} resources."
            )

        item_resource[j] = assigned_resources[0]

    return item_resource

# Start of Ai Generated code modified
def calculate_big_m(
    instance: dict,
    item_resource: Dict[int, int],
) -> Dict[Tuple[int, int], float]:
    """
    Calculate a valid production upper bound B[j,t].

    B[j,t] = capacity[m,t] / production_usage[m,j], where m is the resource
    assigned to item j. This is the maximum production if the entire
    resource capacity were devoted to item j. Setup time is NOT subtracted,
    because when W[j,t] = 1 the setup is carried over and no new setup time
    is consumed.
    """
    number_of_items = instance["items"]
    number_of_periods = instance["periods"]

    big_m: Dict[Tuple[int, int], float] = {}

    for j in range(number_of_items):
        m = item_resource[j]
        production_time_per_unit = instance["production_capacity"][m][j]

        if production_time_per_unit <= 0:
            raise ValueError(
                f"Item {j + 1} has invalid production capacity usage."
            )

        for t in range(number_of_periods):
            available_capacity = instance["capacity_limits"][m][t]
            big_m[j, t] = available_capacity / production_time_per_unit

    return big_m
# End of AI-generated code modified


# ---------------------------------------------------------------------------
# Model construction (formulation unchanged from validated version)
# ---------------------------------------------------------------------------

def build_clspl_model(instance: dict) -> Tuple[gp.Model, dict]:
    """
    Build the regular Inventory & Lot-size CLSPL formulation requested
    by the professor: equations (1), (16), (3)-(7), (10)-(15).
    """
    model = gp.Model("Group4_MultiLevel_CLSPL")

    number_of_items = instance["items"]
    number_of_periods = instance["periods"]
    number_of_resources = instance["resources"]

    # -----------------------------------------------------------------
    # Data-integrity checks before the model is built.
    #
    # External demand: short rows are only tolerated if they are
    # entirely zero (a benign data-file defect, e.g. D20's last row).
    # All other matrices are checked strictly - a wrong shape there
    # would silently change the optimisation problem, which is not
    # acceptable, so we raise a clear error instead.
    # -----------------------------------------------------------------
    demand_matrix = _normalise_demand(
        instance["external_demand"], number_of_periods, number_of_items
    )
    _check_matrix_shape(
        instance["bom"], number_of_items, number_of_items, "BOM"
    )
    _check_matrix_shape(
        instance["capacity_limits"],
        number_of_resources,
        number_of_periods,
        "CapacityLimitsForEachResourceAndPeriod",
    )
    _check_matrix_shape(
        instance["production_capacity"],
        number_of_resources,
        number_of_items,
        "CapacityNeedsForProductionForEachResourceAndItem",
    )
    _check_matrix_shape(
        instance["setup_capacity"],
        number_of_resources,
        number_of_items,
        "CapacityNeedsForSetupForEachResourceAndItem",
    )

    bom_matrix = instance["bom"]
    capacity_matrix = instance["capacity_limits"]
    production_matrix = instance["production_capacity"]
    setup_cap_matrix = instance["setup_capacity"]

    items = range(number_of_items)
    periods = range(number_of_periods)
    resources = range(number_of_resources)

    item_resource = find_item_resources(instance)

    items_on_resource = {
        m: [j for j in items if item_resource[j] == m] for m in resources
    }

    big_m = calculate_big_m(instance, item_resource)

    # -----------------------------------------------------------------
    # Decision variables
    # -----------------------------------------------------------------

    # X[j,t]: production quantity of item j in period t
    X = model.addVars(items, periods, lb=0.0, vtype=GRB.CONTINUOUS, name="X")

    # I[j,t]: inventory of item j at end of period t
    I = model.addVars(items, periods, lb=0.0, vtype=GRB.CONTINUOUS, name="I")

    # Y[j,t]: 1 if a new setup for item j is performed in period t
    Y = model.addVars(items, periods, vtype=GRB.BINARY, name="Y")

    # W[j,t]: 1 if the setup state for item j is carried over from t-1 to t
    W = model.addVars(items, periods, vtype=GRB.BINARY, name="W")

    # Q[m,t]: helper variable for the single-item linked-through-period case
    # Eq. (13) implies Q[m,t] <= 1 because Y[j,t] + Q[m,t] <= 1 with Y >= 0.
    Q = model.addVars(
        resources, periods, lb=0.0, vtype=GRB.CONTINUOUS, name="Q"
    )

    # -----------------------------------------------------------------
    # Equation (1): objective
    # -----------------------------------------------------------------
    # Holding cost is charged for t = 1,..,T-1 (i.e. range(T-1) in Python).
    # Final inventory is forced to zero by Eq. (5).
    holding_cost = gp.quicksum(
        instance["holding_costs"][j] * I[j, t]
        for j in items
        for t in range(number_of_periods - 1)
    )

    setup_cost = gp.quicksum(
        instance["setup_costs"][j] * Y[j, t] for j in items for t in periods
    )

    model.setObjective(holding_cost + setup_cost, GRB.MINIMIZE)

    # -----------------------------------------------------------------
    # Equation (16): multi-level inventory balance
    # -----------------------------------------------------------------
    for j in items:
        for t in periods:
            if t == 0:
                previous_inventory = instance["initial_inventory"][j]
            else:
                previous_inventory = I[j, t - 1]

            dependent_demand = gp.quicksum(
                bom_matrix[j][k] * X[k, t]
                for k in items
                if bom_matrix[j][k] != 0
            )

            model.addConstr(
                previous_inventory + X[j, t]
                == I[j, t]
                + demand_matrix[j][t]
                + dependent_demand,
                name=f"inv_balance_item_{j + 1}_period_{t + 1}",
            )

    # Equation (5): final inventory = 0
    for j in items:
        model.addConstr(
            I[j, number_of_periods - 1] == 0,
            name=f"final_inv_item_{j + 1}",
        )

    # -----------------------------------------------------------------
    # Equation (3): capacity constraints
    # -----------------------------------------------------------------
    for m in resources:
        for t in periods:
            production_capacity_used = gp.quicksum(
                production_matrix[m][j] * X[j, t]
                for j in items_on_resource[m]
            )
            setup_capacity_used = gp.quicksum(
                setup_cap_matrix[m][j] * Y[j, t]
                for j in items_on_resource[m]
            )
            model.addConstr(
                production_capacity_used + setup_capacity_used
                <= capacity_matrix[m][t],
                name=f"capacity_resource_{m + 1}_period_{t + 1}",
            )

    # -----------------------------------------------------------------
    # Equation (4) for linked lots: production allowed if Y=1 OR W=1
    # -----------------------------------------------------------------
    for j in items:
        for t in periods:
            model.addConstr(
                X[j, t] <= big_m[j, t] * (Y[j, t] + W[j, t]),
                name=f"setup_forcing_item_{j + 1}_period_{t + 1}",
            )

    # -----------------------------------------------------------------
    # Equation (10): at most one setup carried over per resource per period
    # -----------------------------------------------------------------
    for m in resources:
        for t in range(1, number_of_periods):
            model.addConstr(
                gp.quicksum(W[j, t] for j in items_on_resource[m]) <= 1,
                name=f"one_carryover_resource_{m + 1}_period_{t + 1}",
            )

    # -----------------------------------------------------------------
    # Equation (11): W[j,t] <= Y[j,t-1] + W[j,t-1]
    # -----------------------------------------------------------------
    for j in items:
        for t in range(1, number_of_periods):
            model.addConstr(
                W[j, t] <= Y[j, t - 1] + W[j, t - 1],
                name=f"carryover_chain_item_{j + 1}_period_{t + 1}",
            )

    # -----------------------------------------------------------------
    # Equation (12): W[j,t+1] + W[j,t] <= 1 + Q[m,t]  for t = 1..T-1
    # -----------------------------------------------------------------
    for j in items:
        m = item_resource[j]
        for t in range(number_of_periods - 1):
            model.addConstr(
                W[j, t + 1] + W[j, t] <= 1 + Q[m, t],
                name=f"double_link_item_{j + 1}_period_{t + 1}",
            )

    # -----------------------------------------------------------------
    # Equation (13): Y[j,t] + Q[m,t] <= 1 for every j in R_m
    # -----------------------------------------------------------------
    for m in resources:
        for j in items_on_resource[m]:
            for t in periods:
                model.addConstr(
                    Y[j, t] + Q[m, t] <= 1,
                    name=(
                        f"no_setup_in_single_item_mode_"
                        f"resource_{m + 1}_item_{j + 1}_period_{t + 1}"
                    ),
                )

    # -----------------------------------------------------------------
    # Equations (14) and (15): boundary conditions
    # -----------------------------------------------------------------
    for j in items:
        model.addConstr(W[j, 0] == 0, name=f"initial_W_item_{j + 1}")


# Start of AI-generated code unmodified
    for m in resources:
        model.addConstr(Q[m, 0] == 0, name=f"initial_Q_resource_{m + 1}")
        model.addConstr(
            Q[m, number_of_periods - 1] == 0,
            name=f"final_Q_resource_{m + 1}",
        )

    model.update()

    variables = {
        "X": X,
        "I": I,
        "Y": Y,
        "W": W,
        "Q": Q,
        "item_resource": item_resource,
    }

    return model, variables



# ---------------------------------------------------------------------------
# Result export
# ---------------------------------------------------------------------------

# Start of AI-generated code unmodified
def export_item_results(
    output_path: Path,
    instance: dict,
    variables: dict,
) -> None:
    """Write detailed per-item, per-period results (X, I, Y, W) to CSV."""
    X = variables["X"]
    I = variables["I"]
    Y = variables["Y"]
    W = variables["W"]
    item_resource = variables["item_resource"]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "item_index",
                "item_name",
                "period",
                "X_production",
                "I_inventory",
                "Y_new_setup",
                "W_carried_setup",
                "assigned_resource",
            ]
        )

        for j in range(instance["items"]):
            for t in range(instance["periods"]):
                writer.writerow(
                    [
                        j + 1,
                        instance["item_names"][j],
                        t + 1,
                        clean(X[j, t].X),
                        clean(I[j, t].X),
                        int(round(clean(Y[j, t].X))),
                        int(round(clean(W[j, t].X))),
                        item_resource[j] + 1,
                    ]
                )

# End of AI-generated code unmodified
def export_q_results(
    output_path: Path,
    instance: dict,
    variables: dict,
) -> None:
    """Write Q-variable values per resource and period to CSV."""
    Q = variables["Q"]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["resource", "period", "Q_value"])

        for m in range(instance["resources"]):
            for t in range(instance["periods"]):
                writer.writerow([m + 1, t + 1, clean(Q[m, t].X)])


def write_summary_row(
    summary_rows: List[Dict[str, str]],
    row: Dict[str, str],
) -> None:
    """Append one row to the summary buffer."""
    summary_rows.append(row)


def save_summary(summary_path: Path, summary_rows: List[Dict[str, str]]) -> None:
    """Write the combined summary CSV (one row per instance)."""
    fieldnames = [
        "instance_file",
        "model_name",
        "items",
        "periods",
        "resources",
        "status_code",
        "status_name",
        "has_solution",
        "objective_value",
        "best_bound",
        "mip_gap",
        "runtime_seconds",
        "num_variables",
        "num_constraints",
        "explored_nodes",
        "solution_count",
        "notes",
    ]

    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in summary_rows:
            # Make sure every key exists; missing ones become empty strings.
            full = {name: row.get(name, "") for name in fieldnames}
            writer.writerow(full)



# ---------------------------------------------------------------------------


def solve_one_instance(
    instance_file_path: Path,
    output_folder: Path,
    debug_folder: Path,
) -> Dict[str, str]:
    """
    Build, solve, and export results for a single instance.
    Returns a dictionary that becomes one row of the summary CSV.
    Never raises: errors are caught and reported in the returned row.
    """
    file_name = instance_file_path.name
    stub = instance_stub(file_name)

    summary: Dict[str, str] = {
        "instance_file": file_name,
        "model_name": "",
        "items": "",
        "periods": "",
        "resources": "",
        "status_code": "",
        "status_name": "",
        "has_solution": "False",
        "objective_value": "",
        "best_bound": "",
        "mip_gap": "",
        "runtime_seconds": "",
        "num_variables": "",
        "num_constraints": "",
        "explored_nodes": "",
        "solution_count": "",
        "notes": "",
    }

    print("=" * 72)
    print(f"Instance: {file_name}")
    print("=" * 72)

    # ----- read -----
    try:
        print("  [1/4] Reading instance ...")
        instance = read_instance(instance_file_path)
    except Exception as exc:
        print(f"  ERROR while reading: {exc}")
        summary["status_name"] = "READ_ERROR"
        summary["notes"] = f"Read error: {exc}"
        return summary

    summary["model_name"] = str(instance.get("model_name", ""))
    summary["items"] = str(instance["items"])
    summary["periods"] = str(instance["periods"])
    summary["resources"] = str(instance["resources"])

    # ----- build -----
    try:
        print("  [2/4] Building model ...")
        model, variables = build_clspl_model(instance)
        model.Params.TimeLimit = TIME_LIMIT_SECONDS
        # Reduce log spam in batch mode; the per-instance progress is enough.
        model.Params.OutputFlag = 1

        lp_path = debug_folder / f"{stub}_model.lp"
        model.write(str(lp_path))
        print(f"        LP file written: {lp_path}")

        summary["num_variables"] = str(model.NumVars)
        summary["num_constraints"] = str(model.NumConstrs)

    except GurobiError as exc:
        # Restricted licence rejection or other Gurobi build error.
        print("  GUROBI ERROR while building model:")
        print(f"    {exc}")
        if "size-limited" in str(exc).lower() or "license" in str(exc).lower():
            summary["status_name"] = "LICENCE_ERROR"
            summary["notes"] = (
                "Restricted Gurobi licence rejected this model. "
                "An academic licence is required for this instance."
            )
            print(
                "  >>> Restricted licence appears too small for this model."
            )
            print("  >>> An academic Gurobi licence is required.")
        else:
            summary["status_name"] = "BUILD_ERROR"
            summary["notes"] = f"GurobiError: {exc}"
        return summary
    except Exception as exc:
        print("  ERROR while building model:")
        traceback.print_exc()
        summary["status_name"] = "BUILD_ERROR"
        summary["notes"] = f"Build error: {exc}"
        return summary

    # ----- solve -----
    try:
        print(f"  [3/4] Solving (time limit {TIME_LIMIT_SECONDS}s) ...")
        model.optimize()
    except GurobiError as exc:
        print("  GUROBI ERROR while solving:")
        print(f"    {exc}")
        if "size-limited" in str(exc).lower() or "license" in str(exc).lower():
            summary["status_name"] = "LICENCE_ERROR"
            summary["notes"] = (
                "Restricted Gurobi licence rejected this model during "
                "optimisation. An academic licence is required."
            )
        else:
            summary["status_name"] = "SOLVE_ERROR"
            summary["notes"] = f"GurobiError: {exc}"
        return summary
    except Exception as exc:
        print("  ERROR while solving:")
        traceback.print_exc()
        summary["status_name"] = "SOLVE_ERROR"
        summary["notes"] = f"Solve error: {exc}"
        return summary

    status_code = model.Status
    status_name = gurobi_status_name(status_code)
    summary["status_code"] = str(status_code)
    summary["status_name"] = status_name
    summary["runtime_seconds"] = f"{model.Runtime:.4f}"
    try:
        summary["explored_nodes"] = str(int(model.NodeCount))
    except Exception:
        summary["explored_nodes"] = ""
    summary["solution_count"] = str(model.SolCount)

    has_solution = model.SolCount > 0

    # ----- handle infeasibility -----
    if status_code == GRB.INFEASIBLE:
        print("  Model is INFEASIBLE - computing IIS ...")
        try:
            model.computeIIS()
            ilp_path = debug_folder / f"{stub}_infeasible.ilp"
            model.write(str(ilp_path))
            print(f"        IIS written: {ilp_path}")
            summary["notes"] = f"Infeasible. IIS file: {ilp_path.name}"
        except Exception as exc:
            print(f"  Could not compute IIS: {exc}")
            summary["notes"] = f"Infeasible. IIS computation failed: {exc}"
        return summary

    
    if status_code == GRB.TIME_LIMIT and has_solution:
        summary["status_name"] = "TIME_LIMIT_WITH_SOLUTION"
        summary["notes"] = (
            "Time limit hit. Incumbent solution exported; "
            "see best_bound and mip_gap for quality."
        )
    elif status_code == GRB.TIME_LIMIT and not has_solution:
        summary["status_name"] = "TIME_LIMIT_NO_SOLUTION"
        summary["notes"] = "Time limit hit without any feasible solution."
        print("  Time limit reached, no feasible solution available.")
        return summary

    if not has_solution:
        # Any other status with no solution: just record and move on.
        summary["notes"] = summary["notes"] or (
            f"No solution available (status {status_name})."
        )
        print(f"  No feasible solution available (status {status_name}).")
        return summary

    # ----- export solution -----
    summary["has_solution"] = "True"
    try:
        summary["objective_value"] = f"{model.ObjVal:.6f}"
    except Exception:
        summary["objective_value"] = ""

    try:
        summary["best_bound"] = f"{model.ObjBound:.6f}"
    except Exception:
        summary["best_bound"] = ""

    try:
        summary["mip_gap"] = f"{model.MIPGap:.6f}"
    except Exception:
        summary["mip_gap"] = ""

    print("  [4/4] Exporting results ...")
    items_csv = output_folder / f"{stub}_item_results.csv"
    q_csv = output_folder / f"{stub}_Q_results.csv"

    try:
        export_item_results(items_csv, instance, variables)
        print(f"        Item-level results: {items_csv}")
    except Exception as exc:
        print(f"  ERROR exporting item results: {exc}")
        summary["notes"] = (summary["notes"] + f"; export error: {exc}").strip(
            "; "
        )
#Start of AI generated code
    try:
        export_q_results(q_csv, instance, variables)
        print(f"        Q results        : {q_csv}")
    except Exception as exc:
        print(f"  ERROR exporting Q results: {exc}")
        summary["notes"] = (summary["notes"] + f"; export error: {exc}").strip(
            "; "
        )

    print(
        f"  Status   : {summary['status_name']}\n"
        f"  Objective: {summary['objective_value']}\n"
        f"  Runtime  : {summary['runtime_seconds']} s\n"
        f"  MIP gap  : {summary['mip_gap']}"
    )

    # Dispose of the model to release Gurobi memory before the next instance.
    model.dispose()

    return summary
# End of AI-generated code unmodified

def main() -> None:
    """Run all four instances in sequence and write all output files."""
    project_folder = Path(__file__).resolve().parent.parent
    instances_folder = project_folder / "instances"
    output_folder = project_folder / "output"
    debug_folder = project_folder / "model_debug"

    output_folder.mkdir(parents=True, exist_ok=True)
    debug_folder.mkdir(parents=True, exist_ok=True)

    print()
    print("##" * 36)
    print("Group 4 - CLSPL Project (Suerie & Stadtler 2003)")
    print(f"Solving {len(INSTANCE_FILES)} instances with a "
          f"{TIME_LIMIT_SECONDS}-second limit each.")
    print("##" * 36)
    print()

    summary_rows: List[Dict[str, str]] = []

    for file_name in INSTANCE_FILES:
        instance_path = instances_folder / file_name

        if not instance_path.exists():
            print(f"!! Instance file missing: {instance_path}")
            summary_rows.append(
                {
                    "instance_file": file_name,
                    "status_name": "FILE_NOT_FOUND",
                    "notes": f"File not found at {instance_path}",
                    "has_solution": "False",
                }
            )
            continue

        try:
            row = solve_one_instance(instance_path, output_folder, debug_folder)
        except Exception as exc:
            # Catch-all: never let one instance abort the whole run.
            print(f"!! Unhandled error on {file_name}: {exc}")
            traceback.print_exc()
            row = {
                "instance_file": file_name,
                "status_name": "UNHANDLED_ERROR",
                "notes": f"Unhandled exception: {exc}",
                "has_solution": "False",
            }

        write_summary_row(summary_rows, row)
        print()

    summary_path = output_folder / "results_summary.csv"
    save_summary(summary_path, summary_rows)

    print("##" * 36)
    print(f"Summary written to: {summary_path}")
    print("##" * 36)


if __name__ == "__main__":
    main()
