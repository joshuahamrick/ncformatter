const fs = require('fs');
const path = require('path');

const docxPath = process.argv[2];
if (!docxPath) {
    console.error('Usage: node get-text.js <docx-path>');
    process.exit(1);
}

// Try to use the existing API endpoint
const buf = fs.readFileSync(docxPath);
const base64 = buf.toString('base64');

fetch('https://ncformatter.vercel.app/api/process-doc.py', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        fileData: base64,
        fileName: path.basename(docxPath)
    })
})
.then(res => res.json())
.then(json => {
    if (json.success && json.ir && json.ir.blocks) {
        json.ir.blocks.forEach((block, idx) => {
            if (block.type === 'paragraph') {
                const text = (block.runs || []).map(r => r.text || '').join('');
                if (text.trim()) {
                    console.log(text);
                }
            } else if (block.type === 'table') {
                console.log('\n[TABLE]');
                if (block.rows) {
                    block.rows.forEach(row => {
                        if (row.cells) {
                            const rowText = row.cells.map(cell => {
                                if (cell.content && cell.content[0]) {
                                    return (cell.content[0].runs || []).map(r => r.text || '').join('');
                                }
                                return '';
                            }).filter(t => t).join(' | ');
                            if (rowText) console.log(rowText);
                        }
                    });
                }
            }
        });
    } else {
        console.error('Error:', json.error || 'Unknown error');
    }
})
.catch(err => {
    console.error('Fetch error:', err.message);
    process.exit(1);
});


