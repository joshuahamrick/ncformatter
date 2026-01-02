#!/usr/bin/env python3
"""Convert bullet points to tables in SI002"""

import re
from pathlib import Path

html_path = Path(__file__).parent.parent / "formatter examples" / "SI002" / "SI002-formatted.html"

with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Pattern to find list items (lines ending with " or" or " or.")
list_item_pattern = re.compile(r'^<div>(.+?)\s+or\.?</div>$')

new_lines = []
i = 0
while i < len(lines):
    line = lines[i].strip()
    
    # Check if this is a list item
    match = list_item_pattern.match(line)
    if match:
        # Collect consecutive list items
        list_items = []
        j = i
        while j < len(lines):
            item_line = lines[j].strip()
            item_match = list_item_pattern.match(item_line)
            if item_match:
                # Extract text (remove " or" ending)
                text = item_match.group(1).strip()
                list_items.append(text)
                j += 1
                # Skip <br> after list item
                if j < len(lines) and lines[j].strip() == '<br>':
                    j += 1
            else:
                break
        
        if len(list_items) > 1:
            # Convert to table format
            new_lines.append('<div><table width="100%" style="border-collapse: collapse"><tbody>')
            for item_text in list_items:
                new_lines.append('<tr>')
                new_lines.append('  <td width="3%" valign="top" style="text-align: center">•</td>')
                new_lines.append(f'  <td>{item_text}</td>')
                new_lines.append('</tr>')
            new_lines.append('</tbody></table></div>')
            new_lines.append('<br>')
            i = j
            continue
    
    new_lines.append(lines[i])
    i += 1

# Write back
with open(html_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Converted bullet points. New file has {len(new_lines)} lines")

