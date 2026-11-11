import zipfile, xml.etree.ElementTree as ET
p = 'Aqua_pH.docx'
z = zipfile.ZipFile(p)
root = ET.fromstring(z.read('word/document.xml'))
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
texts = []
for pnode in root.findall('.//w:p', ns):
    parts = []
    for t in pnode.findall('.//w:t', ns):
        parts.append(t.text or '')
    txt = ''.join(parts)
    if txt.strip():
        texts.append(txt.strip())
open('doc_text.txt', 'w', encoding='utf-8').write('\n'.join(texts))
print('wrote', len(texts), 'paragraphs')
print('\n'.join(texts[:200]))
