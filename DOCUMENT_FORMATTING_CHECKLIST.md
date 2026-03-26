# Document Formatting Analysis Checklist

## ⚠️⚠️ CRITICAL RULE #1: USE EXACT DOCUMENT TEXT - NEVER MAKE UP WORDING

**NEVER paraphrase or rewrite the document text!**

### Common Mistake Example (CA030):
- ❌ **WRONG**: "You may contact us by phone toll-free at {[plsMatrix.LossPreventionPhoneNumberTollFree]} during business hours"
- ✅ **CORRECT**: "You may contact us by phone toll-free at {[plsMatrix.CSPhoneNumber]} during business hours"
- **Issues**: Wrong variable (Loss Prevention vs Customer Service) AND didn't verify exact document wording

### How to Avoid:
1. **Read EVERY word** from the source document - don't assume phrasing
2. **Check empty runs** in Word document to identify WHERE placeholders go
3. **Use correct variable** based on document type:
   - Customer Service letters → `CSPhoneNumber`
   - Loss Mitigation letters → `LossPreventionPhoneNumberTollFree`
4. **Don't add styling** unless extraction shows it (e.g., `text-align: justify` is redundant if default)
5. **Compare with similar documents** to verify variable choices

## ⚠️ CRITICAL RULE #2: USE EXTRACTION DATA AS PRIMARY SOURCE OF TRUTH

**DO NOT RELY ON VISUAL INSPECTION ALONE!**

### MANDATORY FIRST STEP: Run Universal Extraction Tool

**USE THE UNIVERSAL TOOL - NO MORE CUSTOM SCRIPTS!**

1. **ALWAYS run the UNIVERSAL extraction tool FIRST**:
   ```powershell
   python tools/extract-document.py "DOCUMENT-NAME.docx"
   ```
   
   Example:
   ```powershell
   python tools/extract-document.py "LM250 - GSE RPP Offer CBRP - Keesler - V1.0.docx"
   ```

2. **Search for ALL formatting markers** in the output:
   ```powershell
   # Find all BOLD markers
   python tools/extract-document.py "DOCUMENT.docx" 2>&1 | Select-String -Pattern "\[BOLD"
   
   # Find all FONT_SIZE markers (non-default sizes)
   python tools/extract-document.py "DOCUMENT.docx" 2>&1 | Select-String -Pattern "FONT_SIZE"
   
   # Find all UNDERLINE markers
   python tools/extract-document.py "DOCUMENT.docx" 2>&1 | Select-String -Pattern "\[.*UNDERLINE"
   
   # Find all ALIGNMENT markers (non-left)
   python tools/extract-document.py "DOCUMENT.docx" 2>&1 | Select-String -Pattern "ALIGN_"
   ```

3. **The universal tool extracts EVERYTHING**:
   - ✅ BOLD, UNDERLINE, ITALIC
   - ✅ FONT_SIZE_XXpt (only non-default, i.e., not 11pt)
   - ✅ ALIGN_CENTER, ALIGN_RIGHT, ALIGN_JUSTIFY
   - ✅ Table content with cell-level formatting
   - ✅ Works for ANY document - no custom scripts needed
3. **Create a checklist of EVERY [BOLD] marker**
4. **Systematically verify each marker is reflected in your HTML**
5. **NEVER skip this step** - extraction data is authoritative, screenshots are supplementary

### Why This Matters:
- ❌ Visual inspection misses subtle formatting
- ❌ Screenshots don't always show all details
- ❌ Assumptions about "typical" formatting are often wrong
- ✅ Extraction data contains explicit [BOLD], [UNDERLINE], [FONT_SIZE] markers
- ✅ Systematic verification catches 100% of formatting flags
- ✅ No guessing required - the data tells you exactly what should be formatted

### ⚠️ CRITICAL: When Extraction and Reality Diverge

**Extraction data is PRIMARY but not always SUFFICIENT:**

**Scenario 1: Extraction shows [BOLD] but visual shows NOT bold**
- Happens with conditional logic or metadata highlighting
- **Solution**: Trust the VISUAL/screenshot, not extraction
- **Example**: "You were evaluated for..." showed [BOLD] in extraction but is actually NOT bold in final output

