""" annotation to pdf export using reportlab and pypdf
all local functions on or from backup except

add_authors() on backup, optional upload to pdf

"""
from typing import  Union, Optional, BinaryIO
import time
import os
import os.path as osp
import json
import logging
from tempfile import mkstemp
import re
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.graphics.shapes import Drawing, PolyLine
from reportlab.lib import colors
from reportlab.graphics import renderPDF
import pypdf

# .rm version 6 api
from .rmscene import SceneLineItemBlock, Line, read_blocks
from .unremarkable import restart_xochitl, _is_uuid, _find_folder, _get_xochitl, _rsync_up
from .pdf import get_pdf_info

##
# .rm annotation binary files
#
def read_rm(data: Union[str, BinaryIO]) -> list:
    """
    .rm reader to to list
    """
    return [e for e in read_blocks(data)]

def read_lines(blocks: list) -> tuple:
    """ reads 
    """
    lines = []
    _x = []
    _y = []
    for i, block in enumerate(blocks):
        if isinstance(block, SceneLineItemBlock):
            if isinstance(block.item.value, Line):
                line = read_line_rm(block)
                lines.append(line)
                assert (line['x'] and line['y']), f"line {i} has no members! {line}"
                _x += line['x']
                _y += line['y']
            elif block.item.value is not None:
                raise ValueError(f'SceneLineItemBlock()[{i}].item().value {type(block.item.value)}')
                # print(f'SceneLineItemBlock()[{i}].item().value class : {type(block.item.value)}')
    if lines  and _x and _y:
        minmax = (min(_x), max(_x)), (min(_y), max(_y))
    else:
        minmax = None
    return lines, minmax

def read_line_rm(line: SceneLineItemBlock):
    """
    .__dict__.keys() ['extra_data', 'parent_id', 'item']
    .item.__dict__.keys() ['item_id', 'left_id', 'right_id', 'deleted_length', 'value']
    .item.value.__dict__.keys() ['color', 'tool', 'points', 'thickness_scale', 'starting_length']

    .item.value.color               <PenColor.BLACK: 0>
    .item.value.tool                <Pen.FINELINER_2: 17>
    .item.value.thickness_scale     1.3742877492877492
    .item.value.starting_length     0.0

    .item.value.tool 
    <enum 'Pen'>
    'BALLPOINT_1', 'BALLPOINT_2', 'CALIGRAPHY', 'ERASER', 'ERASER_AREA', 'FINELINER_1',
    'FINELINER_2', 'HIGHLIGHTER_1', 'HIGHLIGHTER_2', 'MARKER_1', 'MARKER_2', 'MECHANICAL_PENCIL_1',
    'MECHANICAL_PENCIL_2', 'PAINTBRUSH_1', 'PAINTBRUSH_2', 'PENCIL_1', 'PENCIL_2'

    .item.value.color
    <enum 'PenColor'>
    'BLACK', 'GRAY', 'WHITE', 'YELLOW', 'GREEN', 'PINK', 'BLUE', 'RED', 'GRAY_OVERLAP'

    for line in lines:
        if line.item.value is not None:
            print(line.item.value.tool)
            print(line.item.value.__dict__.keys()) ['color', 'tool', 'points', 'thickness_scale', 'starting_length']
        Pen.FINELINER_2
        Pen.HIGHLIGHTER_2
        Pen.PAINTBRUSH_2
        Pen.CALIGRAPHY
    """
    # dict_keys(['color', 'tool', 'points', 'thickness_scale', 'starting_length'])
    points = line.item.value.points
    out = {
        "x": [p.x for p in points],
        "y": [p.y for p in points],
        "speed" : [p.speed for p in points],
        "direction" : [p.direction for p in points],
        "width" : [p.width for p in points],
        "pressure" : [p.pressure for p in points],
        "color" : line.item.value.color,
        "tool" : line.item.value.tool,
        "thickness_scale" : getattr(line.item.value, 'thickness_scale', 1.0),
        "starting_length" : getattr(line.item.value, 'starting_length', 0.0)
    }
    return out


