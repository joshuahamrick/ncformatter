"""
Convert plain div list items to bullet point tables in SI002-Triad.
Strategy: After any "Method of Transfer" header, consecutive short div+br items = bullet list.
"""
import re

filepath = r'formatter examples/SI002-Triad/SI002-Triad-formatted.html'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

def make_bullet_table(items):
    """Create a bullet point table from list of text items"""
    rows = []
    for text in items:
        # Strip trailing " or" 
        clean = text.strip()
        if clean.endswith(' or'):
            clean = clean[:-3]
        rows.append(f'<tr valign="top">\n  <td width="3%" style="text-align: center">\u2022</td>\n  <td>{clean}</td>\n</tr>')
    return '<table width="100%" style="border-collapse: collapse"><tbody>\n' + '\n'.join(rows) + '\n</tbody></table>\n'

def is_list_item(line_text):
    """Check if a line looks like a list item (short, not a header/note/paragraph)"""
    # Must be a simple div
    m = re.match(r'^<div>(.+)</div>$', line_text.strip())
    if not m:
        return False
    text = m.group(1)
    # Skip if it's too long (likely explanatory paragraph)
    if len(text) > 200:
        return False
    # Skip if it contains HTML tags (bold, table, etc.)
    if '<' in text:
        return False
    # Skip certain patterns that are headers/notes, not list items
    skip_patterns = [
        r'^Method of Transfer',
        r'^Primary Method of Transfer',
        r'^To prove',
        r'^Note:',
        r'^If the ',
        r'^If registered',
        r'^If you ',
        r'^If no ',
        r'^If Testate',
        r'^If Intestate',
        r'^For ',
        r'^You ',
        r'^This process',
        r'^A transfer',
        r'^Documents evidencing',
        r'^A deed from less than',
        r'^Rather than',
        r'^No deed',
        r'^The ',
        r'^Our ',
        r'^Please ',
        r'^Real estate may',
        r'^One may',
        r'^There are no',
        r'^Setting forth',
        r'^AGREED',
        r'^Borrower',
    ]
    for pat in skip_patterns:
        if re.match(pat, text):
            return False
    return True

def get_div_text(line_text):
    m = re.match(r'^<div>(.+)</div>$', line_text.strip())
    return m.group(1) if m else None

output = []
i = 0
changes = 0
total_lines = len(lines)

while i < total_lines:
    line = lines[i]
    stripped = line.strip()
    
    # Check if this is a Method of Transfer header
    is_method_header = re.match(r'^<div>(?:Primary )?Method of Transfer', stripped) or \
                       re.match(r'^<div>(?:Primary )?Method of transfer', stripped)
    
    # Also check for "following will suffice/serve" headers that precede lists
    is_list_header = re.match(r'^<div>.*(?:following will (?:suffice|serve)|Affidavit containing the following|An affidavit signed by the trustee stating)', stripped)
    
    if (is_method_header or is_list_header):
        output.append(line)
        i += 1
        
        # Skip br after header
        if i < total_lines and lines[i].strip() == '<br>':
            output.append(lines[i])
            i += 1
        
        # Check if already followed by a table
        if i < total_lines and '<table' in lines[i]:
            continue  # Already a bullet table
        
        # Collect consecutive list items
        list_items = []
        save_i = i
        
        while i < total_lines:
            curr_stripped = lines[i].strip()
            
            if is_list_item(curr_stripped):
                text = get_div_text(curr_stripped)
                list_items.append(text)
                i += 1
                # Skip trailing <br>
                if i < total_lines and lines[i].strip() == '<br>':
                    i += 1
            else:
                break
        
        if len(list_items) >= 2:
            output.append(make_bullet_table(list_items))
            changes += 1
            print(f"  Converted {len(list_items)} items at line ~{save_i}: {[it[:40] for it in list_items]}")
        else:
            # Put back the original lines
            i = save_i
            for j in range(save_i, min(save_i + len(list_items) * 2, total_lines)):
                output.append(lines[j])
            i = save_i + max(len(list_items) * 2, 1)
            if len(list_items) == 0:
                # No items found, just continue
                pass
    else:
        output.append(line)
        i += 1

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(output)

print(f"\nTotal: {changes} bullet table conversions made")
