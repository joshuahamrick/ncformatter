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
    """Generate the final formatted HTML"""
    
    html_parts = []
    
    # Process each paragraph
    for para in paragraphs:
        if not para['text'].strip():
            continue
            
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