def get_rm_files(root, bare_uuid: bool = False) -> list:
    """ return .rm files associated to a remarkable pdf"""
    root = osp.splitext(root)[0]
    out = []
    if osp.isdir(root):
        out = [f.path for f in os.scandir(root) if f.name.endswith('.rm')]
        if bare_uuid:
            out = [osp.splitext(osp.basename(f))[0] for f in out]
    return out

##
# .content json files
#
def read_content(root: str, rm_files: Optional[tuple] = None, add_all: bool = False) -> dict:
    """ uid.content json files
    content.keys()
   ['cPages',
   'coverPageNumber',
   'customZoomCenterX',
   'customZoomCenterY',
   'customZoomOrientation',
   'customZoomPageHeight',
   'customZoomPageWidth',
   'customZoomScale',
   'documentMetadata', 'dummyDocument', 'extraMetadata', 'fileType',
   'fontName', 'formatVersion',
   'lineHeight', 'margins', 'orientation',
   'pageCount', 'pageTags',
   'sizeInBytes', 'tags',
   'textAlignment', 'textScale',
   'zoomMode'])
    """
    folder = osp.splitext(root)[0]
    _uuid = osp.basename(folder)
    assert _is_uuid(_uuid), f"name {root} is not uuid"
    _uuid = folder +".pdf" if osp.isfile(folder +".pdf") else _uuid
    content_file = folder +".content"
    assert osp.isfile(content_file), f"<{content_file}> not found"
    with open(content_file, 'r', encoding='utf8') as fi:
        data = json.load(fi)
    out = {"uuid": _uuid, "pageCount": data["pageCount"]}
    for k in ['customZoomCenterX',
              'customZoomCenterY',
              'customZoomOrientation',
              'customZoomPageHeight',
              'customZoomPageWidth',
              'customZoomScale',
              'orientation',
              'margins',
              'zoomMode']:
        if k in data:
            out[k] = data[k]
    # get all rm_files
    if rm_files is None:
        if osp.isdir(folder):
            rm_files = [f.path for f in os.scandir(folder) if f.name.endswith(".rm")]
        else:
            rm_files = []
    out['pages'] = []
    if rm_files:
        rm_ids = [osp.splitext(osp.basename(f))[0] for f in rm_files]
        if 'cPages' in data and 'pages' in data['cPages']:
            pages = data['cPages']['pages']
            for i, page in enumerate(pages):
                if page['id'] in rm_ids:
                    # if add_all: # debug add entire content of page
                    #     page_data += [page]
                    # .rm file fullname
                    page_dict = {"rm": rm_files[rm_ids.index(page['id'])]}
                    # page number
                    if 'redir' in page:
                        page_dict['number'] = page['redir']['value']
                    else:
                        page_dict['number'] = i # is this correct?
                    if 'verticalScroll' in page:
                        page_dict['verticalScroll'] = page['verticalScroll']['value']
                    out['pages'].append(page_dict)

        elif 'pages' in data:
            pages = []
            if not 'redirectionPageMap' in data:
                data['redirectionPageMap'] = list(range(0, len(data['pages'])))
            for i, page in enumerate(data['pages']):
                if page in rm_ids:
                    j = i if i not in data['redirectionPageMap'] else data['redirectionPageMap'][i]
                    if i < len(data['redirectionPageMap']):
                        out['pages'] += [{"rm": rm_files[rm_ids.index(page)],
                                        "number": j}]

    return out


