from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
path = Path(r'C:\Users\cwakh\Downloads\TCAMS_Contract_Terms_and_Conditions.docx')
out = Path(r'cfa-dash\.pytest-tmp\tcams_terms.txt')
out.parent.mkdir(exist_ok=True)
with ZipFile(path) as zf:
    xml = zf.read('word/document.xml')
root = ET.fromstring(xml)
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
paragraphs = []
for para in root.findall('.//w:p', ns):
    parts = [node.text or '' for node in para.findall('.//w:t', ns)]
    text = ''.join(parts).strip()
    if text:
        paragraphs.append(text)
clean = '\n\n'.join(paragraphs)
out.write_text(clean, encoding='utf-8')
print(f'wrote {out} chars={len(clean)} paragraphs={len(paragraphs)}')
print(clean[:1200])
