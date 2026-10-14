"""Verify tutorial assets, embedded fonts, links, copies and section coverage."""
from pathlib import Path
import sys, json, re, hashlib
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build/tutorial-deps'))
import pymupdf as fitz
from PIL import Image, ImageDraw

BASE = ROOT / 'docs/tutorials'
manifest = json.loads((BASE / 'sources/pdf_manifest.json').read_text(encoding='utf8'))
checks = []; steps = []
for document in manifest:
    path = ROOT / document['path']
    assert path.read_bytes() == (ROOT / document['distribution_copy']).read_bytes()
    pdf = fitz.open(path)
    assert pdf.embfile_count() == 1
    for page in pdf:
        used_fonts = {span['font'] for block in page.get_text('dict')['blocks']
                      if block['type'] == 0 for line in block['lines'] for span in line['spans']}
        for font in page.get_fonts():
            if font[3].split('+')[-1] in used_fonts:
                assert pdf.extract_font(font[0])[3], 'Unembedded font'
        for link in page.get_links():
            if 'page' in link and link['page'] >= 0:
                assert link['page'] < len(pdf)
            if 'uri' in link and link['uri'].startswith('PhaseStudio_'):
                assert (BASE / link['uri']).is_file()
    text = '\n'.join(page.get_text() for page in pdf)
    assert 'Jana2020' in text and 'SharpED' in text
    assert '\ufffd' not in text
    source = BASE / document['source']
    for match in re.finditer(r'<!-- PAGE (.*?) -->', source.read_text(encoding='utf8')):
        meta = json.loads(match.group(1))
        image = meta.get('image')
        if image:
            assert (BASE / image).is_file()
            Image.open(BASE / image).verify()
        steps.append(dict(document=document['filename'], section=meta['title'],
                          image=image, captured=bool(image), keys=meta.get('keys', []),
                          state=meta.get('caption', 'See source/asset provenance inventories')))
    output = ROOT / 'build/tutorials/final-contact-sheets'
    output.mkdir(parents=True, exist_ok=True)
    renders = ROOT / 'build/tutorials/pdf-qa' / path.stem
    for start in range(0, len(pdf), 12):
        sheet = Image.new('RGB', (1260, 1840), '#cfd8e3'); draw = ImageDraw.Draw(sheet)
        for offset in range(min(12, len(pdf)-start)):
            image = Image.open(renders / f'page-{start+offset+1:03d}.png')
            image.thumbnail((390, 425)); x=15+(offset%3)*420; y=20+(offset//3)*460
            sheet.paste(image, (x, y+20)); draw.text((x,y), str(start+offset+1), fill='black')
        sheet.save(output / f'{path.stem}-{start//12+1:02d}.jpg')
    checks.append(dict(filename=path.name, pages=len(pdf), fonts='embedded',
                       local_links='resolved', distribution_copy='identical',
                       assets='present/readable', font_licence='attached'))
fields = json.loads((BASE/'sources/control_inventory.json').read_text(encoding='utf8'))
documented = {key for step in steps for key in step['keys']}
assert {field['key'] for field in fields} <= documented
for file in (BASE/'sources').glob('*.json'):
    assert not re.search(r'honzi|ochlor|VznB7|2int3total', file.read_text(encoding='utf8'), re.I), file
(BASE/'sources/step_screenshot_inventory.json').write_text(json.dumps(steps,indent=2),encoding='utf8')
(BASE/'sources/validation.json').write_text(json.dumps(dict(checks=checks,
    documented_controls=len(documented), pages_rendered=sum(item['pages'] for item in checks)),indent=2),encoding='utf8')
print(json.dumps(checks))