**Scenario 2: Extraction shows [BOLD] for entire line but only PART is bold**
- Happens with inline/partial formatting
- **Solution**: Examine run-level data or open Word doc directly
- **Example**: "...accept this offer, OR" - only "OR" is bold

**Scenario 3: Extraction doesn't show styling but visual does**
- Rare but possible
- **Solution**: Visual wins - add the formatting

**Cross-Reference Process:**
1. Start with extraction data
2. For ANY unexpected patterns (bold + conditional, bold on long paragraphs), verify visually
3. If extraction contradicts visual, **trust visual**
4. Update your HTML based on VISUAL TRUTH, not extraction alone

## BEFORE STARTING ANY FORMATTING WORK

### Step 1: Extract and Analyze Document Structure
1. Run extraction script to get full document content with formatting flags (see CRITICAL section above)
2. Review ENTIRE document for:
   - Section headers (usually bold)
   - Paragraph text (check extraction for [BOLD] flag specifically)
   - Special formatting (underline, italics, ALL CAPS)
   - Alignment (center, left, right)

**CRITICAL - Ignore Metadata Highlighting:**
- ❌ **Yellow/blue highlighting** in source documents is metadata (variable names, conditional markers)
- ❌ **Colored text** in source is often just to show conditionals, NOT actual text color
- ✅ Only apply actual formatting shown in final rendered document or screenshots
- ✅ If unsure about a color, ask - don't assume highlighted = colored text

### Step 2: Identify Special Styled Elements
Check for:
- **Colored boxes/backgrounds** (blue, light blue, etc.)
  - Note exact hex colors from screenshots
  - Check for border styles (solid, width, color)
  - Check for border-radius (rounded vs square corners)
- **Banner headers** (colored backgrounds with text)
- **Tables** (standard vs styled)
- **Signature blocks** (special alignment/formatting)
- **Text colors** (blue, red, etc. for emphasis or special sections)
  - Investor-specific text often in blue
  - Check INSIDE styled boxes for colored text
- **Underlines** on URLs, emphasized text
  - ALL URLs should typically be underlined
  - Check for bold+underline combinations

### Step 3: Font Size Analysis
**CRITICAL: Banner headers and titles often have larger font sizes (14pt, 16pt)**

Common font sizes to check:
- **Banner headers** ("ACT NOW!", "Additional Repayment Plan Information") → Often 14pt
- **Section headers** ("What is a Repayment Plan?", "To Prevent Foreclosure Action") → Check document
- **Body text** → Default 11pt
- **Styled box titles** → May be 12pt or 14pt

How to check:
1. Create a font checker script (see example above)
2. Run it to identify all non-default font sizes
3. Apply `style="font-size: XXpt"` to matching elements in HTML

**Common mistake:**
- ❌ Assuming all text is default size
- ✅ Check banner/title text for larger fonts

### Step 4: Bold Text Analysis - PARAGRAPH AND RUN-LEVEL
**CRITICAL: Check for BOTH full-paragraph bold AND inline/partial bold**

**TWO LEVELS OF BOLD DETECTION REQUIRED:**

1. **Paragraph-Level Bold** (entire paragraph):
   - Section headers ("What is a Repayment Plan?", "To Prevent Foreclosure Action")
   - Full paragraphs that are entirely bold
   - Check extraction for line with [BOLD] flag

2. **Run-Level Bold** (partial/inline within paragraph):
   - ⚠️ **THIS IS WHAT YOU KEEP MISSING!**
   - Bold on SPECIFIC WORDS within a regular paragraph
   - Examples: "...accept this offer, **OR**", "review the **Additional Resources** for more"
   - **HOW TO DETECT**: Extraction shows [BOLD] but only some runs within paragraph are bold
   - **REQUIRES**: Examine run-by-run data, not just paragraph-level

**Process for detecting inline bold:**
```powershell
# Use universal extraction tool
python tools/extract-document.py "DOCUMENT.docx" > extraction-full.txt

# Look for paragraphs with [BOLD] flag
# For each one, check if ENTIRE paragraph should be bold or just parts
# If unsure, examine the Word document directly at that line
```

