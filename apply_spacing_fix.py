"""
Apply the SPACING marker changes to format_ir_for_prompt in generate-template.py.
Uses direct string manipulation to ensure correct tab indentation.
"""

src = open('api/generate-template.py', encoding='utf-8').read()

# Change 1: Add seen_salutation flag
old1 = '\tpara_counter = 0  # Sequential numbering - no gaps from skipped blanks\n\tfor idx, block in enumerate(blocks):'
new1 = '\tpara_counter = 0  # Sequential numbering - no gaps from skipped blanks\n\tseen_salutation = False  # Only emit SPACING markers after the Dear/salutation\n\tfor idx, block in enumerate(blocks):'
assert old1 in src, "Change 1: marker not found"
src = src.replace(old1, new1, 1)
print("Change 1: Added seen_salutation flag")

# Change 2: Replace empty block handler
# Old: simple list-separator-only handler
old2 = '''\t\t\tif not text or len(text) < 3:
\t\t\t\tif block.get('isListItem') and (not text or len(text) < 3):
\t\t\t\t\t# Empty list item \u2014 include it as an explicit empty placeholder
\t\t\t\t\tlist_level = block.get('listLevel', 0) or 0
\t\t\t\t\tpara_counter += 1
\t\t\t\t\tformatted.append(f"Paragraph {para_counter}: [EMPTY_LIST_ITEM_LEVEL_{list_level}]")
\t\t\t\telse:
\t\t\t\t\t# Check if this blank paragraph falls between two list items
\t\t\t\t\t# If so, it signals they should be in SEPARATE list tables
\t\t\t\t\tprev_is_list = False
\t\t\t\t\tnext_is_list = False
\t\t\t\t\tfor prev_idx in range(idx - 1, max(0, idx - 3), -1):
\t\t\t\t\t\tif blocks[prev_idx].get('type') == 'paragraph':
\t\t\t\t\t\t\tprev_runs = blocks[prev_idx].get('runs', [])
\t\t\t\t\t\t\tprev_text = ''.join([r.get('text', '') for r in prev_runs]).strip()
\t\t\t\t\t\t\tif prev_text:
\t\t\t\t\t\t\t\tprev_is_list = blocks[prev_idx].get('isListItem', False)
\t\t\t\t\t\t\t\tbreak
\t\t\t\t\tfor next_idx in range(idx + 1, min(len(blocks), idx + 3)):
\t\t\t\t\t\tif blocks[next_idx].get('type') == 'paragraph':
\t\t\t\t\t\t\tnext_runs = blocks[next_idx].get('runs', [])
\t\t\t\t\t\t\tnext_text = ''.join([r.get('text', '') for r in next_runs]).strip()
\t\t\t\t\t\t\tif next_text:
\t\t\t\t\t\t\t\tnext_is_list = blocks[next_idx].get('isListItem', False)
\t\t\t\t\t\t\t\tbreak
\t\t\t\t\tif prev_is_list and next_is_list:
\t\t\t\t\t\tpara_counter += 1
\t\t\t\t\t\tformatted.append(f"Paragraph {para_counter}: [LIST_SEPARATOR: blank line between list items \u2014 these are SEPARATE list groups, output as SEPARATE <div><table> blocks with <br> between them]")
\t\t\t\tcontinue'''

