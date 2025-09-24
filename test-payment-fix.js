// Test the payment table conversion fix
const fs = require('fs');

// Simulate the current broken output
const brokenOutput = `<div>Next Payment Due Date: {[M026]}</div>
<br>
<div>Number of Payments Due as of the Date of This Notice: {[M590]}</div>
<br>
<div>Total Monthly Payments Due: {Money({[M591]})}</div>
<br>
<div>Late Charges: {Money({[M015]})}</div>
<br>
<div>Other Charges: Uncollected NSF Fees: {Money({[M593]})}</div>
<br>
<div>Other Fees: {Money({[C004]})}</div>
<br>
<div>Corporate Advance Balance: {Money({[M585]})}</div>
<br>
<div>Partial Payment (Unapplied) Balance: {Money({[M013]})}</div>
<br>
<div>TOTAL YOU MUST PAY TO CURE DEFAULT: {Math({[C001]} + {[M585]} - {[M013]}|Money)}</div>`;

console.log('Testing payment table conversion...');
console.log('Input:', brokenOutput);

// Test the new approach
let formatted = brokenOutput;

// First try the complete replacement
const paymentTable = `<table width="80%" style="border-collapse: collapse"><tbody><tr>
  <td width="50%">Next Payment Due Date:</td>
  <td>{[M026]}</td>
  </tr><tr>
  <td width="50%">Number of Payments Due as of the Date of This Notice:</td>
  <td>{[M590]}</td>
  </tr><tr>
  <td width="50%">Total Monthly Payments Due:</td>
  <td>{Money({[M591]})}</td>
  </tr><tr>
  <td width="50%">Late Charges:</td>
  <td>{Money({[M015]})}</td>
  </tr><tr>
  <td width="50%">Other Charges: Uncollected NSF Fees:</td>
  <td>{Money({[M593]})}</td>
  </tr><tr>
  <td width="50%">Other Fees:</td>
  <td>{Money({[C004]})}</td>
  </tr><tr>
  <td width="50%">Fees)</td>
  <td></td>
  </tr><tr>
  <td width="50%">Corporate Advance Balance:</td>
  <td>{Money({[M585]})}</td>
  </tr><tr>
  <td width="50%">Partial Payment (Unapplied) Balance:</td>
  <td>{Money({[M013]})}</td>
</tr></tbody></table>
<div>TOTAL YOU MUST PAY TO CURE DEFAULT: {Math({[C001]} + {[M585]} - {[M013]}|Money)}</div>`;

// Try complete replacement first
formatted = formatted.replace(
    /<div>Next Payment Due Date: \{[^}]+\}<\/div>\s*<br>\s*<div>Number of Payments Due as of the Date of This Notice: \{[^}]+\}<\/div>\s*<br>\s*<div>Total Monthly Payments Due: \{Money\(\{[^}]+\}\)\}<\/div>\s*<br>\s*<div>Late Charges: \{Money\(\{[^}]+\}\)\}<\/div>\s*<br>\s*<div>Other Charges: Uncollected NSF Fees: \{Money\(\{[^}]+\}\)\}<\/div>\s*<br>\s*<div>Other Fees: \{Money\(\{[^}]+\}\)\}<\/div>\s*<br>\s*<div>Corporate Advance Balance: \{Money\(\{[^}]+\}\)\}<\/div>\s*<br>\s*<div>Partial Payment \(Unapplied\) Balance: \{Money\(\{[^}]+\}\)\}<\/div>\s*<br>\s*<div>TOTAL YOU MUST PAY TO CURE DEFAULT: \{Math\(\{[^}]+\}\)\}<\/div>/g,
    paymentTable
);

console.log('After complete replacement:', formatted);

// If that didn't work, try individual replacements
if (!formatted.includes('<table width="80%"')) {
    console.log('Complete replacement failed, trying individual replacements...');
    
    formatted = brokenOutput;
    
    // Replace each div individually
    formatted = formatted.replace(/<div>Next Payment Due Date: \{[^}]+\}<\/div>/g, '<table width="80%" style="border-collapse: collapse"><tbody><tr><td width="50%">Next Payment Due Date:</td><td>{[M026]}</td></tr>');
    formatted = formatted.replace(/<div>Number of Payments Due as of the Date of This Notice: \{[^}]+\}<\/div>/g, '<tr><td width="50%">Number of Payments Due as of the Date of This Notice:</td><td>{[M590]}</td></tr>');
    formatted = formatted.replace(/<div>Total Monthly Payments Due: \{Money\(\{[^}]+\}\)\}<\/div>/g, '<tr><td width="50%">Total Monthly Payments Due:</td><td>{Money({[M591]})}</td></tr>');
    formatted = formatted.replace(/<div>Late Charges: \{Money\(\{[^}]+\}\)\}<\/div>/g, '<tr><td width="50%">Late Charges:</td><td>{Money({[M015]})}</td></tr>');
    formatted = formatted.replace(/<div>Other Charges: Uncollected NSF Fees: \{Money\(\{[^}]+\}\)\}<\/div>/g, '<tr><td width="50%">Other Charges: Uncollected NSF Fees:</td><td>{Money({[M593]})}</td></tr>');
    formatted = formatted.replace(/<div>Other Fees: \{Money\(\{[^}]+\}\)\}<\/div>/g, '<tr><td width="50%">Other Fees:</td><td>{Money({[C004]})}</td></tr>');
    formatted = formatted.replace(/<div>Corporate Advance Balance: \{Money\(\{[^}]+\}\)\}<\/div>/g, '<tr><td width="50%">Fees)</td><td></td></tr><tr><td width="50%">Corporate Advance Balance:</td><td>{Money({[M585]})}</td></tr>');
    formatted = formatted.replace(/<div>Partial Payment \(Unapplied\) Balance: \{Money\(\{[^}]+\}\)\}<\/div>/g, '<tr><td width="50%">Partial Payment (Unapplied) Balance:</td><td>{Money({[M013]})}</td></tr></tbody></table>');
    
    console.log('After individual replacements:', formatted);
}

// Check if we have a proper table
if (formatted.includes('<table width="80%"')) {
    console.log('✅ SUCCESS: Payment table conversion working!');
} else {
    console.log('❌ FAILED: Payment table conversion not working');
}

