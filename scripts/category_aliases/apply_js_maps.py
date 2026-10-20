"""Splice the generated category maps into dashboard.html.

Replaces the two hand-maintained alias maps with generated ones driven by the
same table as utils/categories.py, so the display layer and the storage layer
cannot drift apart. Run gen_categories.py first.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gen_categories as g  # noqa: E402

PATH = os.path.join(g.PROJECT_ROOT, "dashboard.html")

src = open(PATH, encoding="utf-8").read()

START_MARK = "// Normalize raw category names to clean, consolidated groups."
END_MARK = "const EXPANDED_GROUPS_KEY"

start = src.index(START_MARK)
end = src.index(END_MARK)

js_main, py_main, js_sub, py_sub, _ = g.build()


def emit(name, mapping, indent=6):
    pad = " " * indent
    lines = [f"const {name} = {{"]
    for k in sorted(mapping):
        lines.append(f"{pad}'{k}': '{mapping[k]}',")
    lines.append("};")
    return "\n".join(lines)


new_block = f"""// Normalize raw category names to clean, consolidated groups.
// Handles spacing inconsistencies, duplicate groups, and merges similar
// categories, so the sidebar shows one row per shelf however a store spells it.
//
// Keys are compared with spacing and punctuation removed and case ignored, the
// same normalisation the Python side uses, so "Accesory", "Acc Miscellaneous"
// and "accessories" all reach one shelf. Any name not listed is left untouched
// rather than guessed at.
function categoryKey(name) {{
  return String(name || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
}}

{emit('MAIN_ALIASES', js_main)}

function normalizeCategoryMain(cat) {{
  const raw = String(cat || '').split(' · ')[0].trim();

  return MAIN_ALIASES[categoryKey(raw)] || raw;
}}

function categoryMain(cat) {{
  return normalizeCategoryMain(cat);
}}

function categorySub(cat) {{
  const parts = String(cat || '').split(' · ');
  return parts.length > 1 ? parts.slice(1).join(' · ').trim() : cat;
}}

// Subcategory labels are corrected for case, spacing and spelling, and obvious
// variants are merged ("Hoodie"/"Hoodies", "Smalls"/"small buds") so one shelf
// does not split into several rows because two stores typed it differently.
{emit('SUB_ALIASES', js_sub)}

function normalizeCategorySub(cat) {{
  const raw = categorySub(cat);

  return SUB_ALIASES[categoryKey(raw)] || raw;
}}

"""

src = src[:start] + new_block + src[end:]
open(PATH, "w", encoding="utf-8").write(src)
print(f"patched {PATH}: {len(js_main)} main aliases, {len(js_sub)} sub aliases")
