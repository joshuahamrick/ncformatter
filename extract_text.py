import sys
import io
from docx import Document

def extract_text(docx_path):
    doc = Document(docx_path)
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text)
    return '\n'.join(paragraphs)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python extract_text.py <docx_path>")
        sys.exit(1)
    
    docx_path = sys.argv[1]
    try:
        text = extract_text(docx_path)
        # Use UTF-8 encoding for output
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        print(text)
    except Exception as e:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

