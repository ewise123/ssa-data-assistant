import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

ConfigDict = Dict[str, Any]


def load_aliases(config_dir: str | Path = "app/config") -> Dict[str, Dict[str, List[str]]]:
    """
    Load all *_aliases.csv files into a nested mapping keyed by the file stem.
    Example: {"clients": {"Acme": ["acme inc", ...]}, "tools": {...}}
    """
    base = Path(config_dir)
    aliases: Dict[str, Dict[str, List[str]]] = {}
    for csv_path in sorted(base.glob("*_aliases.csv")):
        stem = csv_path.stem.replace("_aliases", "")
        with csv_path.open(mode="r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames or []
            if len(fieldnames) < 2:
                continue
            canonical_field, alias_field = fieldnames[0], fieldnames[1]
            mapping: Dict[str, List[str]] = defaultdict(list)
            for row in reader:
                canonical = (row.get(canonical_field) or "").strip()
                alias = (row.get(alias_field) or "").strip()
                if not canonical or not alias:
                    continue
                mapping[canonical].append(alias)
        if mapping:
            aliases[stem] = dict(mapping)
    return aliases


def load_allowed_values(directory: str | Path = "app/config/allowed_values") -> Dict[str, List[str]]:
    """
    Load allowed-value CSVs where each file contains one value per row.
    The filename (without extension) is used as the key.
    """
    base = Path(directory)
    if not base.exists():
        return {}

    allowed: Dict[str, List[str]] = {}
    for csv_path in sorted(base.glob("*.csv")):
        values: List[str] = []
        with csv_path.open(mode="r", encoding="utf-8") as fh:
            for line in fh:
                val = line.strip()
                if val:
                    values.append(val)
        if values:
            allowed[csv_path.stem] = values
    return allowed


def load_join_map(path: str | Path = "app/config/join_map.json") -> ConfigDict:
    p = Path(path)
    if not p.exists():
        return {"paths": []}
    return json.loads(p.read_text(encoding="utf-8"))


def load_column_semantics(path: str | Path = "app/config/column_semantics.csv") -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Load column semantics into a nested mapping:
    {
        "TableName": {
            "column_name": {
                "semantic_type": "...",
                "preferred_filter": "...",
                "pattern": "...",
                "notes": "...",
            }
        }
    }
    """
    p = Path(path)
    if not p.exists():
        return {}

    semantics: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(dict)
    with p.open(mode="r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            table = (row.get("table") or "").strip()
            column = (row.get("column") or "").strip()
            if not table or not column:
                continue
            semantics[table][column] = {
                "semantic_type": (row.get("semantic_type") or "").strip(),
                "preferred_filter": (row.get("preferred_filter") or "").strip(),
                "pattern": (row.get("pattern") or "").strip(),
                "notes": (row.get("notes") or "").strip(),
            }
    return {table: columns for table, columns in semantics.items()}


def load_disambiguation_rules(path: str | Path = "app/config/disambiguation.json") -> ConfigDict:
    p = Path(path)
    if not p.exists():
        return {"rules": []}
    return json.loads(p.read_text(encoding="utf-8"))