**Common mistakes to AVOID:**
- ❌ **Missing inline bold** - most common error! (e.g., missing bold on "OR", "Additional Resources")
- ❌ Bolding entire paragraphs when only specific words are bold
- ❌ Over-bolding - applying bold to conditional wrappers instead of content
- ❌ Trusting extraction alone - extraction shows [BOLD] but may not indicate if partial

**CRITICAL Rules:**
- Some entire paragraphs ARE bold - verify each individually
- Some paragraphs have ONLY specific words bold - check run-level data
- When extraction shows [BOLD] + conditional logic, verify carefully (may be metadata)
- Formatting goes INSIDE conditional variables, not around the conditional wrapper

### Step 5: Bullet Points and Check Marks
1. Identify bullet style:
   - Standard round bullets (•) → `<td width="3%" valign="top" style="text-align: center">•</td>`
   - **Square bullets (■)** → `<td width="3%" valign="top" style="text-align: center; font-size: 8pt">■</td>` (smaller font)
   - Check marks → Use: `&#10004;` (✔ heavy check mark)
   - Light check marks → Use: `&#10003;` (✓)
   - Numbered lists (1., 2., 3.)
2. Check for left margin/indentation on bullet groups
3. Verify bullet point content is NOT bolded unless source shows bold
4. **CRITICAL**: Different sections may use DIFFERENT bullet styles - check each section separately
5. **Square bullets should be smaller** - use `font-size: 8pt` on the bullet cell

### Step 6: Table Analysis
Check for:
- **Standard tables** (Loan Number/RE)
  - Labels bold or not bold? (verify from screenshots)
  - Column widths
  - Alignment
- **Bullet point tables** (for formatting bullets)
  - Width percentages
  - Border-collapse
  - Alignment
- **Styled tables** (with backgrounds, borders)
  - Background colors
  - Border styles
  - Padding

### Step 7: Box/Banner Styling Verification
**CRITICAL: Verify EVERY attribute for EVERY box - DO NOT ASSUME CONSISTENCY**

**⚠️ MAJOR MISTAKE**: Assuming all styled boxes have same padding/styling
- ❌ WRONG: "All banners probably have 8pt padding"  
- ✅ CORRECT: Check EACH box individually, padding can vary (1pt vs 8pt)

**Create a table for EACH styled box:**

| Box Name | Width | Border | BG Color | Text Color | Padding | Alignment |
|----------|-------|--------|----------|------------|---------|-----------|
| QUESTIONS? | 95% | 1pt solid blue | Light blue | Black | 8pt | center |
| ACT NOW! | 95% | 1pt solid blue | Dark blue | White | 1pt | center |
| Additional Resources | 95% | 1pt solid blue | Lavender | Black | 8pt | left |
| Add'l Repay Info | 95% | 1pt solid blue | Dark blue | White | 1pt | center |

**For each styled box, verify individually:**
1. **Width** - don't assume all are same
2. **Border** - width, style, color
3. **Background color** - exact hex/rgba
4. **Text color** - especially white vs black
5. **Padding** - ⚠️ VARIES! Some boxes are 1pt, others 8pt
6. **Alignment** - center vs left
7. **Margin** - spacing around box
8. **Font size** - banners often 14pt, check EACH one

**NO ASSUMPTIONS - VERIFY EACH ATTRIBUTE FOR EACH BOX**

### Step 8: Content Completeness Check
Verify ALL content sections are included:
- Header and date
- Mailing address
- Loan Number/RE table
- Salutation
- All body paragraphs (in exact order)
- All sections with headers
- All styled boxes
- All bullet points/tables
- Conditional sections (If statements)
- Signature block

### Step 9: Conditional Logic Verification
Check for:
- Investor conditionals (M944 = 'F' for Fannie, 'H' for Freddie)
- Occupancy conditionals (M657 = '1')
- SPOC conditionals (O274, O294)
- Date/calculation conditionals
- Verify placement (inside boxes, outside boxes)

**CRITICAL: Conditional Formatting Rules**

**❌ WRONG - Formatting AROUND conditional wrapper:**
```html
<div><b><u>{If('{[O274]}' NOT IN ('', '0', NULL))}{[O274]}{Else}...{End If}</u></b></div>
```

**✅ CORRECT - Formatting INSIDE conditional (on the variables):**
```html
<div>{If('{[O274]}' NOT IN ('', '0', NULL))}{[O274]}{Else}...{End If}</div>
```