def get_annotated(folder: str = "?") -> dict:
    """ read .content and .metadata files to find rm files
        return Documents with annotations
    """
    if folder == "?":
        folder = _get_xochitl()
    if folder is None:
        folder = _find_folder('xochitl')
    assert osp.isdir(folder), f"stored xochitl backup folder not found {folder}"

    out = {"annotated":[], "old":[], "noannot":[],
           "path": folder}

    contents = [f.path for f in os.scandir(folder) if f.name.endswith('.content')]
    for i, c in enumerate(contents):
        metadata = c.replace('.content', '.metadata')
        if not osp.isfile(metadata):
            print(f"no metadata file for content file {c}, skipping")
            continue
        with open(metadata, 'r', encoding='utf8') as fi:
            m = json.load(fi)
        if m['type'] == 'DocumentType':
            name = m['visibleName']
            uid = osp.splitext(osp.basename(c))[0]
            parent = "MyFiles"
            if _is_uuid(m['parent']):
                with open(osp.join(osp.dirname(c), m['parent']+".metadata"),
                          'r', encoding='utf8') as fi:
                    mparent = json.load(fi)
                parent = mparent['visibleName']

            annot = {"uuid":uid, "name": name, "parent": parent}
            pdf = c.replace(".content", ".pdf")
            has_pdf = osp.isfile(pdf)
            if has_pdf:
                pdf_ratio = []
                _pdfinfo = get_pdf_info(pdf)
                if isinstance(_pdfinfo['height'], list):
                    _h = _pdfinfo['height']
                    _w = _pdfinfo['width']
                    _s = set([_h.index(i) for i in set(_h)] + [_w.index(i) for i in (_w)])
                    pdf_ratio = [_h[i]/_w[i] for i in _s]
                else:
                    pdf_ratio = _pdfinfo['height']/_pdfinfo['width']
                annot['pdf_ratio'] = pdf_ratio
            content = read_content(c)
            if 'orentation' in content:
                annot['orientation'] = content['orientation']

            if 'pages' in content and len(content['pages']):
                numbers = [p['number'] for p in content['pages']]
                annot["annotated"] = numbers

                if 'zoomMode' in content:
                    annot['zoom_mode'] = content['zoomMode']
                    out['annotated'] += [annot]
                else:
                    out["old"] += [annot]
            else:
                out['noannot'] += [annot]

    return out


def get_name_from_uuid(uid: str) -> str:
    """get visible name from uuid, uuid must exist
    """
    metadata = osp.splitext(uid)[0]+".metadata"
    if not osp.isfile(metadata):
        xochitl = _get_xochitl()
        metadata = osp.join(xochitl, metadata)
    assert osp.isfile(metadata), f"<{metadata}> not found"
    with open(metadata, 'r', encoding='utf8') as fi:
        t = json.load(fi)
    return t['visibleName']


def get_uuid_from_name(name: str,
                       partial: bool = False,
                       ignore_case: bool = False,
                       xochitl: Optional[str] = None) -> Union[str, list, None]:
    """get uuid from visible names
    Args:
        name    (str) filename we are looking for
        partial (bool [False]) return list of partially matching names
        ignore_case (bool [False]) ignore case
        xochitl (str [None]) xochitl folder, default from ~/.xochitl
    examples:
    # list of tuples with "Adversarial" in name
    >>> get_uuid_from_name("Adversarial", partial=True)
    >>> get_uuid_from_name("TokenLearner What Can 8 Learned Tokens Do for Images and Videos")
    """
    if xochitl is None:
        xochitl = _get_xochitl()
    assert osp.isdir(xochitl), f"backup remarkable folder not found <{xochitl}?"

    metadatas = [f.path for f in os.scandir(xochitl) if f.name.endswith(".metadata")]
    out = [] if partial else None
    if ignore_case:
        name = name.lower()
    for i, meta in enumerate(metadatas):
        with open(meta, 'r', encoding='utf8') as fi:
            t = json.load(fi)
        visible_name = t['visibleName']
        if ignore_case:
            visible_name = visible_name.lower()
        if partial and name in visible_name:
            out += [(t['visibleName'], meta)]
        elif name == visible_name:
            return meta
    return out


