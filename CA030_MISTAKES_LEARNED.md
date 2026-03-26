# CA030 Mistakes - Critical Lessons Learned

## What I Did Wrong

### 1. ❌ Used Wrong Phone Variable
**My Version**: `{[plsMatrix.LossPreventionPhoneNumberTollFree]}`  
**Correct**: `{[plsMatrix.CSPhoneNumber]}`  
**Why Wrong**: This is a CUSTOMER SERVICE initial contact letter, not a loss mitigation letter

**How to Avoid**:
- Check document type/purpose before selecting variables
- Customer Service letters → `CSPhoneNumber`
- Loss Mitigation letters → `LossPreventionPhoneNumberTollFree`
- Look at similar document examples for pattern

### 2. ❌ Didn't Use Exact Document Text
**My Version**: Made up my own phrasing with variables inserted
**Correct**: Use EXACT text from document, identify placeholder locations via empty runs

**Example**:
```
Document has: "recognizes that homeownership..." (with empty runs before)
Correct: {[plsMatrix.CompanyLongName]} recognizes that homeownership...
Wrong: I added my own version of text instead of using exact wording
```

**How to Avoid**:
- Read EVERY word from source document
- Check for empty runs to identify where placeholders go
- Copy exact phrasing, don't paraphrase
- When text seems "incomplete", look for empty runs indicating placeholders

### 3. ❌ Added Redundant Styling
**My Version**: Added `style="text-align: justify"` to every paragraph  
**Correct**: No styling needed (justify is default)

**How to Avoid**:
- Only add styling that's explicitly different from default
- Check existing templates for styling patterns
- If extraction doesn't show styling flag, don't add it

### 4. ❌ Didn't Examine Document Structure Carefully
**My Approach**: Relied on extraction alone, assumed standard structure
**Correct**: Check Word document directly for:
  - Empty runs (placeholder locations)
  - Actual text wording
  - Variable types based on document purpose

**How to Avoid**:
- Run extraction AND examine Word document runs
- Look for "smooshed" text (e.g., "atduring") indicating missing placeholders
- Check empty runs: `[print(f'Run {i}: |{r.text}|') for i, r in enumerate(p.runs)]`

## Root Cause Analysis

**PRIMARY FAILURE**: Assumed I could paraphrase/improve the document text  
**SHOULD HAVE**: Used exact document wording and identified placeholder positions

**SECONDARY FAILURE**: Didn't verify variable choice against document type  
**SHOULD HAVE**: Checked similar CA documents for correct phone variable

**TERTIARY FAILURE**: Added styling without verification  
**SHOULD HAVE**: Only added styling explicitly shown in extraction/document

## Prevention Strategy

### Before Starting ANY Document:

1. **Identify Document Type**
   - Customer Service? → Use CS variables
   - Loss Mitigation? → Use Loss Prevention variables
   - Check filename and content for clues

2. **Read Source Document Completely**
   - Don't skip ANY text
   - Look for empty runs indicating placeholders
   - Note exact wording, don't paraphrase

3. **Check Similar Examples**
   - Find documents with same prefix (CA, LM, etc.)
   - Verify variable patterns
   - Check styling patterns

4. **Verify Every Variable**
   - Don't assume - check against examples
   - Wrong variable = broken template

5. **Only Add Explicit Styling**
   - If extraction doesn't show it, don't add it
   - Check if styling is default before adding

## Updated Checklist Items Added

✅ **CRITICAL RULE #1**: USE EXACT DOCUMENT TEXT - NEVER MAKE UP WORDING  
✅ **Variable Verification**: Check document type before selecting phone/contact variables  
✅ **No Redundant Styling**: Only add styling that's explicitly different from default  
✅ **Empty Run Detection**: Examine Word document runs to find placeholder locations  

## Success Criteria for Next Document

- [ ] Identified document type (CS vs Loss Mit)
- [ ] Used exact document wording (no paraphrasing)
- [ ] Verified variables match document type
- [ ] Checked for empty runs to locate placeholders
- [ ] Only added styling explicitly shown
- [ ] Compared with similar examples

**NEVER AGAIN**: Making up text or using wrong variables!
