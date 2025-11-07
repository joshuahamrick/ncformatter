const s = 'TOTAL YOU MUST PAY TO CURE DEFAULT: ${[C001E6]} + {[M585E6]} – {[M013E6]} (something)';
const step1 = s.replace(/\{\[([A-Za-z0-9]+)E[0-9]+\]\}/g, '{[$1]}');
console.log('step1:', step1);
const step2 = step1.replace(/\$\s*\{\[([A-Za-z0-9]+)\]\}\s*\+\s*\{\[([A-Za-z0-9]+)\]\}\s*[–-]\s*\{\[([A-Za-z0-9]+)\]\}/g, '{Math({[$1]} + {[$2]} - {[$3]}|Money)}');
console.log('step2:', step2);

