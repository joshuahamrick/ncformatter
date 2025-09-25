from http.server import BaseHTTPRequestHandler
import json
import base64
import io
import traceback

# Try to import docx, but handle if it's not available
try:
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

import re

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        """Handle POST requests to process Word documents"""
        
        try:
            # Get content length
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Parse JSON data
            data = json.loads(post_data.decode('utf-8'))
            file_data = data.get('fileData')
            file_name = data.get('fileName', 'document.docx')
            
            if not file_data:
                self.send_error_response(400, 'No file data provided')
                return
            
            if not DOCX_AVAILABLE:
                self.send_error_response(500, 'python-docx library not available')
                return
            
            # Decode base64 file data
            file_bytes = base64.b64decode(file_data)
            
            # Process the Word document
            result = process_word_document(file_bytes, file_name)
            
            # Send success response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
            self.end_headers()
            
            response = json.dumps(result)
            self.wfile.write(response.encode('utf-8'))
            
        except Exception as e:
            # Send detailed error response
            error_msg = f"Error: {str(e)}\nTraceback: {traceback.format_exc()}"
            self.send_error_response(500, error_msg)
    
    def send_error_response(self, status_code, message):
        """Send error response with proper headers"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = json.dumps({'error': message, 'success': False})
        self.wfile.write(response.encode('utf-8'))
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.end_headers()

def process_word_document(file_bytes, file_name):
    """Process Word document and extract all formatting information"""
    
    try:
        # Load the document
        doc = Document(io.BytesIO(file_bytes))
        
        # Extract document structure with full formatting
        paragraphs = []
        tables = []
        
        # Process paragraphs
        for para in doc.paragraphs:
            paragraph_data = extract_paragraph_formatting(para)
            paragraphs.append(paragraph_data)
        
        # Process tables
        for table in doc.tables:
            table_data = extract_table_formatting(table)
            tables.append(table_data)
        
        # Detect document type and apply specific processing
        document_type = detect_document_type(paragraphs)
        
        # Generate the formatted HTML
        formatted_html = generate_formatted_html(paragraphs, tables, document_type)
        
        # Apply universal formatting rules
        formatted_html = apply_universal_formatting_rules(formatted_html)
        
        return {
            'success': True,
            'formattedHtml': formatted_html,
            'documentType': document_type,
            'paragraphs': paragraphs,
            'tables': tables
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Error processing document: {str(e)}',
            'formattedHtml': f'<div>Error processing document: {str(e)}</div>'
        }

def extract_paragraph_formatting(paragraph):
    """Extract all formatting information from a paragraph"""
    
    para_data = {
        'text': '',
        'alignment': 'left',
        'fontSize': None,
        'bold': False,
        'underline': False,
        'italic': False,
        'runs': []
    }
    
    # Get paragraph alignment
    alignment = paragraph.paragraph_format.alignment
    if alignment:
        if alignment == WD_ALIGN_PARAGRAPH.CENTER:
            para_data['alignment'] = 'center'
        elif alignment == WD_ALIGN_PARAGRAPH.RIGHT:
            para_data['alignment'] = 'right'
        elif alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
            para_data['alignment'] = 'justify'
    
    # Process each run in the paragraph
    full_text = ''
    for run in paragraph.runs:
        run_data = {
            'text': run.text,
            'bold': run.bold,
            'underline': run.underline,
            'italic': run.italic,
            'fontSize': None
        }
        
        # Get font size
        if run.font.size:
            run_data['fontSize'] = str(int(run.font.size.pt)) + 'pt'
        
        para_data['runs'].append(run_data)
        full_text += run.text
    
    para_data['text'] = full_text
    
    # Set paragraph-level formatting based on runs
    if para_data['runs']:
        para_data['bold'] = all(run['bold'] for run in para_data['runs'] if run['text'].strip())
        para_data['underline'] = any(run['underline'] for run in para_data['runs'])
        para_data['italic'] = any(run['italic'] for run in para_data['runs'])
    
    return para_data

def extract_table_formatting(table):
    """Extract formatting information from a table"""
    
    table_data = {
        'rows': [],
        'width': '100%',
        'borderCollapse': True
    }
    
    for row in table.rows:
        row_data = {'cells': []}
        
        for cell in row.cells:
            cell_data = {
                'text': cell.text,
                'width': None,
                'alignment': 'left',
                'bold': False,
                'underline': False
            }
            
            # Get cell formatting
            if cell.paragraphs:
                para = cell.paragraphs[0]
                if para.runs:
                    run = para.runs[0]
                    cell_data['bold'] = run.bold
                    cell_data['underline'] = run.underline
            
            row_data['cells'].append(cell_data)
        
        table_data['rows'].append(row_data)
    
    return table_data

def detect_document_type(paragraphs):
    """Detect the type of document based on content"""
    
    all_text = ' '.join([p['text'] for p in paragraphs])
    
    # Check for H003 TagHeader
    if re.search(r'\{Insert\(H003\s+TagHeader\)\}', all_text):
        return 'H003'
    elif re.search(r'Notice of Intention to Foreclose', all_text):
        return 'BR010'
    elif re.search(r'Notice of Default and Right to Cure', all_text):
        return 'BR017'
    elif re.search(r'Privacy Policy|FACTS', all_text):
        return 'PRIVACY'
    elif re.search(r'maturity date|payoff statement', all_text):
        return 'SL106'
    else:
        return 'GENERIC'

def generate_formatted_html(paragraphs, tables, document_type):
    """Generate the final formatted HTML with proper structure"""
    
    html_parts = []
    
    # Process each paragraph individually but with smart replacements
    for para in paragraphs:
        if not para['text'].strip():
            continue
            
        text = para['text'].strip()
        
        # Create the div with proper formatting
        div_attrs = []
        
        # Add alignment
        if para['alignment'] != 'left':
            div_attrs.append(f'text-align: {para["alignment"]}')
        
        # Add font size (if consistent across runs)
        font_sizes = [run['fontSize'] for run in para['runs'] if run['fontSize']]
        if font_sizes and len(set(font_sizes)) == 1:
            div_attrs.append(f'font-size: {font_sizes[0]}')
        
        # Build the div tag
        div_style = f' style="{"; ".join(div_attrs)}"' if div_attrs else ''
        
        # Process the text with formatting
        formatted_text = process_text_with_formatting(para['runs'])
        
        html_parts.append(f'<div{div_style}>{formatted_text}</div>')
    
    return '\n<br>\n'.join(html_parts)

def process_section(paragraphs, section_type):
    """Process a section of paragraphs based on its type"""
    
    if not paragraphs:
        return ''
    
    if section_type == 'header':
        # Create clean header structure
        return '''<div>{Insert(H003 TagHeader)}</div>
<br>
<div>{[L001]}</div>
<br>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>'''
    
    elif section_type == 'title':
        # Create centered document title
        title_text = paragraphs[0]['text'].strip()
        if 'Notice of Intention' in title_text:
            return '<div style="text-align: center"><b>Notice of Intention to Foreclose Mortgage</b></div>'
        elif 'Notice of Default' in title_text:
            return '<div style="text-align: center"><b>Notice of Default</b></div>'
        else:
            return f'<div style="text-align: center"><b>{title_text}</b></div>'
    
    elif section_type == 'borrower':
        # Create RE table structure
        return '''<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="20%"><b>Borrower Name:</b></td>
  <td>{[M558]}{If('{[M559]}'&lt;&gt;'')} and {[M559]}{End If}</td>
  </tr><tr>
  <td width="20%" valign="top"><b>Mailing Address:</b></td>
  <td>{Compress({[M561]}|{[M562]}|{[M563]}{[M564]}{[M565]}{[M566]})}</td>
  </tr><tr>
  <td width="20%"><b>Mortgage Loan No:</b></td>
  <td>{[M594]}</td>
  </tr><tr>
  <td width="20%"><b>Property Address:</b></td>
  <td>{Compress({[M567]}|{[M583]})}</td>
</tr></tbody></table></div>'''
    
    elif section_type == 'salutation':
        # Create clean salutation
        return '<div>Dear {[Salutation]},</div>'
    
    elif section_type == 'payment':
        # Create payment table
        return '''<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="50%">Number of Payments Due:</td>
  <td>{[M590]}</td>
  </tr><tr>
  <td width="50%">Net Payment Amount:</td>
  <td>{Money}</td>
  </tr><tr>
  <td width="50%">Unpaid Late Charges:</td>
  <td>{Money}</td>
  </tr><tr>
  <td width="50%">NSF & Other Fees:</td>
  <td>{Money} + {Money}</td>
  </tr><tr>
  <td width="50%">Unapplied/Suspense Funds:</td>
  <td>{Money}</td>
</tr></tbody></table></div>'''
    
    else:
        # Regular content - process normally
        html_parts = []
        for para in paragraphs:
            div_attrs = []
            
            # Add alignment
            if para['alignment'] != 'left':
                div_attrs.append(f'text-align: {para["alignment"]}')
            
            # Add font size (if consistent across runs)
            font_sizes = [run['fontSize'] for run in para['runs'] if run['fontSize']]
            if font_sizes and len(set(font_sizes)) == 1:
                div_attrs.append(f'font-size: {font_sizes[0]}')
            
            # Build the div tag
            div_style = f' style="{"; ".join(div_attrs)}"' if div_attrs else ''
            
            # Process the text with formatting
            formatted_text = process_text_with_formatting(para['runs'])
            
            html_parts.append(f'<div{div_style}>{formatted_text}</div>')
        
        return '\n'.join(html_parts)

def process_text_with_formatting(runs):
    """Process text runs and apply formatting tags"""
    
    formatted_text = ''
    
    for run in runs:
        text = run['text']
        if not text:
            continue
            
        # Apply formatting tags
        if run['bold']:
            text = f'<b>{text}</b>'
        if run['underline']:
            text = f'<u>{text}</u>'
        if run['italic']:
            text = f'<i>{text}</i>'
        
        # Apply font size if present (wrap around formatting tags)
        if run['fontSize']:
            text = f'<span style="font-size: {run["fontSize"]}">{text}</span>'
        
        formatted_text += text
    
    return formatted_text

def apply_universal_formatting_rules(html_text):
    """Apply universal formatting rules to any document"""
    
    try:
        # 1. Fix field names first (clean up descriptive text)
        html_text = fix_field_names(html_text)
        
        # 2. Wrap money fields
        html_text = wrap_money_fields(html_text)
        
        # 3. Fix the header structure completely
        html_text = fix_header_structure_completely(html_text)
        
        # 4. Add document title and RE table
        html_text = add_document_title_and_re_table(html_text)
        
        # 5. Fix salutation section
        html_text = fix_salutation_section(html_text)
        
        # 6. Fix payment information
        html_text = fix_payment_information(html_text)
        
        # 7. Add plsMatrix prefixes where needed
        html_text = add_pls_matrix_prefixes(html_text)
        
        # 8. Clean excessive formatting
        html_text = clean_excessive_formatting(html_text)
        
    except Exception as e:
        # If any step fails, return the original text with error info
        html_text = f'<div style="color: red;">Universal formatting error: {str(e)}</div>' + html_text
    
    return html_text

def fix_header_structure_completely(text):
    """Completely replace the messy header with clean structure"""
    # Find the start of the document (first tagHeader with any content after it)
    # More flexible pattern to handle {[tagHeader]}(Company Address Line 1)
    start_match = re.search(r'<div[^>]*>\{\[tagHeader\]\}[^<]*</div>', text)
    if not start_match:
        # Try alternative pattern
        start_match = re.search(r'<div[^>]*>\{\[tagHeader\]\}[^<]*</div>', text)
    if not start_match:
        return text
    
    # Find where the header section ends (before any borrower info or Dear)
    end_patterns = [
        r'<div[^>]*>Borrower Name:',
        r'<div[^>]*>Dear',
        r'<div[^>]*>Notice is hereby given',
        r'<div[^>]*>To cure'
    ]
    
    end_pos = None
    for pattern in end_patterns:
        end_match = re.search(pattern, text)
        if end_match:
            end_pos = end_match.start()
            break
    
    if end_pos:
        # Replace the entire header section
        clean_header = '''<div>{Insert(H003 TagHeader)}</div>
<br>
<div>{[L001]}</div>
<br>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>'''
        
        text = text[:start_match.start()] + clean_header + text[end_pos:]
    
    return text

def add_document_title_and_re_table(text):
    """Add document title and RE table structure"""
    # Add document title after the header
    header_end = re.search(r'<br><br><br><br><br>', text)
    if header_end:
        insert_pos = header_end.end()
        
        title_html = '''<div style="text-align: center"><b>Notice of Intention to Foreclose Mortgage</b></div>
<br>'''
        
        re_table_html = '''<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="20%"><b>Borrower Name:</b></td>
  <td>{[M558]}{If('{[M559]}'&lt;&gt;'')} and {[M559]}{End If}</td>
  </tr><tr>
  <td width="20%" valign="top"><b>Mailing Address:</b></td>
  <td>{Compress({[M561]}|{[M562]}|{[M563]}{[M564]}{[M565]}{[M566]})}</td>
  </tr><tr>
  <td width="20%"><b>Mortgage Loan No:</b></td>
  <td>{[M594]}</td>
  </tr><tr>
  <td width="20%"><b>Property Address:</b></td>
  <td>{Compress({[M567]}|{[M583]})}</td>
</tr></tbody></table></div>
<br>'''
        
        text = text[:insert_pos] + title_html + re_table_html + text[insert_pos:]
    
    return text

def fix_salutation_section(text):
    """Fix the salutation section to show only one clean salutation"""
    # Find the first Dear and remove all the multiple options
    dear_start = re.search(r'<div[^>]*>Dear', text)
    if dear_start:
        # Find where the salutation section ends
        end_patterns = [
            r'<div[^>]*>Notice is hereby given',
            r'<div[^>]*>To cure',
            r'<div[^>]*>You are required'
        ]
        
        end_pos = None
        for pattern in end_patterns:
            end_match = re.search(pattern, text)
            if end_match:
                end_pos = end_match.start()
                break
        
        if end_pos:
            # Replace all the Dear options with a clean salutation
            clean_salutation = '<div>Dear {[Salutation]},</div>\n<br>'
            text = text[:dear_start.start()] + clean_salutation + text[end_pos:]
    
    return text

def fix_payment_information(text):
    """Fix payment information to be in a proper table"""
    # Find the payment information section
    payment_start = re.search(r'<div[^>]*>Number of Payments Due:', text)
    if payment_start:
        # Find where this section ends
        end_patterns = [
            r'<div[^>]*>If you do not cure',
            r'<div[^>]*>You should realize',
            r'<div[^>]*>Please consider'
        ]
        
        end_pos = None
        for pattern in end_patterns:
            end_match = re.search(pattern, text)
            if end_match:
                end_pos = end_match.start()
                break
        
        if end_pos:
            # Create clean payment table
            payment_table = '''<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="50%">Number of Payments Due:</td>
  <td>{[M590]}</td>
  </tr><tr>
  <td width="50%">Net Payment Amount:</td>
  <td>{Money}</td>
  </tr><tr>
  <td width="50%">Unpaid Late Charges:</td>
  <td>{Money}</td>
  </tr><tr>
  <td width="50%">NSF & Other Fees:</td>
  <td>{Money} + {Money}</td>
  </tr><tr>
  <td width="50%">Unapplied/Suspense Funds:</td>
  <td>{Money}</td>
</tr></tbody></table></div>
<br>'''
            
            text = text[:payment_start.start()] + payment_table + text[end_pos:]
    
    return text

def add_pls_matrix_prefixes(text):
    """Add plsMatrix. prefixes to specific fields"""
    # Fields that need plsMatrix prefix
    pls_matrix_fields = [
        'CSPhoneNumber', 'SPOCContactEmail', 'PayoffAddr1', 'PayoffAddr2',
        'CompanyShortName', 'CompanyLongName', 'CashMgmtDept', 'LossMitHrs',
        'LoanCounselingPh', 'SeeReverse'
    ]
    
    for field in pls_matrix_fields:
        text = re.sub(r'\{\[' + field + r'\]\}', r'{[plsMatrix.' + field + ']}', text)
    
    return text

def fix_field_names(text):
    """Convert field names to standard format"""
    # Fix broken field names like {[M558]} that got split into {[M558]}
    text = re.sub(r'\{<b>([A-Z]\d+[A-Z]?E?\d*)\}</b>', r'{[\1]}', text)
    text = re.sub(r'\{<b>([A-Z]\d+[A-Z]?)\}</b>', r'{[\1]}', text)
    
    # Fix field names that got split across tags
    text = re.sub(r'\{<b>([A-Z]\d+[A-Z]?E?\d*)</b><b>\}', r'{[\1]}', text)
    
    # Fix specific broken patterns we see in the output
    text = re.sub(r'<b>\{</b><b>\[M558\]\}</b>', '{[M558]}', text)
    
    # Convert specific header fields to the correct format
    text = re.sub(r'\{\[H002\]\}', '{Insert(H003 TagHeader)}', text)
    text = re.sub(r'\{\[H003\]\}', '{Insert(H003 TagHeader)}', text)
    text = re.sub(r'\{\[H004\]\}', '{Insert(H003 TagHeader)}', text)
    text = re.sub(r'\{\[L001E8\]\}', '{[L001]}', text)
    text = re.sub(r'<b>\{</b><b>\[M559\]\}</b>', '{[M559]}', text)
    text = re.sub(r'<b>\{</b><b>\[M594\]\}</b>', '{[M594]}', text)
    text = re.sub(r'<b>\{</b><b>\[M561\]\}</b>', '{[M561]}', text)
    text = re.sub(r'<b>\{</b><b>\[M562\]\}</b>', '{[M562]}', text)
    text = re.sub(r'<b>\{</b><b>\[M563\]\}</b>', '{[M563]}', text)
    text = re.sub(r'<b>\{</b><b>\[M564\]\}</b>', '{[M564]}', text)
    text = re.sub(r'<b>\{</b><b>\[M565\]\}</b>', '{[M565]}', text)
    text = re.sub(r'<b>\{</b><b>\[M566\]\}</b>', '{[M566]}', text)
    text = re.sub(r'<b>\{</b><b>\[M567\]\}</b>', '{[M567]}', text)
    text = re.sub(r'<b>\{</b><b>\[M583\]\}</b>', '{[M583]}', text)
    text = re.sub(r'<b>\{</b><b>\[M568\]\}</b>', '{[M568]}', text)
    
    # Convert various field formats to standard {[field]} format
    text = re.sub(r'\{Insert\(([^}]+)\)\}', r'{[tagHeader]}', text)
    text = re.sub(r'\{([A-Z0-9]+)\}', r'{\[\1\]}', text)  # {FIELD} -> {[FIELD]}
    text = re.sub(r'\{([A-Z0-9]+E[0-9]+)\}', r'{\[\1\]}', text)  # {FIELDE1} -> {[FIELDE1]}
    
    # Clean up field names with descriptive text in parentheses - simpler approach
    # Use a more direct pattern that should work reliably
    
    # Pattern for {[fieldname]}(description) - no space before parentheses
    text = re.sub(r'\{\[([A-Za-z0-9]+)\}\]\([^)]*\)', r'{[\1]}', text)
    
    # Pattern for {[fieldname]} (description) - with space before parentheses  
    text = re.sub(r'\{\[([A-Za-z0-9]+)\}\]\s+\([^)]*\)', r'{[\1]}', text)
    
    # Debug output to see if function is working
    if 'tagHeader' in text:
        # Test if the regex patterns are actually working
        test_pattern = r'\{\[([A-Za-z0-9]+)\}\]\([^)]*\)'
        test_result = re.search(test_pattern, text)
        if test_result:
            text = '<div style="color: green;">✓ Field names function found patterns: ' + test_result.group(0) + '</div>' + text
        else:
            text = '<div style="color: orange;">⚠ Field names function running but no patterns found</div>' + text
    
    return text

def create_clean_header_structure(text):
    """Create clean header structure following universal pattern"""
    # Universal header pattern from analysis
    header_html = '''<div>{Insert(H003 TagHeader)}</div>
<br>
<div>{[L001]}</div>
<br>
<div>{[mailingAddress]}</div>
<br><br><br><br><br>'''
    
    # Find the start of the messy header and replace everything until "Notice of Intention"
    # Look for the first occurrence of any header field
    header_patterns = [
        r'<div[^>]*>\{\[tagHeader\]\}[^<]*</div>',
        r'<div[^>]*>\{[H0-9]+\}[^<]*</div>',
        r'<div[^>]*>\{[L0-9]+\}[^<]*</div>'
    ]
    
    start_pos = None
    for pattern in header_patterns:
        match = re.search(pattern, text)
        if match:
            start_pos = match.start()
            break
    
    if start_pos is not None:
        # Find where the header section ends (before "Notice of Intention")
        notice_start = re.search(r'<div[^>]*>Notice of Intention', text)
        if notice_start:
            # Replace the entire messy header section
            end_pos = notice_start.start()
            text = text[:start_pos] + header_html + text[end_pos:]
        else:
            # If no "Notice of Intention" found, look for other document title patterns
            title_patterns = [
                r'<div[^>]*>Notice of Default',
                r'<div[^>]*>Dear',
                r'<div[^>]*>To cure',
                r'<div[^>]*>You are required'
            ]
            for pattern in title_patterns:
                match = re.search(pattern, text)
                if match:
                    end_pos = match.start()
                    text = text[:start_pos] + header_html + text[end_pos:]
                    break
    
    return text

def create_proper_header(text):
    """Create proper header structure with company info and date"""
    # Create header section
    header_html = '''<div>{[tagHeader]}</div>
<br>
<div style="text-align: right">{[L001E8]}</div>
<br>
<div>{[mailingAddress]}</div>
<br>
<br>
<br>
<br>
<br>'''
    
    # Look for the header pattern - find where the current header starts
    header_start = text.find('{[tagHeader]}')
    if header_start != -1:
        # Find where the header section ends (before "Notice of Intention")
        notice_start = text.find('Notice of Intention to Foreclose Mortgage')
        if notice_start != -1:
            # Replace the messy header section with proper structure
            text = text[:header_start] + header_html + text[notice_start:]
    
    return text

def create_universal_re_table(text):
    """Create universal RE table structure based on analysis"""
    # Universal RE table pattern from BR008 analysis
    re_table_html = '''<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="20%"><b>Borrower Name:</b></td>
  <td>{[M558]}{If('{[M559]}'&lt;&gt;'')} and {[M559]}{End If}</td>
  </tr><tr>
  <td width="20%" valign="top"><b>Mailing Address:</b></td>
  <td>{Compress({[M561]}|{[M562]}|{[M563]}{[M564]}{[M565]}{[M566]})}</td>
  </tr><tr>
  <td width="20%"><b>Mortgage Loan No:</b></td>
  <td>{[M594]}</td>
  </tr><tr>
  <td width="20%"><b>Property Address:</b></td>
  <td>{Compress({[M567]}|{[M583]})}</td>
</tr></tbody></table></div>'''
    
    # Find the document title and insert RE table after it
    title_patterns = [
        r'<div[^>]*>Notice of Intention to Foreclose Mortgage[^<]*</div>',
        r'<div[^>]*>Notice of Default[^<]*</div>',
        r'<div[^>]*>Notice of Breach[^<]*</div>'
    ]
    
    title_match = None
    for pattern in title_patterns:
        title_match = re.search(pattern, text)
        if title_match:
            break
    
    if title_match:
        # Insert RE table right after the title
        insert_pos = title_match.end()
        text = text[:insert_pos] + '<br>' + re_table_html + '<br>' + text[insert_pos:]
        
        # Now remove the scattered borrower info that appears later
        borrower_patterns = [
            r'<div><b>Borrower Name:',
            r'<div>Borrower Name:',
            r'<div><b>Mortgage Loan No:',
            r'<div>Mortgage Loan No:',
            r'<div><b>Property Address:',
            r'<div>Property Address:'
        ]
        
        borrower_start = None
        for pattern in borrower_patterns:
            borrower_start = re.search(pattern, text)
            if borrower_start:
                break
        
        if borrower_start:
            # Find where this section ends (before "Dear" or main content)
            dear_patterns = [
                r'<div>Dear \{[Salutation]\}',
                r'<div>Dear \{',
                r'<div>Notice is hereby given',
                r'<div>To cure',
                r'<div>You are required'
            ]
            
            dear_start = None
            for pattern in dear_patterns:
                dear_start = re.search(pattern, text)
                if dear_start:
                    break
            
            if dear_start:
                # Remove the scattered borrower info
                start_pos = borrower_start.start()
                end_pos = dear_start.start()
                text = text[:start_pos] + text[end_pos:]
    
    return text

def create_re_table_structure(text):
    """Create RE table structure"""
    # Create RE table
    re_table_html = '''<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="20%">RE: Loan No:</td>
  <td>{[M594]}</td>
  </tr><tr>
  <td width="20%" valign="top">Property Address:</td>
  <td>{Compress({[M567]}|{[M583]}|{[M568]})}</td>
</tr></tbody></table></div>'''
    
    # Find where to insert the RE table - after the document title
    title_end = text.find('Notice of Intention to Foreclose Mortgage</b></div>')
    if title_end != -1:
        # Insert RE table after the title
        insert_point = title_end + len('Notice of Intention to Foreclose Mortgage</b></div>')
        text = text[:insert_point] + '<br>' + re_table_html + '<br>' + text[insert_point:]
    
    return text

def format_document_title_universal(text):
    """Format document title following universal pattern"""
    # Universal title pattern: centered and bold
    title_patterns = [
        r'Notice of Intention to Foreclose Mortgage',
        r'Notice of Default and Right to Cure',
        r'Notice of Default and Cure Letter',
        r'Notice of Breach'
    ]
    
    # Check if any title already exists
    title_exists = False
    for pattern in title_patterns:
        if re.search(pattern, text):
            title_exists = True
            break
    
    # If no title exists, add one based on document content
    if not title_exists:
        # Look for foreclosure-related content to determine title
        if re.search(r'foreclose|foreclosure', text, re.IGNORECASE):
            title_html = '<div style="text-align: center"><b>Notice of Intention to Foreclose Mortgage</b></div>'
        elif re.search(r'default.*cure|cure.*default', text, re.IGNORECASE):
            title_html = '<div style="text-align: center"><b>Notice of Default and Right to Cure</b></div>'
        else:
            title_html = '<div style="text-align: center"><b>Notice of Default</b></div>'
        
        # Insert title after the RE table or at the beginning of main content
        re_table_end = re.search(r'</tbody></table></div>', text)
        if re_table_end:
            insert_pos = re_table_end.end()
            text = text[:insert_pos] + '<br>' + title_html + '<br>' + text[insert_pos:]
        else:
            # Insert at the beginning of main content
            main_content_start = re.search(r'<div[^>]*>Dear', text)
            if main_content_start:
                insert_pos = main_content_start.start()
                text = text[:insert_pos] + title_html + '<br>' + text[insert_pos:]
    
    # Format existing titles
    for pattern in title_patterns:
        # Find and replace with universal centered format
        escaped_pattern = re.escape(pattern)
        text = re.sub(rf'<div[^>]*>{escaped_pattern}[^<]*</div>',
                     f'<div style="text-align: center"><b>{pattern}</b></div>', text)
    
    return text

def format_document_title(text):
    """Format the main document title"""
    # Fix the title that's currently embedded in the header div
    text = re.sub(r'Notice of Intention to Foreclose Mortgage</b></div>', 
                  'Notice of Intention to Foreclose Mortgage</b></div>', text)
    
    # Also handle the case where it's in a regular div
    text = re.sub(r'<div[^>]*>Notice of Intention to Foreclose Mortgage</div>', 
                  '<div style="text-align: center"><b>Notice of Intention to Foreclose Mortgage</b></div>', text)
    
    return text

def create_borrower_table(text):
    """Create borrower information table"""
    # This would create a table for borrower info if needed
    return text

def format_salutation_universal(text):
    """Format salutation following universal pattern"""
    # Find the first "Dear" and replace all multiple options with clean salutation
    dear_patterns = [
        r'<div[^>]*>Dear',
        r'<div>Dear',
        r'Dear'
    ]
    
    dear_start = None
    for pattern in dear_patterns:
        dear_start = re.search(pattern, text)
        if dear_start:
            break
    
    if dear_start:
        # Find where all the Dear options end (before main content)
        end_patterns = [
            r'<div[^>]*>Notice is hereby given',
            r'<div[^>]*>To cure',
            r'<div[^>]*>You are required',
            r'<div[^>]*>This notice',
            r'<div[^>]*>We are writing'
        ]
        
        end_pos = None
        for pattern in end_patterns:
            end_match = re.search(pattern, text)
            if end_match:
                end_pos = end_match.start()
                break
        
        if end_pos:
            # Replace all the Dear options with a clean salutation
            salutation_html = '<div>Dear {[Salutation]},</div>'
            text = text[:dear_start.start()] + salutation_html + text[end_pos:]
    
    # Also clean up any remaining broken Dear patterns
    text = re.sub(r'<div[^>]*>Dear[^<]*</div>\s*<br>\s*<div[^>]*></div>\s*<br>\s*', '', text)
    
    return text

def format_salutation(text):
    """Format the salutation section"""
    # Find the first "Dear" and replace all the multiple options with a clean salutation
    dear_start = text.find('Dear {[M558]}')
    if dear_start != -1:
        # Find where all the Dear options end (before "Notice is hereby")
        notice_start = text.find('Notice is hereby given')
        if notice_start != -1:
            # Replace all the Dear options with a clean salutation
            salutation_html = '<div>Dear {[Salutation]},</div>'
            text = text[:dear_start] + salutation_html + text[notice_start:]
    
    # Also handle cases where Dear appears multiple times in sequence
    # Remove all the duplicate Dear lines
    text = re.sub(r'<div[^>]*>Dear[^<]*</div>\s*<br>\s*<div[^>]*></div>\s*<br>\s*', '', text)
    
    return text

def wrap_money_fields(text):
    """Wrap money fields in Money() and Math() functions"""
    # Wrap individual money fields with E6 suffix (with or without descriptive text)
    text = re.sub(r'\$\{\[([A-Z0-9]+E6)\]\}\s*\([^)]*\)', r'{Money({\[\1\]})}', text)
    text = re.sub(r'\$\{\[([A-Z0-9]+E6)\]\}\([^)]*\)', r'{Money({\[\1\]})}', text)
    text = re.sub(r'\$\{\[([A-Z0-9]+E6)\]\}', r'{Money({\[\1\]})}', text)
    
    # Wrap E6 fields without $ signs but with descriptive text
    text = re.sub(r'\{\[([A-Z0-9]+E6)\]\}\s*\([^)]*\)', r'{Money({\[\1\]})}', text)
    text = re.sub(r'\{\[([A-Z0-9]+E6)\]\}\([^)]*\)', r'{Money({\[\1\]})}', text)
    
    # Wrap regular fields that appear to be money (with $ signs and descriptive text)
    text = re.sub(r'\$\{\[([A-Z0-9]+)\]\}\s*\([^)]*\)', r'{Money({\[\1\]})}', text)
    text = re.sub(r'\$\{\[([A-Z0-9]+)\]\}\([^)]*\)', r'{Money({\[\1\]})}', text)
    
    # Debug output
    if 'E6' in text:
        text = '<div style="color: blue;">✓ Money function is running</div>' + text
    
    return text

def create_payment_info_tables(text):
    """Create payment information tables"""
    # Create payment breakdown table
    payment_table_html = '''<div><table width="100%" style="border-collapse: collapse"><tbody><tr>
  <td width="50%">Number of Payments Due:</td>
  <td>{[M590]}</td>
  </tr><tr>
  <td width="50%">Net Payment Amount:</td>
  <td>{Money({[M591E6]})}</td>
  </tr><tr>
  <td width="50%">Unpaid Late Charges:</td>
  <td>{Money({[M015E6]})}</td>
  </tr><tr>
  <td width="50%">NSF & Other Fees:</td>
  <td>{Money({[M593E6]})} + {Money({[C004E6]})}</td>
  </tr><tr>
  <td width="50%">Unapplied/Suspense Funds:</td>
  <td>{Money({[M013E6]})}</td>
</tr></tbody></table></div>'''
    
    # Find the payment info section - look for the table that's embedded in text
    table_start = text.find('<div><table width="100%" style="border-collapse: collapse"><tbody><tr>')
    if table_start != -1:
        # Find where this embedded table ends
        table_end = text.find('</table></div>', table_start) + len('</table></div>')
        if table_end != -1:
            # Replace the embedded table with proper formatting
            text = text[:table_start] + payment_table_html + text[table_end:]
    
    # Also handle the case where payment info is in regular text
    payment_start = text.find('Number of Payments Due:')
    if payment_start != -1 and table_start == -1:
        # Find where this section ends (before "If you do not cure")
        cure_start = text.find('If you do not cure the default')
        if cure_start != -1:
            # Replace the payment info section with table
            text = text[:payment_start] + payment_table_html + text[cure_start:]
    
    return text

def clean_excessive_formatting(text):
    """Remove excessive formatting that doesn't match universal patterns"""
    # Remove repeated style attributes (like "text-align: justify; text-align: justify")
    text = re.sub(r'text-align: justify; text-align: justify', 'text-align: justify', text)
    text = re.sub(r'(text-align: justify; )+', 'text-align: justify; ', text)
    text = re.sub(r'(font-size: [^;]+; )+', lambda m: m.group(0).split('; ')[0] + '; ', text)
    
    # Remove excessive style attributes from every div
    text = re.sub(r'<div style="text-align: justify"><b>', '<div>', text)
    text = re.sub(r'<div style="text-align: justify">', '<div>', text)
    
    # Remove excessive <b> tags that wrap every line
    text = re.sub(r'<b>(\{[^}]+\})</b>', r'\1', text)
    
    # Clean up broken HTML tags
    text = re.sub(r'</b><b>', '', text)  # Remove broken </b><b> sequences
    text = re.sub(r'<b></b>', '', text)  # Remove empty bold tags
    text = re.sub(r'<b>\s*</b>', '', text)  # Remove bold tags with only whitespace
    
    # Fix orphaned </b> tags without opening <b>
    text = re.sub(r'(\{[^}]+\})\s*</b>', r'\1', text)  # Remove </b> after field names
    text = re.sub(r'([^<])\s*</b>', r'\1', text)  # Remove orphaned </b> tags
    
    # Fix broken <b></div> patterns
    text = re.sub(r'<b></div>', '</div>', text)
    
    # Fix missing closing </b> tags
    text = re.sub(r'<b>([^<]+)</div>', r'<b>\1</b></div>', text)
    
    # Clean up malformed field names
    text = re.sub(r'\{</b><b>([^}]+)</b><b>\}', r'{\[\1\]}', text)  # Fix broken field names
    
    # Clean up empty divs
    text = re.sub(r'<div><b></b></div>', '', text)
    text = re.sub(r'<div style="text-align: justify"></div>', '', text)
    text = re.sub(r'<div></div>', '', text)
    
    # Remove duplicate payment information that appears after the table
    duplicate_pattern = r'<div><u><b>Number of Payments Due:</b></u><u><b> </b></u><b>{[M590]}</b><b> </b></div>.*?<div><u><b>Unapplied/Suspense Funds: </b></u><b>\$</b><b>\{Money\} </b></div>'
    text = re.sub(duplicate_pattern, '', text, flags=re.DOTALL)
    
    return text

def clean_and_format_html(text):
    """Clean up and add proper spacing"""
    # Remove duplicate payment information that appears after the table
    # Look for the pattern where payment info is repeated as individual lines
    duplicate_pattern = r'<div><u><b>Number of Payments Due:</b></u><u><b> </b></u><b>{[M590]}</b><b> </b></div>.*?<div><u><b>Unapplied/Suspense Funds: </b></u><b>\$</b><b>\{Money\} </b></div>'
    text = re.sub(duplicate_pattern, '', text, flags=re.DOTALL)
    
    # Add <br> between divs for proper spacing
    text = re.sub(r'</div>\s*<div>', '</div>\n<br>\n<div>', text)
    
    # Clean up multiple line breaks
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove excessive whitespace and comments
    text = re.sub(r'\([^)]*\)\s*', '', text)  # Remove comments in parentheses
    text = re.sub(r'\s+', ' ', text)  # Collapse multiple spaces
    text = re.sub(r' \n', '\n', text)  # Remove spaces before newlines
    
    return text
