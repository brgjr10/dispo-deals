#!/usr/bin/env python3
"""
Generate schema documentation from the SQLite database schema.
This script reads the actual database schema and outputs Markdown documentation.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/dispo_deals.db")


def get_schema():
    """Extract schema information from the database."""
    if not DB_PATH.exists():
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = [row['name'] for row in cursor.fetchall()]

    schema = {}
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()

        cursor.execute(f"PRAGMA foreign_key_list({table})")
        fks = cursor.fetchall()

        cursor.execute(f"PRAGMA index_list({table})")
        indexes = cursor.fetchall()

        index_details = {}
        for idx in indexes:
            cursor.execute(f"PRAGMA index_info({idx['name']})")
            idx_cols = cursor.fetchall()
            index_details[idx['name']] = [col['name'] for col in idx_cols]

        schema[table] = {
            'columns': columns,
            'foreign_keys': fks,
            'indexes': index_details
        }

    conn.close()
    return schema


def format_schema(schema):
    """Format schema as Markdown."""
    if not schema:
        return "# Database Schema\n\nDatabase not found. Run the application first to initialize the schema.\n"

    lines = ["# Database Schema", "", "Generated from SQLite database.", ""]

    for table_name, info in sorted(schema.items()):
        lines.append(f"## `{table_name}`")
        lines.append("")
        lines.append("| Column | Type | Not Null | Default | Primary Key |")
        lines.append("|--------|------|----------|---------|-------------|")

        for col in info['columns']:
            pk = "✓" if col['pk'] else ""
            not_null = "✓" if col['notnull'] else ""
            default = col['dflt_value'] if col['dflt_value'] is not None else ""
            lines.append(f"| `{col['name']}` | {col['type']} | {not_null} | {default} | {pk} |")

        if info['foreign_keys']:
            lines.append("")
            lines.append("### Foreign Keys")
            lines.append("")
            lines.append("| Column | References | On Update | On Delete |")
            lines.append("|--------|------------|-----------|-----------|")
            for fk in info['foreign_keys']:
                lines.append(f"| `{fk['from']}` | `{fk['table']}.{fk['to']}` | {fk['on_update']} | {fk['on_delete']} |")

        if info['indexes']:
            lines.append("")
            lines.append("### Indexes")
            lines.append("")
            for idx_name, cols in info['indexes'].items():
                lines.append(f"- **{idx_name}**: `{', '.join(cols)}`")

        lines.append("")

    return "\n".join(lines)


def main():
    schema = get_schema()
    output = format_schema(schema)
    print(output)


if __name__ == "__main__":
    main()