**Rule**: Formatting applies to the CONTENT being rendered, not the conditional logic wrapper.

**Exception**: When entire conditional BLOCK needs container styling:
```html
<div style="background-color: blue">
{If('{[M657]}' = '1')}
<div><b>Conditional content here</b></div>
{End If}
</div>
```

**When in doubt**: Check other templates for conditional formatting patterns.

### Step 10: Variable and Function Syntax
Verify:
- `{[TAG]}` format for variables
- `{[plsMatrix.*]}` for company variables
- `{Math(...|Money)}` for calculations
- `{Date(...|format)}` for date formatting
- `{DateAdd(...|+/-days|format|unit)}` for date calculations
- `{Compress(...)}` for multi-line compression
- `{If(...)}...{Else If(...)}...{Else}...{End If}` for conditionals
- **`{Symbol(ü)}`** for Wingdings check mark ✓
- `{FUNCTIONNAME()}` for other function calls (e.g., `{Q189V2()}`)

**CRITICAL**: Some variables are FUNCTIONS (e.g., `{Q189V2()}`), not simple variables (`{[Q189]}`). Check extraction for function indicators.

### Step 11: Final Comparison - SYSTEMATIC VERIFICATION REQUIRED
**MANDATORY before submitting:**

1. **Extract formatting flags and create verification checklist**:
   - Count total [BOLD] markers in extraction
   - Count total `<b>` tags in your HTML
   - **Numbers should match!**
   
2. **Line-by-line comparison**:
   - For EACH line with [BOLD] in extraction → verify `<b>` in HTML
   - For EACH line with [UNDERLINE] in extraction → verify `<u>` in HTML
   - For EACH styled element in extraction → verify CSS in HTML
   
3. **Reverse check**:
   - For EACH `<b>` tag in your HTML → verify [BOLD] exists in extraction
   - If you bolded something without a [BOLD] marker → REMOVE IT
   
4. **Visual verification** (secondary, after data verification):
   - Check screenshots provided by user
   - Verify all styled boxes match screenshots
   - Verify all content is present in correct order

5. **Self-audit questions**:
   - Did I check extraction data for EVERY section?
   - Did I verify EVERY formatting flag systematically?
   - Did I assume ANY formatting without checking extraction?
   - If yes to #3 → GO BACK and verify with extraction data

## COMMON MISTAKES TO AVOID

### ⚠️ MOST CRITICAL MISTAKES (LM250 Lessons)

1. **❌ MISSING INLINE/PARTIAL BOLD** ← **MOST COMMON ERROR**
   - Checking only if ENTIRE paragraphs are bold
   - Missing bold on SPECIFIC WORDS within paragraphs
   - Example: Missing bold on "OR", "Additional Resources" within regular text
   - **FIX**: Examine run-level data for EVERY line marked [BOLD]

2. **❌ ASSUMING STYLING CONSISTENCY**
   - Assuming all styled boxes have same padding
   - Not verifying EACH box individually
   - Example: ACT NOW has `padding: 1pt`, QUESTIONS has `padding: 8pt`
   - **FIX**: Create table with attributes for EVERY styled element

3. **❌ TRUSTING EXTRACTION OVER VISUAL**
   - Extraction shows [BOLD] but final output isn't bold
   - Happens with conditional logic or metadata highlighting
   - Example: "You were evaluated..." extraction showed [BOLD] but should NOT be bold
   - **FIX**: Cross-reference extraction with visual verification

4. **❌ FORMATTING CONDITIONAL WRAPPERS INSTEAD OF CONTENT**
   - Putting `<b><u>` around entire `{If()...{End If}` block
   - Should only format the content variables
   - Example: SPOC name formatting
   - **FIX**: Formatting goes on variables, not conditional wrapper

5. **❌ WRONG FUNCTION FORMATS**
   - Using `{[Q189]}` instead of `{Q189V2()}`
   - Not recognizing function calls vs variables
   - **FIX**: Check extraction for function indicators, verify exact syntax

6. **❌ USING HTML ENTITIES INSTEAD OF DIRECT UNICODE**
   - Using `&#10004;` instead of `✔`
   - **FIX**: Check existing templates for character usage patterns

