"""Conservative CPU recommendations, not automatic performance tuning."""

import os


def available_cpus():
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def recommended_threads():
    # Respect affinity; leave benchmarking to determine the best thread count.
    return available_cpus()