new2 = '''\t\t\tif not text or len(text) < 3:
\t\t\t\tif block.get('isListItem') and (not text or len(text) < 3):
\t\t\t\t\t# Empty list item \u2014 include it as an explicit empty placeholder
\t\t\t\t\tlist_level = block.get('listLevel', 0) or 0
\t\t\t\t\tpara_counter += 1
\t\t\t\t\tformatted.append(f"Paragraph {para_counter}: [EMPTY_LIST_ITEM_LEVEL_{list_level}]")
\t\t\t\telse:
\t\t\t\t\t# Check if the PREVIOUS block was also an empty non-list paragraph.
\t\t\t\t\t# If so, this block is part of an already-counted run \u2014 skip silently.
\t\t\t\t\tprev_was_empty = False
\t\t\t\t\tfor prev_idx in range(idx - 1, max(-1, idx - 5), -1):
\t\t\t\t\t\tprev_block = blocks[prev_idx]
\t\t\t\t\t\tif prev_block.get('type') != 'paragraph':
\t\t\t\t\t\t\tbreak
\t\t\t\t\t\tprev_runs = prev_block.get('runs', [])
\t\t\t\t\t\tprev_text = ''.join([r.get('text', '') for r in prev_runs]).strip()
\t\t\t\t\t\tif not prev_text or len(prev_text) < 3:
\t\t\t\t\t\t\tif not prev_block.get('isListItem'):
\t\t\t\t\t\t\t\tprev_was_empty = True
\t\t\t\t\t\tbreak  # Only check immediate predecessor

\t\t\t\t\tif not prev_was_empty:
\t\t\t\t\t\t# This is the first block of a consecutive empty run.
\t\t\t\t\t\t# Count how many consecutive empty blocks follow (including this one).
\t\t\t\t\t\tblank_count = 1
\t\t\t\t\t\tfor next_idx in range(idx + 1, len(blocks)):
\t\t\t\t\t\t\tnb = blocks[next_idx]
\t\t\t\t\t\t\tif nb.get('type') != 'paragraph':
\t\t\t\t\t\t\t\tbreak
\t\t\t\t\t\t\tnb_text = ''.join([r.get('text', '') for r in nb.get('runs', [])]).strip()
\t\t\t\t\t\t\tif (not nb_text or len(nb_text) < 3) and not nb.get('isListItem'):
\t\t\t\t\t\t\t\tblank_count += 1
\t\t\t\t\t\t\telse:
\t\t\t\t\t\t\t\tbreak

\t\t\t\t\t\tif blank_count >= 2 and seen_salutation:
\t\t\t\t\t\t\t# Emit explicit SPACING marker (only in letter body, not header preamble)
\t\t\t\t\t\t\tbr_tags = '<br>' * blank_count
\t\t\t\t\t\t\tpara_counter += 1
\t\t\t\t\t\t\tformatted.append(
\t\t\t\t\t\t\t\tf"Paragraph {para_counter}: [SPACING: {blank_count} blank lines \u2014 output exactly {br_tags}]"
\t\t\t\t\t\t\t)
\t\t\t\t\t\telse:
\t\t\t\t\t\t\t# Single blank line: check for list separator
\t\t\t\t\t\t\tprev_is_list = False
\t\t\t\t\t\t\tnext_is_list = False
\t\t\t\t\t\t\tfor prev_idx in range(idx - 1, max(0, idx - 3), -1):
\t\t\t\t\t\t\t\tif blocks[prev_idx].get('type') == 'paragraph':
\t\t\t\t\t\t\t\t\tprev_runs = blocks[prev_idx].get('runs', [])
\t\t\t\t\t\t\t\t\tprev_text_l = ''.join([r.get('text', '') for r in prev_runs]).strip()
\t\t\t\t\t\t\t\t\tif prev_text_l:
\t\t\t\t\t\t\t\t\t\tprev_is_list = blocks[prev_idx].get('isListItem', False)
\t\t\t\t\t\t\t\t\t\tbreak
\t\t\t\t\t\t\tfor next_idx in range(idx + 1, min(len(blocks), idx + 3)):
\t\t\t\t\t\t\t\tif blocks[next_idx].get('type') == 'paragraph':
\t\t\t\t\t\t\t\t\tnext_runs = blocks[next_idx].get('runs', [])
\t\t\t\t\t\t\t\t\tnext_text_l = ''.join([r.get('text', '') for r in next_runs]).strip()
\t\t\t\t\t\t\t\t\tif next_text_l:
\t\t\t\t\t\t\t\t\t\tnext_is_list = blocks[next_idx].get('isListItem', False)
\t\t\t\t\t\t\t\t\t\tbreak
\t\t\t\t\t\t\tif prev_is_list and next_is_list:
\t\t\t\t\t\t\t\tpara_counter += 1
\t\t\t\t\t\t\t\tformatted.append(f"Paragraph {para_counter}: [LIST_SEPARATOR: blank line between list items \u2014 these are SEPARATE list groups, output as SEPARATE <div><table> blocks with <br> between them]")
\t\t\t\tcontinue'''

if old2 in src:
    src = src.replace(old2, new2, 1)
    print("Change 2: Replaced empty block handler with SPACING logic")
else:
    # Try to find the section with approximate matching
    import re
    # Find the empty check block manually
    idx = src.find('\t\t\tif not text or len(text) < 3:\n\t\t\t\tif block.get(\'isListItem\')')
    if idx >= 0:
        print(f"Found empty check at char {idx}")
        # Find the closing 'continue'
        end_idx = src.find('\t\t\t\tcontinue', idx)
        if end_idx >= 0:
            end_idx = src.find('\n', end_idx) + 1
            print(f"Found continue at char {end_idx}")
            old_section = src[idx:end_idx]
            print(f"Old section length: {len(old_section)}")
            print(f"Old section preview: {repr(old_section[:200])}")
        else:
            print("ERROR: Could not find continue")
    else:
        print("ERROR: Could not find empty check block")
    exit(1)

# Change 3: Add seen_salutation tracking after formatted.append for content paragraphs
# Find the content paragraph append line and add tracking after it
old3 = '\t\t\tpara_counter += 1\n\t\t\tformatted.append(f"Paragraph {para_counter}: {cleaned_text[:char_limit]}{formatting_note}")'
new3 = '\t\t\tpara_counter += 1\n\t\t\tformatted.append(f"Paragraph {para_counter}: {cleaned_text[:char_limit]}{formatting_note}")\n\t\t\t# Track when we\'ve entered the letter body (past the preamble)\n\t\t\tif not seen_salutation and re.match(r\'Dear\\b\', cleaned_text, re.IGNORECASE):\n\t\t\t\tseen_salutation = True'
assert old3 in src, f"Change 3: marker not found. Searching for: {repr(old3[:100])}"
src = src.replace(old3, new3, 1)
print("Change 3: Added seen_salutation tracking")

# Change 4: Add trailing <br> strip to normalize_html
old4 = '\treturn normalized.strip()'
new4 = '\t# Strip trailing <br> tags at end of document\n\tnormalized = re.sub(r\'(\\s*<br>\\s*)+$\', \'\', normalized.strip())\n\n\treturn normalized.strip()'
assert src.count(old4) >= 1, "Change 4: marker not found"
src = src.replace(old4, new4, 1)
print("Change 4: Added trailing <br> strip")

open('api/generate-template.py', 'w', encoding='utf-8').write(src)
print("\nDone! Verifying syntax...")
import subprocess
result = subprocess.run(['python', '-m', 'py_compile', 'api/generate-template.py'], capture_output=True, text=True)
if result.returncode == 0:
    print("Syntax OK!")
else:
    print("SYNTAX ERROR:")
    print(result.stderr)
