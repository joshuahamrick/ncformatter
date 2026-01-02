#!/usr/bin/env python3
"""Final bullet point conversion and table formatting"""

import re
from pathlib import Path

html_path = Path(__file__).parent.parent / "formatter examples" / "SI002" / "SI002-formatted.html"

with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# First, format existing tables with proper line breaks
formatted_lines = []
for line in lines:
    # Check if line contains a compact table
    if '<table' in line and '<tr>' in line and '  <td' not in line:
        # Split table into properly formatted lines
        if '<tr>' in line and '</tr>' in line:
            # Extract table parts
            table_match = re.search(r'(<div><table[^>]*><tbody>)(.*?)(</tbody></table></div>)', line)
            if table_match:
                table_start = table_match.group(1)
                table_body = table_match.group(2)
                table_end = table_match.group(3)
                
                # Extract rows
                rows = re.findall(r'<tr>\s*<td[^>]*>([^<]+)</td>\s*<td>([^<]+)</td>\s*</tr>', table_body)
                
                if rows:
                    formatted_lines.append(table_start + '\n')
                    for bullet_text, content_text in rows:
                        formatted_lines.append('<tr>\n')
                        formatted_lines.append('  <td width="3%" valign="top" style="text-align: center">•</td>\n')
                        formatted_lines.append(f'  <td>{content_text}</td>\n')
                        formatted_lines.append('</tr>\n')
                    formatted_lines.append(table_end)
                    continue
    
    formatted_lines.append(line)

# Now find remaining "or" items that should be bullet lists
new_lines = []
i = 0

while i < len(formatted_lines):
    line = formatted_lines[i].strip()
    
    # Check if this line ends with " or</div>"
    if line.endswith(' or</div>'):
        # Collect consecutive items
        list_items = []
        j = i
        
        # Collect all "or" items
        while j < len(formatted_lines):
            current_line = formatted_lines[j].strip()
            if current_line.endswith(' or</div>'):
                match = re.match(r'<div>(.+?)\s+or</div>', current_line)
                if match:
                    list_items.append(match.group(1).strip())
                j += 1
                # Skip <br>
                if j < len(formatted_lines) and formatted_lines[j].strip() == '<br>':
                    j += 1
            else:
                break
        
        # Check for non-"or" item after
        if j < len(formatted_lines):
            next_line = formatted_lines[j].strip()
            if (next_line.startswith('<div>') and 
                not next_line.startswith('<div>Method of Transfer:') and 
                not next_line.startswith('<div>If ') and 
                not next_line.startswith('<div>Primary Method') and 
                not next_line.startswith('<div>To prove') and 
                '{If' not in next_line and 
                '{End If}' not in next_line and
                '<table' not in next_line):
                match = re.match(r'<div>(.+?)</div>', next_line)
                if match:
                    text = match.group(1).strip()
                    if len(text) < 150 and text not in ['Method of Transfer: Nonprobate', 'Method of Transfer: Probate']:
                        list_items.append(text)
                        j += 1
                        if j < len(formatted_lines) and formatted_lines[j].strip() == '<br>':
                            j += 1
        
        if len(list_items) >= 2:
            # Convert to table
            new_lines.append('<div><table width="100%" style="border-collapse: collapse"><tbody>\n')
            for item in list_items:
                new_lines.append('<tr>\n')
                new_lines.append('  <td width="3%" valign="top" style="text-align: center">•</td>\n')
                new_lines.append(f'  <td>{item}</td>\n')
                new_lines.append('</tr>\n')
            new_lines.append('</tbody></table></div>\n')
            new_lines.append('<br>\n')
            i = j
            continue
    
    new_lines.append(formatted_lines[i])
    i += 1

# Write back
with open(html_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Converted remaining bullet points. File now has {len(new_lines)} lines")