def get_annotation_data(content: dict, annot: Union[str,int]) -> tuple:
    """  a bit redundant CLEANUP
    Args
        content     (dict) - output from read_content
        annot  (str, int) .rm filename, uuid for rm file name, or page num with .rm file
    number = ?

    import os.path as osp
    from unremarkable.unremarkable import read_content
    from sandy import *

    f = "2adc1f4a-06ed-487d-b6b2-d2d995bd467e"
    xochitl='/home/z/data/reMarkable/xochitl'
    f = osp.join(xochitl,f)
    out = read_content(f)

    numbers = [p['number'] for p in out['pages']]

    data, lines = get_annotation_data(out, number)

    """
    logging.basicConfig(level=logging.ERROR)
    # _logger = logging.getLogger('your_module_with_logger.__name__')
    # _logger.setLevel(logging.ERROR)

    if isinstance(annot, str):
        number = None
        for i, page in enumerate(content['pages']):
            if annot in page['rm']:
                annot = page['rm']
                number = page['number']
                break
        assert osp.isfile(annot) and annot.endswith('.rm'), f"annotation {annot} not found in {content['pages']}"
    elif isinstance(annot, int):
        numbers = [p['number'] for p in content['pages']]
        assert annot in numbers, f"page number {annot} has no .rm file, only {numbers}"
        number = annot
        annot = content['pages'][numbers.index(annot)]['rm']
    data = {k:v for k,v in content.items() if k != 'pages'}
    data['rm'] = annot

    blocks = read_rm(annot)
    lines, data['limits'] = read_lines(blocks)
    if lines:
        data['annotation_width'] = data['limits'][0][1] - data['limits'][0][0]
        data['annotation_height'] = data['limits'][1][1] - data['limits'][1][0]

    # assuming that rm is annot over pdf
    if osp.isfile(content['uuid']):
        pdfinfo = get_pdf_info(content['uuid'])
        data['pdf_width'] = pdfinfo['width']
        data['pdf_height'] = pdfinfo['height']
        data['number'] = number
    return data, lines


def get_content_file(uid, xochitl: Optional[str] = None) -> str:
    """ returns .content file in folder if exits
    """
    if xochitl is None:
        xochitl = _get_xochitl()
    assert osp.isdir(xochitl), f"stored xochitl backup folder not found {xochitl}"
    assert _is_uuid(osp.splitext(osp.basename(uid))[0]), f"invalid remarkable file uuid {uid}"
    uid = osp.splitext(uid)[0]+'.content'
    if not osp.isfile(uid):
        uid = osp.join(xochitl, uid)
    assert osp.isfile(uid), f"file {uid} not found"
    return uid


def remarkable_name(filename,
                    xochitl: Optional[str] = None,
                    ignore_case: bool = True,
                    partial: bool = True) -> tuple:
    """return uuid and visible name 
    Args
        filename    (str) uuid or partial visible name
        is not sufficiently unique asserts and prints all possible names
    """
    file_uuid, name, metadata, content, pdf = _gather_uuid_info(filename, xochitl=xochitl,
                                                                ignore_case=ignore_case,
                                                                partial=partial)
    return file_uuid, name

def _gather_uuid_info(filename,
                      xochitl: Optional[str] = None,
                      ignore_case: bool = True,
                      partial: bool = True) -> tuple:
    if xochitl is None:
        xochitl = _get_xochitl()
    if not _is_uuid(osp.basename(osp.splitext(filename)[0])):
        name = filename
        # try to find exact name first
        _fname = get_uuid_from_name(filename, xochitl=xochitl, ignore_case=False, partial=False)
        if _fname is None:
            _fname = get_uuid_from_name(filename, xochitl=xochitl, partial=partial,
                                        ignore_case=ignore_case)
            assert len(_fname) == 1, f"pass exact filename, <{filename}> not found,{_fname}"
            name, _fname = _fname[0]
        metadata = _fname
        assert metadata is not None, f"arg expected visible file name or uuid, got {filename}"
    else:
        metadata = osp.splitext(filename)[0]+".metadata"
        if not osp.isfile(metadata):
            metadata = osp.join(xochitl, osp.basename(metadata))
        assert osp.isfile(metadata), f"metadata file {metadata} not found"
        name = get_name_from_uuid(metadata)

    content = metadata.replace(".metadata", ".content")
    assert osp.isfile(content), f"content file not found {content}"
    pdf = metadata.replace('.metadata', '.pdf')
    file_uuid = osp.splitext(osp.basename(metadata))[0]

    return file_uuid, name, metadata, content, pdf

