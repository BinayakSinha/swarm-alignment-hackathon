"""Convert report/report.html into an editable Word file (stdlib only).
Usage (from the project root):  python3 -I report/make_docx.py
Figures are taken from report/fig_png/*.png (PNG renders of results/*.svg)."""
import os
import re
import struct
import zipfile
from html import escape as _esc
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "report", "report.html")
OUT = os.path.join(ROOT, "Swarm_Alignment_Track4_Report.docx")
PNG_DIR = os.path.join(ROOT, "report", "fig_png")

PAGE_W, PAGE_H, MAR_LR, MAR_TB = 11906, 16838, 964, 1020  # A4, 17/18 mm margins
TEXT_W = PAGE_W - 2 * MAR_LR
FONT, MONO = "Times New Roman", "Consolas"


def esc(s):
    return _esc(s, quote=False)


def run(text, b=False, i=False, code=False, size=None):
    rpr = ""
    if code:
        rpr += f'<w:rFonts w:ascii="{MONO}" w:hAnsi="{MONO}" w:cs="{MONO}"/>'
    if b:
        rpr += "<w:b/>"
    if i:
        rpr += "<w:i/>"
    if code or size:
        rpr += f'<w:sz w:val="{size or 18}"/>'
    rpr = f"<w:rPr>{rpr}</w:rPr>" if rpr else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def para(runs, style=None, align=None, num=None, extra_ppr="", keep_next=False):
    ppr = ""
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if keep_next:
        ppr += "<w:keepNext/>"
    if num:
        ppr += f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>'
    ppr += extra_ppr
    if align:
        ppr += f'<w:jc w:val="{align}"/>'
    return f"<w:p><w:pPr>{ppr}</w:pPr>{''.join(runs)}</w:p>"


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


