"""
Second pass: Find consecutive div+br sequences (2+ items) that aren't 
after a Method of Transfer header but are still list items within state blocks.
"""
import re

filepath = r'formatter examples/SI002-Triad/SI002-Triad-formatted.html'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

def make_bullet_table(items):
    rows = []
    for text in items:
        clean = text.strip()
        if clean.endswith(' or'):
            clean = clean[:-3]
        rows.append(f'<tr valign="top">\n  <td width="3%" style="text-align: center">\u2022</td>\n  <td>{clean}</td>\n</tr>')
    return '<table width="100%" style="border-collapse: collapse"><tbody>\n' + '\n'.join(rows) + '\n</tbody></table>\n'

def is_short_list_item(text):
    """Check if text looks like a document list item (short, no HTML)"""
    if len(text) > 150:
        return False
    if '<' in text:
        return False
    # Skip headers and explanatory text
    skip_starts = [
        'Method of Transfer', 'Primary Method', 'To prove', 'Note:', 
        'If the ', 'If registered', 'If you ', 'If no ', 'If Testate',
        'If Intestate', 'For ', 'You ', 'This process', 'A transfer',
        'Documents evidencing', 'A deed from less', 'Rather than',
        'No deed', 'The ', 'Our ', 'Please ', 'Real estate may',
        'One may', 'There are no', 'Setting forth', 'AGREED', 'Borrower',
        'Dear ', '{', 'Sincerely', 'Customer Service', 'Loss Mitigation',
        'Congratulations', 'Upon review', 'We are', 'We will',
        'Any pending', 'We reserve', 'We will hold', 'Our acceptance',
        'All terms', 'Credit', 'In order', 'You only', 'Deed conveying the property to you, that is signed',
    ]
    for s in skip_starts:
        if text.startswith(s):
            return False
    return True

def get_div_text(line):
    m = re.match(r'^<div>(.+)</div>$', line.strip())
    return m.group(1) if m else None

# Scan for consecutive short div+br sequences within state conditionals
output = []
i = 0
changes = 0
total = len(lines)

while i < total:
    line = lines[i]
    stripped = line.strip()
    
    # Check if already in/near a table
    if '<table' in stripped:
        output.append(line)
        i += 1
        continue
    
    # Check for a div that could be a list item
    text = get_div_text(stripped)
    if text and is_short_list_item(text):
        # Look ahead to count consecutive list items
        items = []
        save_i = i
        while i < total:
            curr = lines[i].strip()
            ct = get_div_text(curr)
            if ct and is_short_list_item(ct):
                items.append(ct)
                i += 1
                if i < total and lines[i].strip() == '<br>':
                    i += 1
            else:
                break
        
        if len(items) >= 2:
            # Check if these are already inside a table (look back for <table)
            already_in_table = False
            for j in range(max(0, save_i-5), save_i):
                if '<table' in lines[j]:
                    already_in_table = True
                    break
            
            if not already_in_table:
                output.append(make_bullet_table(items))
                changes += 1
                print(f"  Pass2 converted {len(items)} items at line ~{save_i}: {[it[:50] for it in items]}")
                continue
        
        # Not enough items or already in table, output as-is
        i = save_i
        output.append(lines[i])
        i += 1
    else:
        output.append(line)
        i += 1

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(output)

print(f"\nPass 2: {changes} additional bullet table conversions")