# patch .content files in remarkable tablet with authors
# local function on backup -> .content file
# upload to remarkable -> .content_file
def add_authors(filename: str,
                authors: Union[str, tuple],
                title: Optional[str] = None,
                year: Union[str, int, None] = None,
                tags: Union[tuple, str, None] = None,
                xochitl: Optional[str] = None,
                override: bool = False,
                upload: bool = True,
                restart: bool = False):
    """ add Authors to .content json file so they show in remarkable UI
    Args
        filename    (str) uuid or visible name (can be partial if unique)
        authors     (str, tuple)
        title       (str [None]) only writes if override set to True
        year        (int, str) if passed, concat to authors so it shows in xochitl
        tags        (str, tuple) -
        upload      (bool [True]) upload to tablet, False: only local file
        restart     (bool [False]) restarts xochitl service
    Examples:
     add_authors('Learning to Learn', ['S. Fang', 'J. Li', 'X. Lin', 'R. Ji'], year=2021)
     add_authors('60e7724c-61cc-492d-9d37-cc14430e0efd',
                 ['S. Fang', 'J. Li', 'X. Lin', 'R. Ji'], year=2021)
    """
    file_uuid, name, metadata, content, pdf = _gather_uuid_info(filename, xochitl)

    with open(content, 'r', encoding='utf8') as _fi:
        data = json.load(_fi)
    if 'documentMetadata' not in content:
        data['documentMetadata'] = {}
    if isinstance(authors, str):
        authors = [authors]
    if len(authors) > 1:
        authors = [", ".join(authors)] # examples are all lists of 1 str
    if year is not None:
        authors[-1] = authors[-1]+f", {year}"
    data['documentMetadata']['authors'] = list(authors)
    if title is not None and (override or 'title' not in data['documentMetadata']):
        data['documentMetadata']['title'] = title

    if tags is not None:
        tags = tags if isinstance(tags, tuple) else (tags,)
        if 'tags' not in content:
            data['tags'] = []
        names = [tag['name'] for tag in data['tags']]
        for tag in tags:
            if tag not in names:
                data['tags'] += {'name':tag, 'timestamp':int(time.time())}

    with open(content, 'w', encoding='utf8') as _fi:
        json.dump(data, _fi, indent = 4)
    if upload:
        _rsync_up(content)
        if restart:
            restart_xochitl()