class Conv(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body = []           # document.xml body parts
        self.media = []          # (zip name, local path)
        self.runs = None         # current paragraph's runs
        self.fmt = {"b": 0, "i": 0, "code": 0}
        self.block = None        # current block info dict
        self.in_box = False
        self.lists = []          # stack of numIds
        self.n_ol = 0
        self.ol_ids = []         # numIds for ordered lists (each restarts)
        self.table = None
        self.cell = None
        self.in_title = self.in_style = False
        self.fig_img = None
        self.small = False

    # -- helpers
    def start_par(self, **kw):
        self.runs = []
        self.block = kw

    def end_par(self):
        if self.runs is None:
            return
        kw, runs = self.block, self.runs
        self.runs, self.block = None, None
        if not runs and not kw.get("keep_empty"):
            return
        p = para(runs, style=kw.get("style"), align=kw.get("align"), num=kw.get("num"),
                 keep_next=kw.get("keep_next", False))
        if self.in_box:
            self.box.append(p)
        elif self.cell is not None:
            self.cell["paras"].append(p)
        else:
            self.body.append(p)

    def add_text(self, text):
        if self.runs is None:
            if not text.strip():
                return
            self.start_par(style="BodyText")
        text = re.sub(r"\s+", " ", text)
        if not self.runs:
            text = text.lstrip()
        if not text:
            return
        self.runs.append(run(text, b=self.fmt["b"] > 0 or (self.cell or {}).get("th", False),
                             i=self.fmt["i"] > 0, code=self.fmt["code"] > 0,
                             size=19 if self.small else None))

    # -- parser callbacks
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "title":
            self.in_title = True
        elif tag == "style":
            self.in_style = True
        elif tag == "div" and cls == "box":
            self.in_box, self.box = True, []
        elif tag == "div" and cls == "authors":
            self.start_par(style="Authors", align="center")
        elif tag == "div" and cls == "with":
            self.start_par(style="Authors", align="center"); self.fmt["b"] += 1
        elif tag == "div" and cls == "abstract-h":
            self.start_par(style="Authors", align="center", keep_next=True); self.fmt["b"] += 1
        elif tag == "div" and cls == "cap":
            self.start_par(style="Caption")
        elif tag == "h1":
            self.start_par(style="Title", align="center")
        elif tag in ("h2", "h3"):
            self.end_par()
            if "pb" in cls:
                self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
            self.start_par(style="Heading1" if tag == "h2" else "Heading2")
        elif tag == "p":
            self.end_par()
            self.start_par(style="Abstract" if self.in_box else "BodyText")
        elif tag in ("ol", "ul"):
            self.end_par()
            if tag == "ol":
                self.n_ol += 1
                nid = 10 + self.n_ol
                self.ol_ids.append(nid)
            else:
                nid = 1
            self.lists.append(nid)
            self.small = "refs" in cls
        elif tag == "li":
            self.end_par()
            self.start_par(style="ListParagraph", num=self.lists[-1])
        elif tag == "b":
            self.fmt["b"] += 1
        elif tag == "i":
            self.fmt["i"] += 1
        elif tag == "code":
            self.fmt["code"] += 1
        elif tag == "br":
            if self.runs is not None:
                self.runs.append("<w:r><w:br/></w:r>")
        elif tag == "table":
            self.end_par()
            self.table = []
        elif tag == "tr":
            self.table.append([])
        elif tag in ("td", "th"):
            self.cell = {"paras": [], "th": tag == "th", "right": "n" in cls}
            self.table[-1].append(self.cell)
            self.start_par(style="TableText", align="right" if "n" in cls else None)
        elif tag == "figure":
            self.end_par()
        elif tag == "img":
            self.add_image(a["src"])
        elif tag == "figcaption":
            self.start_par(style="Caption")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "style":
            self.in_style = False
        elif tag == "div":
            if self.runs is not None:
                if self.block.get("style") == "Authors" and self.fmt["b"]:
                    self.fmt["b"] -= 1
                self.end_par()
            elif self.in_box:
                self.in_box = False
                b = '<w:{0} w:val="single" w:sz="6" w:space="0" w:color="999999"/>'
                borders = "".join(b.format(x) for x in ("top", "left", "bottom", "right"))
                self.body.append(
                    f'<w:tbl><w:tblPr><w:tblW w:w="{TEXT_W}" w:type="dxa"/><w:tblBorders>{borders}</w:tblBorders>'
                    '<w:tblLayout w:type="fixed"/><w:tblCellMar><w:top w:w="140" w:type="dxa"/>'
                    '<w:left w:w="200" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:right w:w="200" w:type="dxa"/>'
                    f'</w:tblCellMar></w:tblPr><w:tblGrid><w:gridCol w:w="{TEXT_W}"/></w:tblGrid>'
                    f'<w:tr><w:tc><w:tcPr><w:tcW w:w="{TEXT_W}" w:type="dxa"/></w:tcPr>{"".join(self.box)}</w:tc></w:tr></w:tbl>')
                self.body.append(para([], style="BodyText"))
        elif tag in ("h1", "h2", "h3", "p", "li", "figcaption"):
            self.end_par()
        elif tag in ("ol", "ul"):
            self.end_par()
            self.lists.pop()
            self.small = False
        elif tag == "b":
            self.fmt["b"] -= 1
        elif tag == "i":
            self.fmt["i"] -= 1
        elif tag == "code":
            self.fmt["code"] -= 1
        elif tag in ("td", "th"):
            self.end_par()
            if not self.cell["paras"]:
                self.cell["paras"].append(para([], style="TableText"))
            self.cell = None
        elif tag == "table":
            self.body.append(self.table_xml(self.table))
            self.table = None

    def handle_data(self, data):
        if self.in_title or self.in_style:
            return
        if self.table is not None and self.cell is None:
            return
        self.add_text(data)

    # -- tables and images
    def table_xml(self, rows):
        n = max(len(r) for r in rows)
        first = int(TEXT_W * 0.4)
        rest = (TEXT_W - first) // (n - 1)
        widths = [first] + [rest] * (n - 1)
        widths[0] += TEXT_W - sum(widths)
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
        out = [f'<w:tbl><w:tblPr><w:tblW w:w="{TEXT_W}" w:type="dxa"/>'
               '<w:tblLayout w:type="fixed"/>'
               '<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
               f'</w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
        for ri, r in enumerate(rows):
            head = all(c["th"] for c in r)
            trpr = "<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" if head else "<w:trPr><w:cantSplit/></w:trPr>"
            out.append(f"<w:tr>{trpr}")
            for ci, c in enumerate(r):
                bsz, bcol = ("12", "333333") if head else ("4", "BBBBBB")
                out.append(f'<w:tc><w:tcPr><w:tcW w:w="{widths[ci]}" w:type="dxa"/>'
                           f'<w:tcBorders><w:bottom w:val="single" w:sz="{bsz}" w:color="{bcol}"/></w:tcBorders>'
                           f'</w:tcPr>{"".join(c["paras"])}</w:tc>')
            out.append("</w:tr>")
        out.append("</w:tbl>")
        return "".join(out)

    def add_image(self, src):
        name = os.path.splitext(os.path.basename(src))[0] + ".png"
        path = os.path.join(PNG_DIR, name)
        idx = len(self.media) + 1
        rid = f"rIdImg{idx}"
        self.media.append((f"word/media/image{idx}.png", path, rid))
        pw, ph = png_size(path)
        cx = int(15.5 * 360000)                 # 15.5 cm wide
        cy = int(cx * ph / pw)
        drawing = (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{idx}" name="Figure {idx}"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{idx}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
        self.body.append(para([drawing], style="Figure", align="center", keep_next=True))


NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
HDR = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def pstyle(sid, name, size, b=False, i=False, before=0, after=120, align=None, keep_next=False,
           line=264, ind=None, based="Normal"):
    rpr = f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}"/>' + ("<w:b/>" if b else "") + \
          ("<w:i/>" if i else "") + f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    ppr = ("<w:keepNext/>" if keep_next else "") + \
          f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>' + \
          (ind or "") + (f'<w:jc w:val="{align}"/>' if align else "")
    out_lvl = {"Heading1": 0, "Heading2": 1}.get(sid)
    if out_lvl is not None:
        ppr += f'<w:outlineLvl w:val="{out_lvl}"/>'
    basedon = f'<w:basedOn w:val="{based}"/>' if sid != "Normal" else ""
    return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>{basedon}'
            f'<w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


STYLES = HDR + ('<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:cs="{FONT}" '
                f'w:eastAsia="{FONT}"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="en-GB"/></w:rPr></w:rPrDefault>'
                '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
                + pstyle("Normal", "Normal", 21)
                + pstyle("BodyText", "Body Text", 21, after=140, align="both")
                + pstyle("Abstract", "Abstract", 21, after=120, align="both")
                + pstyle("Title", "Title", 36, b=True, after=120, align="center", line=240)
                + pstyle("Authors", "Authors", 21, after=80, align="center")
                + pstyle("Heading1", "heading 1", 25, b=True, before=320, after=100, keep_next=True)
                + pstyle("Heading2", "heading 2", 22, b=True, before=200, after=80, keep_next=True)
                + pstyle("ListParagraph", "List Paragraph", 21, after=60, align="both",
                         ind='<w:ind w:left="360" w:hanging="360"/>')
                + pstyle("Caption", "caption", 18, after=200)
                + pstyle("Figure", "Figure", 21, before=120, after=60, align="center")
                + pstyle("TableText", "Table Text", 19, after=20, line=240)
                + '</w:styles>')


def numbering(ol_ids):
    def absn(aid, fmt, text):
        return (f'<w:abstractNum w:abstractNumId="{aid}"><w:multiLevelType w:val="singleLevel"/>'
                f'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/>'
                '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="360" w:hanging="360"/></w:pPr>'
                + ('<w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/></w:rPr>' if fmt == "bullet" else "")
                + '</w:lvl></w:abstractNum>')
    out = [HDR, '<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">',
           absn(0, "bullet", "")]
    out += [absn(nid, "decimal", "%1.") for nid in ol_ids]  # one list definition per ordered list
    out.append('<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>')
    for nid in ol_ids:
        out.append(f'<w:num w:numId="{nid}"><w:abstractNumId w:val="{nid}"/></w:num>')
    out.append("</w:numbering>")
    return "".join(out)


def main():
    c = Conv()
    c.feed(open(SRC, encoding="utf-8").read())
    c.end_par()
    sect = (f'<w:sectPr><w:pgSz w:w="{PAGE_W}" w:h="{PAGE_H}"/>'
            f'<w:pgMar w:top="{MAR_TB}" w:right="{MAR_LR}" w:bottom="{MAR_TB}" w:left="{MAR_LR}" '
            'w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>')
    doc = HDR + f'<w:document {NS}><w:body>{"".join(c.body)}{sect}</w:body></w:document>'
    rels = HDR + ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                  '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                  '<Relationship Id="rIdNum" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                  + "".join(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                            f'Target="media/{os.path.basename(z)}"/>' for z, _, rid in c.media)
                  + "</Relationships>")
    ctypes = HDR + ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Default Extension="png" ContentType="image/png"/>'
                    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                    '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
                    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                    '</Types>')
    root_rels = HDR + ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                       '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                       '</Relationships>')
    core = HDR + ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                  'xmlns:dc="http://purl.org/dc/elements/1.1/">'
                  '<dc:title>Reading the Message Board</dc:title><dc:creator>Binayak Sinha</dc:creator>'
                  '</cp:coreProperties>')
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("docProps/core.xml", core)
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", numbering(c.ol_ids))
        z.writestr("word/_rels/document.xml.rels", rels)
        for zname, path, _ in c.media:
            z.write(path, zname)
    print("wrote", OUT, "-", len(c.body), "blocks,", len(c.media), "figures")


if __name__ == "__main__":
    main()