### Bolding Errors
- ❌ Making entire paragraphs bold when only the header is bold
- ❌ Making bullet/check mark items bold when they're regular text
- ❌ Making "You must..." statements bold when they're regular text
- ✅ Only bold section headers and specifically emphasized text shown in source

### Styling Errors
- ❌ Adding border-radius when boxes have square corners
- ❌ Wrong background colors (ask for exact hex if unsure)
- ❌ Wrong border colors or widths
- ❌ **Applying metadata colors as actual styling** (blue/yellow highlighting is metadata, not text color!)
- ❌ **Missing underlines** on URLs and emphasized text
- ❌ Using round bullets (•) when square bullets (■) are shown
- ❌ Square bullets too large (should be `font-size: 8pt`)
- ❌ **Adding redundant styling** (e.g., `text-align: justify` when it's default)
- ❌ **Using wrong variable** (CSPhoneNumber vs LossPreventionPhoneNumber - check document type!)
- ✅ Ask for exact styling details if screenshots show styling
- ✅ **Check EVERY URL for underlines**
- ✅ **Ignore colored highlighting in source** - it's metadata, not styling
- ✅ **Only apply colors shown in final screenshots**, not source highlighting
- ✅ **Only apply styling that's explicitly shown** - don't add defaults

### Content Errors
- ❌ Moving conditional text outside of boxes when it should be inside
- ❌ Skipping sections or bullet points
- ❌ Reordering content
- ❌ **Incorrectly combining bold+underline** when only bold is shown (verify each carefully!)
- ❌ **Over-underlining** - adding underlines to regular text when only specific words/URLs should be underlined
- ✅ Maintain exact order and structure from source
- ✅ **Check for multi-level formatting** (bold AND underline together)
- ✅ **Underline ONLY specific elements**: URLs, emphasized technical terms, specific phrases shown in screenshots
- ✅ **Don't underline entire phrases** - only underline what's specifically marked

### Check Mark/Bullet Errors
- ❌ Using wrong character (•, ✓, ☑, √)
- ❌ Using HTML entities (`&#10004;`, `&#10003;`) instead of template functions
- ❌ Using direct Unicode when template function is required
- ❌ Using round bullets when square bullets are shown
- ✅ **Check mark: `{Symbol(ü)}` - THIS IS THE CORRECT WINGDINGS CHECK MARK**
- ✅ Square bullet: `■` (direct Unicode)
- ✅ Round bullet: `•` (direct Unicode)
- ✅ Asterisk bullet: `*` (direct character)
- ✅ **Different sections may use different bullet types - check each section**
- ✅ **ALWAYS use `{Symbol(ü)}` for check marks** - this renders as Wingdings check mark ✓

## QUESTIONS TO ASK BEFORE FINALIZING

1. "Are there any styled boxes I missed?"
2. "Should [element] be bold or regular text?"
3. "What is the exact background color?" (if not clear)
4. "Are the borders rounded or square?"
5. "Should this conditional text be inside or outside the box?"
6. "What check mark character should I use?"

## ANALYSIS ORDER - CRITICAL SEQUENCE

1. **FIRST**: Run universal extraction tool (`python tools/extract-document.py "DOC.docx"`)
2. **SECOND**: Identify all styled elements (boxes, banners, tables) - create attribute table for EACH
3. **THIRD**: **RUN-LEVEL ANALYSIS** - for EVERY line with [BOLD]:
   - Is ENTIRE paragraph bold? → Check extraction
   - Is ONLY specific words bold? → Examine run data or Word doc directly
   - **THIS IS WHERE YOU KEEP FAILING - DON'T SKIP THIS STEP**
4. **FOURTH**: Verify font sizes - check tables and banners (often 14pt)
5. **FIFTH**: Check for special characters (check marks, square bullets, round bullets)
6. **SIXTH**: **Check for text colors** (blue, red, etc.) - especially inside styled boxes
7. **SEVENTH**: **Check for underlines** - ALL URLs and emphasized text
8. **EIGHTH**: **Check for combined formatting** (bold+underline, color+underline, etc.)
9. **NINTH**: Verify conditional placement (inside or outside boxes)
10. **TENTH**: Cross-reference extraction with visual verification
    - If extraction shows [BOLD] + conditional → verify visually
    - If extraction contradicts visual → **trust visual**
11. **ELEVENTH**: Build HTML with correct styling
12. **TWELFTH**: Self-review against screenshots SECTION BY SECTION before submitting
13. **THIRTEENTH**: Run verification counts:
    ```powershell
    # Count [BOLD] in extraction (full + inline)
    # Count <b> tags in HTML
    # Numbers should be close (accounting for conditionals)
    ```

## DETAILED REVIEW FOR STYLED BOXES

When reviewing styled boxes (like "Additional Resources"), check:
1. ✅ Background color correct?
2. ✅ Border style correct (width, color, square/rounded)?
3. ✅ Are bullets round (•) or square (■)? Are square bullets smaller (8pt)?
4. ✅ Are ALL URLs underlined (and ONLY URLs)?
5. ✅ Is there text with special colors? (Verify from screenshots, not source highlighting)
6. ✅ Are there bold+underline combinations? (Check carefully - some text may be bold-only, not bold+underline)
7. ✅ Are conditional sections inside or outside the box?
8. ✅ Does conditional text have special formatting (color, bold, underline)?
9. ✅ **Check each word/phrase individually** - don't apply formatting to entire sentences
10. ✅ **Verify against screenshot** - if text looks regular in screenshot, don't add bold/underline

## HOW TO CATCH YOUR OWN MISTAKES (NO SCREENSHOTS NEEDED)

### The Systematic Approach:

1. **Run the universal extraction tool**:
   ```powershell
   python tools/extract-document.py "DOCUMENT.docx" > extraction-output.txt 2>&1
   ```

2. **Build formatting index from extraction output**:
   - Search extraction for `[BOLD]` → note line numbers
   - Search extraction for `[UNDERLINE]` → note line numbers
   - Search extraction for `[FONT_SIZE_XXpt]` → note ALL non-default sizes (14pt, 16pt, etc.)
   - Search extraction for `[ALIGN_XXX]` → note center/right/justify alignments
   - **NO CUSTOM SCRIPTS NEEDED** - universal tool captures everything

3. **Build HTML verification checklist**:
   - For each [BOLD] marker at line X:
     - Find corresponding text in your HTML
     - Verify `<b>` tags surround it
     - Check off when verified
   
4. **Count and compare**:
   - Total [BOLD] markers in extraction: ___
   - Total `<b>` tags in your HTML: ___
   - **If numbers don't match → investigate every discrepancy**

5. **Use terminal commands for verification**:
   ```powershell
   # Count BOLD markers in extraction
   python tools/extract-document.py "DOCUMENT.docx" 2>&1 | Select-String -Pattern "\[.*BOLD" | Measure-Object | Select-Object -ExpandProperty Count
   
   # Count FONT_SIZE markers in extraction
   python tools/extract-document.py "DOCUMENT.docx" 2>&1 | Select-String -Pattern "FONT_SIZE" | Measure-Object | Select-Object -ExpandProperty Count
   
   # Count <b> tags in your HTML
   Select-String -Pattern "<b>" -Path "formatter examples/DOCNAME/DOCNAME-formatted.html" | Measure-Object | Select-Object -ExpandProperty Count
   
   # Count font-size styles in your HTML
   Select-String -Pattern "font-size:" -Path "formatter examples/DOCNAME/DOCNAME-formatted.html" | Measure-Object | Select-Object -ExpandProperty Count
   ```

### Why This Works:
- ✅ **Data-driven**: Based on extraction flags, not subjective visual assessment
- ✅ **Complete**: Catches 100% of formatting markers
- ✅ **Verifiable**: Counts must match
- ✅ **Independent**: No screenshots needed for initial formatting
- ✅ **Repeatable**: Same process works for every document

### When You Realize You Missed Something:
1. **Don't just fix the immediate issue**
2. **Ask yourself**: "Why didn't I catch this with extraction data?"
3. **Update your process** to prevent similar misses
4. **Run full verification again** to catch other similar issues

## WHEN IN DOUBT

- **ASK** for clarification with specific questions
- **COMPARE** with other completed examples in the codebase
- **VERIFY** with screenshots provided
- **DON'T ASSUME** - especially with bold formatting and styling
- **CHECK EXTRACTION DATA FIRST** - before asking for screenshots
