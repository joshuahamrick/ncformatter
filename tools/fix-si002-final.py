"""
Carefully convert SI002-Triad:
1. Change header from {Insert(H003 TagHeader)} to individual H002/H003/H004
2. Add {Font(Calibri|11pt)}
3. Add HoursOfOperation to closing
4. Convert list items to bullet tables, PRESERVING all {If}/{End If} tags
"""
import re

filepath = r'formatter examples/SI002-Triad/SI002-Triad-formatted.html'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Step 1: Header and font changes
output = []
for i, line in enumerate(lines):
    s = line.strip()
    if s == '<div>{Insert(H003 TagHeader)}</div>':
        output.append('{Font(Calibri|11pt)}\n')
        output.append('<div>{[H002]}</div>\n')
        output.append('<div>{[H003]}</div>\n')
        output.append('<div>{[H004]}</div>\n')
    elif 'please contact our Customer Service Department at {[plsMatrix.CSPhoneNumber]}.' in s and 'HoursOfOperation' not in s:
        output.append(line.replace(
            'please contact our Customer Service Department at {[plsMatrix.CSPhoneNumber]}.',
            'please contact our Customer Service Department at {[plsMatrix.CSPhoneNumber]}. Our office is open {[plsMatrix.HoursOfOperation]}.'
        ))
    else:
        output.append(line)

lines = output

# Step 2: Convert list items to bullet tables
# CRITICAL: Never consume {If}, {End If}, {Else If}, {Else} tags

def is_conditional(s):
    """Check if a line is a conditional tag"""
    return '{If(' in s or '{End If}' in s or '{Else If(' in s or '{Else}' in s

def is_list_item_div(s):
    """Check if a line is a short div that could be a list item"""
    m = re.match(r'^<div>(.+)</div>$', s)
    if not m:
        return False, ''
    text = m.group(1)
    if len(text) > 200:
        return False, ''
    if '<' in text:
        return False, ''
    # Skip headers and explanatory text
    skip_starts = [
        'Method of Transfer', 'Primary Method of Transfer',
        'To prove', 'Note:', 'If the ', 'If registered', 'If you ',
        'If no ', 'If Testate', 'If Intestate', 'For ', 'You ',
        'This process', 'A transfer', 'Documents evidencing',
        'A deed from less', 'Rather than', 'No deed', 'The ',
        'Our ', 'Please ', 'Real estate may', 'One may',
        'There are no', 'Setting forth', 'AGREED', 'Borrower',
        'Dear ', 'Sincerely', 'Customer Service', 'Loss Mitigation',
        'We are', 'We will', 'Any pending', 'We reserve',
        'We will hold', 'Our acceptance', 'All terms', 'Credit',
        'In order', 'You only', 'Re: Loan', 'RE:',
    ]
    # Skip standalone template variables like {[H002]}, {[mailingAddress]}, {[plsMatrix.*]}
    if re.match(r'^\{?\[', text):
        return False, ''
    # Skip if it's purely a template variable
    if re.match(r'^\{.*\}$', text):
        return False, ''
    for s2 in skip_starts:
        if text.startswith(s2):
            return False, ''
    return True, text

def make_bullet_table(items):
    rows = []
    for text in items:
        clean = text.strip()
        if clean.endswith(' or'):
            clean = clean[:-3]
        rows.append(f'<tr valign="top">\n  <td width="3%" style="text-align: center">\u2022</td>\n  <td>{clean}</td>\n</tr>')
    return '<table width="100%" style="border-collapse: collapse"><tbody>\n' + '\n'.join(rows) + '\n</tbody></table>\n'

output2 = []
i = 0
total = len(lines)
changes = 0

while i < total:
    s = lines[i].strip()
    
    # Never touch conditional lines
    if is_conditional(s):
        output2.append(lines[i])
        i += 1
        continue
    
    # Check if already a table
    if '<table' in s:
        output2.append(lines[i])
        i += 1
        continue
    
    # Check for Method of Transfer header or list-preceding header
    is_method = re.match(r'^<div>(?:Primary )?Method of Transfer', s) or \
                re.match(r'^<div>(?:Primary )?Method of transfer', s)
    is_list_hdr = re.match(r'^<div>.*(?:following will (?:suffice|serve)|Affidavit containing the following|affidavit signed by the trustee stating)', s)
    
    if is_method or is_list_hdr:
        output2.append(lines[i])
        i += 1
        # Output br after header
        if i < total and lines[i].strip() == '<br>':
            output2.append(lines[i])
            i += 1
        # Check if next is already a table
        if i < total and '<table' in lines[i]:
            continue
        # Try to collect list items (but STOP at any conditional)
        list_items = []
        save_i = i
        while i < total:
            cs = lines[i].strip()
            if is_conditional(cs):
                break  # NEVER consume conditionals
            if cs == '<br>':
                # Peek: is the next line also a list item or br?
                if i + 1 < total:
                    next_s = lines[i + 1].strip()
                    is_item, _ = is_list_item_div(next_s)
                    if is_item:
                        i += 1  # skip br, continue collecting
                        continue
                break
            is_item, text = is_list_item_div(cs)
            if is_item:
                list_items.append(text)
                i += 1
            else:
                break
        
        if len(list_items) >= 2:
            output2.append(make_bullet_table(list_items))
            changes += 1
            # Skip trailing br if present
            if i < total and lines[i].strip() == '<br>':
                i += 1
        else:
            # Not enough items, restore
            i = save_i
    
    # Also check for standalone consecutive div+br that are list items
    elif is_list_item_div(s)[0]:
        is_item, text = is_list_item_div(s)
        # Look ahead for more list items
        items = [text]
        save_i = i
        i += 1
        # Skip br after first item
        if i < total and lines[i].strip() == '<br>':
            i += 1
        while i < total:
            cs = lines[i].strip()
            if is_conditional(cs):
                break
            if cs == '<br>':
                if i + 1 < total:
                    next_s = lines[i + 1].strip()
                    is_it, _ = is_list_item_div(next_s)
                    if is_it:
                        i += 1
                        continue
                break
            is_it, txt = is_list_item_div(cs)
            if is_it:
                items.append(txt)
                i += 1
                if i < total and lines[i].strip() == '<br>':
                    i += 1
            else:
                break
        
        if len(items) >= 2:
            output2.append(make_bullet_table(items))
            changes += 1
        else:
            # Not enough, restore original lines
            i = save_i
            output2.append(lines[i])
            i += 1
    else:
        output2.append(lines[i])
        i += 1

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(output2)

# Verify
with open(filepath, 'r', encoding='utf-8') as f:
    result = f.read()

ifs = len(re.findall(r'\{If\(', result))
endifs = len(re.findall(r'\{End If\}', result))
print(f"Conversions: {changes}")
print(f"If: {ifs}, End If: {endifs}")
print(f"Original had If: 199, End If: 233")
print(f"Match: If={'YES' if ifs == 199 else 'NO (+1 expected for NE/ND)'}, End If={'YES' if endifs == 233 else 'NO'}")
