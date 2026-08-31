import itertools
import json
from pathlib import Path


def generate_grid(base_config, parameters):
    keys = list(parameters)
    values = [parameters[k] for k in keys]

    for combo in itertools.product(*values):
        config = dict(base_config)
        config.update(dict(zip(keys, combo)))
        yield config


def run_grid(base_config, parameters, output_path):
    results = list(generate_grid(base_config, parameters))

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "experiment_count": len(results),
                "experiments": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return results
