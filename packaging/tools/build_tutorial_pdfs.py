"""Rebuild editable tutorial Markdown as annotated, searchable A4 PDFs.

Dependencies are isolated in build/tutorial-deps. No application code is changed.
All images are actual captures. Highlights/crops are PDF illustration overlays.
"""
from __future__ import annotations
from pathlib import Path
import sys,json,re,html,shutil,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"build/tutorial-deps"))
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from PIL import Image,ImageStat
import pymupdf as fitz
import matplotlib

BASE=ROOT/"docs/tutorials"
OUT=ROOT/"dist/documentation"
QA=ROOT/"build/tutorials/pdf-qa"
OUT.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
FONT=Path(matplotlib.get_data_path())/"fonts/ttf"
for name,file in [("Body","DejaVuSans.ttf"),("BodyBold","DejaVuSans-Bold.ttf"),("BodyItalic","DejaVuSans-Oblique.ttf")]:
    pdfmetrics.registerFont(TTFont(name,str(FONT/file)))
pdfmetrics.registerFontFamily("Body",normal="Body",bold="BodyBold",italic="BodyItalic",boldItalic="BodyBold")
NAVY=colors.HexColor("#001170");CYAN=colors.HexColor("#1fa5ff")
GREY=colors.HexColor("#52658b");PALE=colors.HexColor("#edf3fa")
styles={
    "body":ParagraphStyle("body",fontName="Body",fontSize=10.0,leading=14.1,textColor=NAVY,spaceAfter=9),
    "small":ParagraphStyle("small",fontName="Body",fontSize=8.4,leading=11.6,textColor=GREY),
    "heading":ParagraphStyle("heading",fontName="BodyBold",fontSize=19,leading=24,textColor=NAVY),
}
inventory=[]
for file in (BASE/"sources").glob("*screenshot_inventory.json"):
    inventory += json.loads(file.read_text(encoding="utf8"))
by_path={item.get("path"):item for item in inventory if item.get("path")}
control_images={item["key"]:item for item in inventory if "key" in item and item.get("captured")}
drawn_images={}

def md(text):
    text=html.escape(text)
    text=re.sub(r"\[([^\]]+)\]\(([^)]+)\)",lambda m:f'<link href="{m[2]}" color="#005cb7">{m[1]}</link>',text)
    text=re.sub(r"\*\*(.+?)\*\*",r"<b>\1</b>",text)
    text=re.sub(r"`([^`]+)`",r"<font color='#244b78'>\1</font>",text)
    # Preserve genuine sequential instructions as separate readable steps.
    if re.match(r"^\d+\.\s", text):
        return text.replace("\n", "<br/>")
    return text.replace("\n"," ")

def parse(source):
    text=source.read_text(encoding="utf8")
    title=re.search(r"^# (.+)$",text,re.M).group(1)
    subtitle=re.search(r"^## (.+)$",text,re.M).group(1)
    metadata=json.loads(re.search(r"<!-- DOCUMENT (.+?) -->",text).group(1))
    parts=re.split(r"<!-- PAGE (.+?) -->",text)
    pages=[]
    for i in range(1,len(parts),2):
        page=json.loads(parts[i]);page["text"]=parts[i+1].strip();pages.append(page)
    return title,subtitle,metadata,pages

def text_height(text,width,style):
    return Paragraph(md(text),style).wrap(width,10000)[1]

def paragraph(c,text,x,y,width,style="body"):
    p=Paragraph(md(text),styles[style]);w,h=p.wrap(width,10000)
    p.drawOn(c,x,y-h)
    return y-h-styles[style].spaceAfter