def export_annotated_pdf(filename: str,
                         page: Union[int, tuple, bool] = True,
                         out_folder: str = ".",
                         out_name: Optional[str] = None,
                         xochitl: Optional[str] = None) -> None:
    """ export merged pdf file from backup
    Args
        filename    (str) uuid in xochitl directory, or visible name
            .metadata and .content must exist

        
        page        (int, tuple, bool [True])
            int:     export single page, page must have annotation
            tuple:   export pages in tuple, at least one must have annotations
            True:    export all pages, annotations must exist
            False:   query pages
        out_name    (str [None]) if None : visible name with _annotated_pagen.
        xochitl     (str) root folder, if None look for stored backups

        1,2,3,4
        name': 'God of Carnage Full',
  'pdf_ratio': 0.7727272727272727,
  'uuid': '885a692b-e657-43f3-a6f3-0bc62594f4da',
  'zoom_mode': 'bestFit'},
get_pdf_info('/home/z/data/reMarkable/xochitl/885a692b-e657-43f3-a6f3-0bc62594f4da.pdf')
{'pages': 35, 'width': 792, 'height': 612}


 {'annotated': [0, 1, 2, 3, 4],
  'name': 'LLaMA Open and Efficient Foundation Language Models',
  'pdf_ratio': 1.4142851383223918,
  'uuid': '3c50b5d6-e9b3-4dae-8280-42c5490b83f3',
  'zoom_mode': 'customFit'},

  # OK
   {'annotated': [1, 2, 5, 9, 10, 13, 14],
  'name': 'Blessing of dimensionality mathematical foundations of the '
          'statistical physics of data',
  'pdf_ratio': 1.4142851383223918,
  'uuid': '72cc8f6e-155b-4d67-9ada-efebc32cd30b',
  'zoom_mode': 'customFit'},

  #OK
 {'annotated': [0, 1, 2, 3],
  'name': 'Intrinsic Dimension Estimation Using Packing Numbers',
  'pdf_ratio': 1.2941176470588236,
  'uuid': '2adc1f4a-06ed-487d-b6b2-d2d995bd467e',
  'zoom_mode': 'fitToHeight'},
# OK
  {'annotated': [0, 1, 2, 3, 4, 9],
  'name': 'Do deep generative models know what they dont know',
  'pdf_ratio': 1.2941176470588236,
  'uuid': '3bb743f8-15b9-45a5-87a1-1369dff6769c',
  'zoom_mode': 'bestFit'},
    """
    file_uuid, name, metadata, content, pdf = _gather_uuid_info(filename, xochitl)

    # resolve output_name
    if out_name is None:
        out_name = name.replace(' ', '_')
    if out_name[-4:] != '.pdf':
        out_name += '.pdf'

    out_folder = osp.abspath(osp.expanduser(out_folder))
    out_name = osp.join(out_folder, "_annotated".join(osp.splitext(out_name)))
    assert osp.isdir(out_folder), f"cannot export file to nonexistent folder {out_folder}"

    out = read_content(content)

    # get pages to export_ make sure that annotations exist
    if page is True:
        page = tuple(range(out['pageCount']))
    else:
        if isinstance(page, int):
            page = (page,)
        if isinstance(page, (list, tuple)):
            _pages = re.sub(r'[\,\)\]]', "", re.sub(r'[\(\[\ ]', "_", str(page)))
            out_name = _pages.join(osp.splitext(out_name))

    numbers = [out['pages'][i]['number'] for i in range(len(out['pages']))]
    if page is False or not set(page) & set(numbers):
        _msg = "" if page is False else f"no annotations on pages {page}, "
        print(f"{_msg}annotations on {numbers}, exiting")
        print(f"no pages chosen for export {page} contain annotations {numbers}")
        return None

    if osp.isfile(pdf):
        _info = get_pdf_info(pdf)
        out['pdf_width'], out['pdf_height']  = _info['width'], _info['height']
    else:
        out['pdf_width'], out['pdf_height'] = A4

    #xoff = y_offset = (2572.666 - rm_height)/2 = 38.158
    scale_x, scale_y, scale, center_x, center_y = get_xform(out)

    mainpdf = None
    if osp.isfile(pdf):
        mainpdf = pypdf.PdfReader(pdf)
    pdf_writer = pypdf.PdfWriter()
    _, tempname = mkstemp(suffix=".pdf")

    for i, p in enumerate(page):
        mainpage = mainpdf.pages[p] if mainpdf is not None else None

        if p in numbers:
            data, lines = get_annotation_data(out, p)
            if data['limits'] is None:
                print(f"page {p} has no lines?")
                continue
            shifted = shift_lines(lines, center_x, scale_x, center_y, scale_y, out['pdf_height'])
            draw_annotation(out, lines, shifted, out_name=tempname)
            overlay = pypdf.PdfReader(tempname).pages[0]
            if mainpdf is None:
                mainpage = overlay
            else:
                mainpage.merge_page(overlay)
        if mainpage is not None:
            pdf_writer.add_page(mainpage)

    with open(out_name, 'wb') as fi:
        pdf_writer.write(fi)
    print(f"Saved merged pdf to <{out_name}>")



###
# export single page process
#
def get_data(uid, page, xochitl: Optional[str] = None):
    """ returns pdf, settings dict, lines
    """
    if xochitl is None:
        xochitl = _get_xochitl ()
    assert osp.isdir(xochitl), f"stored xochitl backup folder not found {xochitl}"
    pdf = get_content_file(uid, xochitl)
    out = read_content(pdf)
    numbers = [out['pages'][i]['number'] for i in range(len(out['pages']))]
    pdfname = get_name_from_uuid(pdf)
    assert page in numbers, f"requested page {page}, of {numbers}"
    # print(f"merging page {page} from {numbers}, '{pdfname}', {osp.basename(pdf)}")
    data, lines = get_annotation_data(out, page)
    return pdf, data, lines


