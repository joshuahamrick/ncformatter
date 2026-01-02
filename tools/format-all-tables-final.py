#!/usr/bin/env python3
"""Format all tables and convert remaining bullet points"""

import re
from pathlib import Path

html_path = Path(__file__).parent.parent / "formatter examples" / "SI002" / "SI002-formatted.html"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Format all compact tables
def format_compact_table(match):
    full_table = match.group(0)
    
    # Extract all rows
    rows = re.findall(r'<tr>\s*<td[^>]*>([^<]+)</td>\s*<td>([^<]+)</td>\s*</tr>', full_table)
    
    if not rows:
        return full_table
    
    # Rebuild with proper formatting
    formatted = '<div><table width="100%" style="border-collapse: collapse"><tbody>\n'
    for bullet_text, content_text in rows:
        formatted += '<tr>\n'
        formatted += '  <td width="3%" valign="top" style="text-align: center">•</td>\n'
        formatted += f'  <td>{content_text}</td>\n'
        formatted += '</tr>\n'
    formatted += '</tbody></table></div>'
    
    return formatted

# Pattern for compact tables
pattern = r'<div><table width="100%" style="border-collapse: collapse"><tbody>(<tr>\s*<td[^>]*>[^<]+</td>\s*<td>[^<]+</td>\s*</tr>\s*)+</tbody></table></div>'

content = re.sub(pattern, format_compact_table, content)

# Write back
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Formatted all compact tables")

