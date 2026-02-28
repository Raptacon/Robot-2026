# Native imports
from collections import deque
from typing import Callable, Dict, List

# Internal imports
from utils.subsystem_factory import SubsystemEntry, get_registered_entries


def _topological_sort(entries: List[SubsystemEntry]) -> List[SubsystemEntry]:
    """
    Sort subsystem entries so that dependencies come before dependents.
    Uses Kahn's algorithm. Raises ValueError on cycles.
    """
    by_name: Dict[str, SubsystemEntry] = {e.name: e for e in entries}
    in_degree: Dict[str, int] = {e.name: 0 for e in entries}
    dependents: Dict[str, List[str]] = {e.name: [] for e in entries}

    for entry in entries:
        for dep in entry.dependencies:
            if dep in by_name:
                in_degree[entry.name] += 1
                dependents[dep].append(entry.name)

    queue: deque[str] = deque(
        name for name, deg in in_degree.items() if deg == 0
    )
    result: List[SubsystemEntry] = []

    while queue:
        name = queue.popleft()
        result.append(by_name[name])
        for dependent in dependents[name]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(entries):
        sorted_names = {e.name for e in result}
        cycle_names = [e.name for e in entries if e.name not in sorted_names]
        raise ValueError(f"Dependency cycle detected among: {cycle_names}")

    return result


def get_competition_manifest(container) -> List[SubsystemEntry]:
    """
    Build the full subsystem manifest for the competition robot.

    Importing the subsystem package triggers self-registration of all
    subsystem modules (via their register_subsystem() calls). The
    returned list is topologically sorted so dependencies are created first.
    """
    import subsystem  # triggers registration via __init__.py imports
    return _topological_sort(get_registered_entries())


def _collect_dependencies(target_names, all_entries):
    """
    Collect a set of entry names needed to satisfy the given targets,
    transitively including all dependencies.
    """
    by_name = {e.name: e for e in all_entries}
    result = set()
    queue = list(target_names)
    while queue:
        name = queue.pop()
        if name in result or name not in by_name:
            continue
        result.add(name)
        queue.extend(by_name[name].dependencies)
    return result


def get_sparky_manifest(container) -> List[SubsystemEntry]:
    """
    Build a minimal manifest for Sparky (drivetrain only).
    Transitively includes swerve module dependencies.
    """
    import subsystem  # triggers registration via __init__.py imports
    all_entries = get_registered_entries()
    needed = _collect_dependencies({"drivetrain"}, all_entries)
    return _topological_sort([e for e in all_entries if e.name in needed])


# Maps robot name strings to manifest builder functions.
# None falls back to the full competition manifest.
ROBOT_MANIFESTS: Dict[str, Callable] = {
    "competition": get_competition_manifest,
    "sparky": get_sparky_manifest,
    None: get_competition_manifest,
}
