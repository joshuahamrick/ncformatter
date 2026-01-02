#!/usr/bin/env python3
"""Convert bullet points to tables in SI002 - improved version"""

import re
from pathlib import Path

html_path = Path(__file__).parent.parent / "formatter examples" / "SI002" / "SI002-formatted.html"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to find consecutive list items ending with " or" or " or."
# Look for pattern: <div>Text or</div><br><div>Text or</div><br>...

def convert_list_items(text):
    """Convert consecutive list items to table format"""
    
    # Pattern: <div>... or</div> followed by <br> and another <div>... or</div>
    pattern = r'(<div>([^<]+?)\s+or</div>\s*<br>\s*)+<div>([^<]+?)\s+or</div>'
    
    def replace_func(match):
        # Extract all items
        full_match = match.group(0)
        items = re.findall(r'<div>([^<]+?)\s+or</div>', full_match)
        
        if len(items) >= 2:
            # Build table
            table_html = '<div><table width="100%" style="border-collapse: collapse"><tbody>'
            for item in items:
                item_text = item.strip()
                table_html += f'<tr><td width="3%" valign="top" style="text-align: center">•</td><td>{item_text}</td></tr>'
            table_html += '</tbody></table></div><br>'
            return table_html
        
        return match.group(0)
    
    # Replace all occurrences
    new_content = re.sub(pattern, replace_func, text)
    
    return new_content

# Also handle single "or" items that are part of a list
def convert_single_or_items(text):
    """Convert single items ending with 'or' that appear in sequence"""
    lines = text.split('\n')
    new_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Check if this line ends with " or</div>"
        if line.endswith(' or</div>'):
            # Collect consecutive "or" items
            list_items = []
            j = i
            
            while j < len(lines):
                current_line = lines[j].strip()
                if current_line.endswith(' or</div>'):
                    # Extract text
                    match = re.match(r'<div>(.+?)\s+or</div>', current_line)
                    if match:
                        list_items.append(match.group(1).strip())
                    j += 1
                    # Skip <br> if present
                    if j < len(lines) and lines[j].strip() == '<br>':
                        j += 1
                else:
                    break
            
            if len(list_items) >= 2:
                # Convert to table
                new_lines.append('<div><table width="100%" style="border-collapse: collapse"><tbody>')
                for item in list_items:
                    new_lines.append('<tr>')
                    new_lines.append('  <td width="3%" valign="top" style="text-align: center">•</td>')
                    new_lines.append(f'  <td>{item}</td>')
                    new_lines.append('</tr>')
                new_lines.append('</tbody></table></div>')
                new_lines.append('<br>')
                i = j
                continue
        
        new_lines.append(lines[i])
        i += 1
    
    return '\n'.join(new_lines)

# Apply conversions
content = convert_single_or_items(content)

# Write back
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Converted bullet points to tables")