def crop_image(path,kind):
    im=Image.open(path).convert("RGB")
    # Crops retain a single genuine interface region; no screen assembly.
    boxes={
        "configuration":(0,0,.34,1),
        "wizard-summary":(0,0,1,.47),
        "wizard-workflows":(0,.41,1,1),
        "account-controls":(0,.35,1,1),
        "web-login":(.27,.095,.72,.69),
        "validation":(0,0,1,1),
        "powder-controls":(0,.25,1,.65),
        "github-assets":(.075,.71,.68,.81),
    }
    if kind:
        box=boxes[kind];w,h=im.size;im=im.crop(tuple(round(v*(w if i%2==0 else h)) for i,v in enumerate(box)))
    else:box=(0,0,1,1)
    return im,box

def figure(c,path,kind,x,y,width,max_height,meta,caption=None):
    path=BASE/path
    if not path.is_file():raise FileNotFoundError("Missing required screenshot: "+str(path.relative_to(BASE)))
    im,crop=crop_image(path,kind)
    if max(ImageStat.Stat(im).stddev)<2:raise ValueError("Blank screenshot: "+path.name)
    iw,ih=im.size
    factor=min(width/iw,max_height/ih)
    dw,dh=iw*factor,ih*factor
    left=x+(width-dw)/2;bottom=y-dh
    c.setStrokeColor(colors.HexColor("#ccd8e7"));c.setLineWidth(.5)
    c.drawImage(ImageReader(im),left,bottom,dw,dh)
    c.rect(left,bottom,dw,dh,stroke=1,fill=0)
    drawn_images[str(path.relative_to(BASE))]=True
    rec=by_path.get(str(path.relative_to(BASE)).replace("\\","/"),{})
    targets=rec.get("targets",[])
    # Actual widget bounds become subtle highlights and numbered markers.
    count=0
    highlighted=[]
    for target in targets:
        rx,ry,rw,rh=target["rect"]
        if rx<crop[0] or ry<crop[1] or rx+rw>crop[2] or ry+rh>crop[3]:continue
        xx=left+(rx-crop[0])/(crop[2]-crop[0])*dw
        yy=bottom+dh-(ry+rh-crop[1])/(crop[3]-crop[1])*dh
        ww=rw/(crop[2]-crop[0])*dw;hh=rh/(crop[3]-crop[1])*dh
        c.setStrokeColor(CYAN);c.setLineWidth(1);c.rect(xx-2,yy-2,ww+4,hh+4)
        count+=1
        highlighted.append(target)
        mx=max(left+8,xx-12);my=min(bottom+dh-8,yy+hh+10)
        c.setFillColor(NAVY);c.circle(mx,my,7,stroke=0,fill=1)
        c.setFillColor(colors.white);c.setFont("BodyBold",8);c.drawCentredString(mx,my-2.6,str(count))
        c.setStrokeColor(CYAN);c.line(mx+7,my,xx,yy+hh)
    if not count:
        # A clearly editorial step marker in the image margin, not a fake UI.
        marker_x=max(13,left-12);marker_y=bottom+dh/2
        c.setFillColor(NAVY);c.circle(marker_x,marker_y,7,stroke=0,fill=1)
        c.setFillColor(colors.white);c.setFont("BodyBold",8);c.drawCentredString(marker_x,marker_y-2.7,"1")
        c.setStrokeColor(CYAN);c.setLineWidth(.8);c.line(marker_x+7,marker_y,left,marker_y)
    if caption is None:
        fixture=rec.get("fixture","")
        caption="Actual Phase Studio 2.0.3 UI · " + ("Illustrative synthetic state; no live inference/Jana import." if "fixture" in fixture.lower() or "illustrative" in fixture.lower() else "Public synthetic demonstration data.")
        if "web" in str(path):caption="Actual authenticated SharpED controls; account details and token table excluded." if "sharped-token-controls" in str(path) else "Actual public web page; no login credentials entered."
    y=paragraph(c,caption,x,bottom-8,width,"small")
    if targets and count:
        descriptions=[f"{i+1}. {target['label']}" for i,target in enumerate(highlighted)]
        y=paragraph(c," · ".join(descriptions),x,y,width,"small")
    return y

