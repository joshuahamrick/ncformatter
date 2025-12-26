const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const docxPath = process.argv[2];
if (!docxPath) {
    console.error('Usage: node extract-docx.js <docx-path>');
    process.exit(1);
}

// docx files are zip archives - extract document.xml
const tempDir = path.join(__dirname, 'temp-extract');
if (!fs.existsSync(tempDir)) {
    fs.mkdirSync(tempDir);
}

try {
    // Use PowerShell to extract the zip and read document.xml
    const psScript = `
        $zipPath = '${docxPath.replace(/\\/g, '/')}'
        $tempDir = '${tempDir.replace(/\\/g, '/')}'
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $tempDir)
        $xmlPath = Join-Path $tempDir 'word\\document.xml'
        if (Test-Path $xmlPath) {
            Get-Content $xmlPath -Raw
        }
    `;
    
    const xmlContent = execSync(`powershell -Command "${psScript}"`, { encoding: 'utf8' });
    
    // Simple regex to extract text from XML (basic approach)
    const textMatches = xmlContent.match(/<w:t[^>]*>([^<]*)<\/w:t>/g);
    if (textMatches) {
        const texts = textMatches.map(m => {
            const match = m.match(/<w:t[^>]*>([^<]*)<\/w:t>/);
            return match ? match[1] : '';
        }).filter(t => t.trim());
        console.log(texts.join('\n'));
    }
    
    // Cleanup
    if (fs.existsSync(tempDir)) {
        fs.rmSync(tempDir, { recursive: true, force: true });
    }
} catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
}


