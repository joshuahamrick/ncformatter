import re

with open(r'formatter examples/SI002/SI002-formatted.html', 'r', encoding='utf-8') as f:
    orig = f.read()
with open(r'formatter examples/SI002-Triad/SI002-Triad-formatted.html', 'r', encoding='utf-8') as f:
    triad = f.read()

def get_text(html):
    text = re.sub(r'<[^>]+>', ' ', html)
    return re.sub(r'\s+', ' ', text).strip()

ot = get_text(orig)
tt = get_text(triad)

phrases = [
    'Personal Representative', 'Documents evidencing', 'Judgement of Possession',
    'Transfer on Death Deed', 'Death Certificate', 'Deed of Distribution',
    'Customer Service', 'Affidavit of Surviving', 'Joint Tenant',
]

ok = True
for p in phrases:
    oc = ot.count(p)
    tc = tt.count(p)
    flag = 'OK' if tc >= oc else 'LOST'
    if tc < oc:
        ok = False
    print(f'  {p}: orig={oc} triad={tc} {flag}')

print(f'\nIf count: {triad.count("{If(")}')
print(f'End If count: {triad.count("{End If}")}')
b = chr(8226)
print(f'Bullet cells: orig={orig.count(b)} triad={triad.count(b)}')
print(f'\nAll text preserved: {ok}')