def frame(c,title,page_no,page_count,size):
    w,h=size
    c.setFillColor(colors.white);c.rect(0,0,w,h,stroke=0,fill=1)
    c.setFillColor(NAVY);c.rect(0,h-7,w,7,stroke=0,fill=1)
    c.setFont("BodyBold",8);c.drawString(36,h-26,"PHASE STUDIO  /  2.0.3 SOURCE GUIDE")
    c.setFont("Body",7.8);c.setFillColor(GREY)
    c.drawRightString(w-36,h-26,"Review edition · 14 October 2026")
    c.setStrokeColor(colors.HexColor("#d7e1ee"));c.line(36,36,w-36,36)
    c.setFont("Body",7.6);c.drawString(36,22,title[:65]);c.drawRightString(w-36,22,f"{page_no} / {page_count}")

def document(source):
    title,subtitle,metadata,pages=parse(source)
    # Long guide TOC has links to every section/reference page.
    toc_pages=(len(pages)+23)//24 if "Complete" in metadata["filename"] else 1
    total=1+toc_pages+len(pages)
    path=BASE/metadata["filename"]
    c=canvas.Canvas(str(path),pagesize=A4,pageCompression=1)
    c.setTitle(title+" — "+subtitle);c.setAuthor("Jiří Zelenka · Institute of Physics of the Czech Academy of Sciences")
    c.setSubject("Illustrated development-source review tutorials; verified UI and explicit acceptance gaps")
    frame(c,title,1,total,A4)
    w,h=A4
    c.setFillColor(CYAN);c.rect(36,h-155,52,5,stroke=0,fill=1)
    paragraph(c,title,36,h-170,w-72,"heading")
    paragraph(c,subtitle,36,h-242,w-72)
    paragraph(c,"ILLUSTRATED STEP-BY-STEP TUTORIAL",36,h-292,w-72,"small")
    hero=J+"wizard-input.png" if "Jana2020" in metadata["filename"] else W+"execution-completed.png" if "Complete" in metadata["filename"] else S+"local-run-completed.png"
    figure(c,hero,"wizard-summary" if "Jana2020" in metadata["filename"] else None,36,h-330,w-72,280,metadata,caption="Authentic current application rendering. Synthetic teaching data; see edition/evidence page.")
    paragraph(c,"2.0.3 development-source interface · Public Windows release currently v2.0.2\n\nReview edition: native Jana launch/return captures pending. Token controls captured and sanitised.",36,135,w-72,"small")
    c.bookmarkPage("cover");c.addOutlineEntry("Cover","cover",0);c.showPage()
    for toc in range(toc_pages):
        page_no=2+toc;frame(c,title,page_no,total,A4)
        c.bookmarkPage(f"contents-{toc}")
        if toc==0:c.addOutlineEntry("Contents","contents-0",0)
        y=paragraph(c,"Contents" if toc==0 else "Contents · continued",36,h-60,w-72,"heading")-18
        if toc_pages==1:
            selected=enumerate(pages)
        else:selected=enumerate(pages[toc*24:(toc+1)*24],start=toc*24)
        for index,p in selected:
            num=2+toc_pages+index
            label=p["title"]
            c.setFont("Body",9.0);c.setFillColor(NAVY)
            if pdfmetrics.stringWidth(label,"Body",9)>w-115:
                while pdfmetrics.stringWidth(label+"…","Body",9)>w-115:label=label[:-1]
                label += "…"
            c.drawString(36,y,label);c.drawRightString(w-36,y,str(num))
            c.linkRect("",f"page-{index}",(36,y-4,w-36,y+12),relative=0,thickness=0)
            y-=24 if toc_pages>1 else 29
        c.showPage()
    images=set()
    for index,p in enumerate(pages):
        size=landscape(A4) if p.get("landscape") else A4
        c.setPageSize(size);w,h=size
        frame(c,title,index+2+toc_pages,total,size)
        c.bookmarkPage(f"page-{index}");c.addOutlineEntry(p["title"],f"page-{index}",0)
        y=paragraph(c,p["title"],36,h-57,w-72,"heading")-5
        width=w-72
        blocks=[b.strip() for b in p["text"].split("\n\n") if b.strip()]
        if p.get("reference"):
            # Each option gets its own genuine, enlarged Qt control row.
            split=re.split(r"\n\n---\n\n",p["text"])
            for field_index,content in enumerate(split):
                for block in content.split("\n\n"):
                    if block.strip():y=paragraph(c,block,36,y,width)
                key=p["keys"][field_index]
                row=control_images.get(key)
                if row:
                    y=figure(c,row["path"],None,36,y-4,width,55,p,caption="Genuine enlarged control row · default/imported/disabled context may differ; see text above.")
                    images.add(row["path"])
                y-=14
        else:
            for block in blocks:y=paragraph(c,block,36,y,width)
            if p.get("image"):
                available=y-60
                if available<105:raise ValueError("Insufficient screenshot room: "+p["title"])
                y=figure(c,p["image"],p.get("crop"),36,y-8,width,min(available-45,420 if not p.get("landscape") else 450),p,p.get("caption"))
                images.add(p["image"])
        if y<42:raise ValueError(f"Page content overflow: {p['title']} bottom={y:.1f}")
        c.showPage()
    c.save()
    embedded=fitz.open(path)
    embedded.embfile_add("DejaVu-font-license.txt",(BASE/"assets/DejaVu-font-license.txt").read_bytes(),desc="Embedded font copyright and permission notices")
    embedded.saveIncr();embedded.close()
    # Distribution directory contains exactly the requested PDFs.
    shutil.copy2(path,OUT/path.name)
    pdf=fitz.open(path)
    problems=[];links=0;figures=0
    render=QA/path.stem;render.mkdir(parents=True,exist_ok=True)
    for index,p in enumerate(pdf):
        text=p.get_text()
        if len(text.strip())<30:problems.append(f"blank/textless page {index+1}")
        if "\ufffd" in text:problems.append(f"replacement glyph page {index+1}")
        if re.search(r"honzi|ochlor|2int3total|VznB7",text,re.I):problems.append(f"private text page {index+1}")
        for block in p.get_text("dict")["blocks"]:
            rect=fitz.Rect(block["bbox"])
            if not p.rect.contains(rect):problems.append(f"out-of-page block page {index+1}")
            if block["type"]==1:figures+=1
        for link in p.get_links():
            links+=1
            if "uri" in link and not link["uri"].startswith(("https://","PhaseStudio_")):problems.append(f"unexpected link {link['uri']}")
        p.get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False).save(render/f"page-{index+1:03d}.png")
    if not pdf.get_toc():problems.append("missing navigation outline")
    if problems:raise AssertionError("; ".join(problems))
    summary=dict(filename=path.name,pages=len(pdf),bytes=path.stat().st_size,unique_screenshots=len(images),embedded_image_occurrences=figures,
                 hyperlinks=links,outline_entries=len(pdf.get_toc()),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 path=str(path.relative_to(ROOT)).replace("\\","/"),distribution_copy=str((OUT/path.name).relative_to(ROOT)).replace("\\","/"),qa="All pages rendered; automated bounds/text/privacy/link/navigation checks passed",
                 source=str(source.relative_to(BASE)),publication_ready=False,acceptance_gaps=["native Jana launch/return and continuation screenshots","2.0.3 packaged/native acceptance"])
    print(json.dumps(summary,ensure_ascii=True),flush=True)
    return summary

S="screenshots/standalone/";J="screenshots/jana2020/";W="screenshots/workflow/"
summaries=[document(source) for source in sorted((BASE/"sources").glob("*.md")) if "<!-- DOCUMENT " in source.read_text(encoding="utf8")]
(BASE/"sources/pdf_manifest.json").write_text(json.dumps(summaries,indent=2,ensure_ascii=False),encoding="utf8")
