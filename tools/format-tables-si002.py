#!/usr/bin/env python3
"""Format all bullet point tables with proper line breaks"""

import re
from pathlib import Path

html_path = Path(__file__).parent.parent / "formatter examples" / "SI002" / "SI002-formatted.html"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to find tables that need formatting
# Match: <table...><tbody><tr>  <td>...</td>  <td>...</td></tr><tr>...
pattern = r'(<div><table width="100%" style="border-collapse: collapse"><tbody>)(<tr>\s*<td[^>]*>([^<]+)</td>\s*<td>([^<]+)</td>\s*</tr>\s*)+</tbody></table></div>)'

def format_table(match):
    table_start = match.group(1)
    table_body = match.group(2)
    
    # Extract all rows
    rows = re.findall(r'<tr>\s*<td[^>]*>([^<]+)</td>\s*<td>([^<]+)</td>\s*</tr>', table_body)
    
    # Rebuild with proper formatting
    formatted = table_start + '\n'
    for bullet_text, content_text in rows:
        formatted += '<tr>\n'
        formatted += '  <td width="3%" valign="top" style="text-align: center">•</td>\n'
        formatted += f'  <td>{content_text}</td>\n'
        formatted += '</tr>\n'
    formatted += '</tbody></table></div>'
    
    return formatted

# Replace all matches
content = re.sub(pattern, format_table, content)

# Also fix tables that are already partially formatted but need cleanup
content = re.sub(
    r'<tr>\s*<td width="3%" valign="top" style="text-align: center">•</td>\s*<td>([^<]+)</td>\s*</tr>',
    r'<tr>\n  <td width="3%" valign="top" style="text-align: center">•</td>\n  <td>\1</td>\n</tr>',
    content
)

# Write back
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Formatted all tables with proper line breaks")