def get_xform(data: dict) -> tuple:
    """ unclear how alingment works 
    """
    rm_ratio = 1872/1404 # points?
    rm_width = 1929.5    # pixels?
    rm_height = rm_width*4/3

    if data['orientation'] == 'landscape':
        rm_width, rm_height = rm_height, rm_width
        rm_ratio = 1/rm_ratio
    # what of customZoomOrientation, test if example encountered

    if data['zoomMode'] == 'bestFit': #
        if data['pdf_height']/data['pdf_width'] < rm_ratio:
            rm_height = rm_width*rm_ratio
            scale_y = scale_x = data['pdf_width']/rm_width
        else:
            rm_width = rm_height/rm_ratio
            scale_y = scale_x = data['pdf_height']/rm_height

    elif data['zoomMode'] == 'fitToHeight':
        # if data['pdf_height']/data['pdf_width'] < rm_ratio:
        rm_width = rm_height/rm_ratio
        scale_y = scale_x = data['pdf_width']/rm_width
        # else: # TODO test if example encountered
        #     rm_width = rm_height/rm_ratio
        #     scale_y = scale_x = data['pdf_height']/rm_height

    elif data['zoomMode'] == 'customFit':
        rm_width = data['customZoomPageWidth']
        rm_height = data['customZoomPageHeight']

        # scale lines to pdf size
        scale_x = data['pdf_width']/rm_width
        scale_y = data['pdf_height']/rm_height

    # UNUSED? check if example encountered where it matters
    scale = data['customZoomScale']
    scale = 1 #

    # lines need center transform
    center_x = rm_width/2 + data['customZoomCenterX']
    center_y =  data['customZoomCenterY'] - rm_height/2
    # print([(k, data[k])for k in ('orientation', 'pdf_width', 'pdf_height', 'zoomMode')])
    # print(f"rm_width {rm_width}, rm_height {rm_height}, scale_y {scale_y},  {scale_x}",
    #       f"pdfw/w {data['pdf_width']/rm_width}, pdfh/h {data['pdf_height']/rm_height}")
    # print(f"center_x {center_x}, customZoomCenterX {data['customZoomCenterX']}")
    # print(f"center_y {center_y}, customZoomCenterY {data['customZoomCenterY']}")
    center_y = 0 # WHY?
    return scale_x, scale_y, scale, center_x, center_y


def shift_lines(lines: list,
                center_x: float,
                scale_x: float,
                center_y: float,
                scale_y: float,
                pdf_height: float) -> list:
    """ transforms lines by input transform 
    """
    # scale = data['customZoomScale'] | 1/data['customZoomScale'] or 1A
    shifted_lines  = []
    for i, line in enumerate(lines):
        # recenter then scale to pdf
        x = (np.array(line['x']) + center_x) * scale_x
        y = (np.array(line['y']) + center_y) * scale_y
        # flip y
        y = pdf_height - y
        # x /= scale
        # y /= scale
        shifted_lines.append(np.stack((x,y)).T)
    return shifted_lines


def draw_annotation(data: dict,
                    lines: list,
                    shifted_lines: list,
                    out_name: str = 'annot.pdf') -> None:
    """ only lines are drawn
    Eraser is not really an eraser but a white marker! , ignored here
    """
    d = Drawing(data['pdf_width'], data['pdf_height'])
    for i, line in enumerate(lines):
        if line['tool'].name == "ERASER":
            continue
        color = colors.__dict__[line['color'].name.lower().replace("_overlap", "")]
        line_width = line['thickness_scale']
        opacity = None
        if "HIGHLIGHTER" in line['tool'].name:
            opacity = 0.4
            line_width *= 2
        line_join = line_cap = 0
        if "MARKER" in line['tool'].name:
            line_join = line_cap= 1

        _tools = ('FINELINER_1', 'PENCIL_1', 'MECHANICAL_PENCIL_1', 'BALLPOINT_1',
                  'FINELINER_2', 'PENCIL_2', 'MECHANICAL_PENCIL_2', 'BALLPOINT_2')
        if line['tool'].name in _tools:
            line_width /= 3
        d.add(PolyLine(shifted_lines[i].reshape(-1).tolist(), strokeWidth=line_width,
                       strokeColor=color, strokeOpacity=opacity,
                       strokeLineJoin=line_join, strokeLineCap=line_cap))
    renderPDF.drawToFile(d, out_name)
