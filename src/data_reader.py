from pathlib import Path


def read_instance(file_path: Path) -> dict:
    """
    Read one MLCLS .dat test instance and return its data
    inside a Python dictionary.
    """

    with file_path.open("r", encoding="utf-8", errors="replace") as file:
        lines = [line.strip() for line in file if line.strip()]

    data = {}
    index = 0

    if lines[index] != "Modelname":
        raise ValueError("Expected 'Modelname' section.")
    index += 1

    data["model_name"] = lines[index]
    index += 1

    if lines[index] != "NumberOfPeriods,Items,Resources":
        raise ValueError("Expected number section.")
    index += 1

    periods, items, resources = map(int, lines[index].split())
    data["periods"] = periods
    data["items"] = items
    data["resources"] = resources
    index += 1

    if lines[index] != (
        "SetupCost,HoldingCost,LeadTime,InitialInventory,NameOfItem"
    ):
        raise ValueError("Expected item-data section.")
    index += 1

    setup_costs = []
    holding_costs = []
    lead_times = []
    initial_inventory = []
    item_names = []

    for _ in range(items):
        parts = lines[index].split()

        setup_costs.append(float(parts[0]))
        holding_costs.append(float(parts[1]))
        lead_times.append(int(parts[2]))
        initial_inventory.append(float(parts[3]))
        item_names.append(parts[4])

        index += 1

    data["setup_costs"] = setup_costs
    data["holding_costs"] = holding_costs
    data["lead_times"] = lead_times
    data["initial_inventory"] = initial_inventory
    data["item_names"] = item_names

    if not lines[index].startswith("BOM"):
        raise ValueError("Expected BOM section.")
    index += 1

    bom = []

    for _ in range(items):
        row = list(map(float, lines[index].split()))
        bom.append(row)
        index += 1

    data["bom"] = bom

    if lines[index] != "ExternalDemandForEachItemAndPeriod":
        raise ValueError("Expected demand section.")
    index += 1

    external_demand = []

    for _ in range(items):
        row = list(map(float, lines[index].split()))
        external_demand.append(row)
        index += 1

    data["external_demand"] = external_demand

    if lines[index] != "CapacityLimitsForEachResourceAndPeriod":
        raise ValueError("Expected capacity-limit section.")
    index += 1

    capacity_limits = []

    for _ in range(resources):
        row = list(map(float, lines[index].split()))
        capacity_limits.append(row)
        index += 1

    data["capacity_limits"] = capacity_limits

    if lines[index] != "CapacityNeedsForProductionForEachResourceAndItem":
        raise ValueError("Expected production-capacity section.")
    index += 1

    production_capacity = []

    for _ in range(resources):
        row = list(map(float, lines[index].split()))
        production_capacity.append(row)
        index += 1

    data["production_capacity"] = production_capacity

    if lines[index] != "CapacityNeedsForSetupForEachResourceAndItem":
        raise ValueError("Expected setup-capacity section.")
    index += 1

    setup_capacity = []

    for _ in range(resources):
        row = list(map(float, lines[index].split()))
        setup_capacity.append(row)
        index += 1

    data["setup_capacity"] = setup_capacity

    if lines[index] != "OverTimeCostsForEachResource":
        raise ValueError("Expected overtime-cost section.")
    index += 1

    overtime_costs = list(map(float, lines[index].split()))
    data["overtime_costs"] = overtime_costs

    return data

# Start of AI-generated code unmodified
def main() -> None:
    project_folder = Path(__file__).resolve().parent.parent
    instances_folder = project_folder / "instances"

    instance_files = [
        "A6_G001545_MLCLS.dat",
        "B6_G511541_MLCLS.dat",
        "C20_K805132_MLCLS.dat",
        "D20_G819321_MLCLS.dat",
    ]

    for file_name in instance_files:
        file_path = instances_folder / file_name

        print("\n" + "=" * 70)
        print(f"Reading: {file_name}")
        print("=" * 70)

        if not file_path.exists():
            print(f"File not found: {file_path}")
            continue

        try:
            instance = read_instance(file_path)

            print("INSTANCE READ SUCCESSFULLY")
            print(f"Model name: {instance['model_name']}")
            print(f"Periods: {instance['periods']}")
            print(f"Items: {instance['items']}")
            print(f"Resources: {instance['resources']}")

            print(
                "Demand dimensions: "
                f"{len(instance['external_demand'])} x "
                f"{len(instance['external_demand'][0])}"
            )

            print(
                "BOM dimensions: "
                f"{len(instance['bom'])} x "
                f"{len(instance['bom'][0])}"
            )

            print(
                "Capacity dimensions: "
                f"{len(instance['capacity_limits'])} x "
                f"{len(instance['capacity_limits'][0])}"
            )

        except Exception as error:
            print(f"Error while reading {file_name}: {error}")

# Start of AI-generated code unmodified
if __name__ == "__main__":
    main()

