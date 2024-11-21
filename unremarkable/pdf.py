"""@xvdp
pdf utilities

pdf_mod() # add metadata, bibtex, modify page range

# non metadata & links preserving
rotate()  # rotate all pages in a pdf
doublepage() # convert to 2 page view
"""
from typing import Optional, Union
import os
import os.path as osp
from pprint import pprint
import numpy as np
import pypdf
from pybtex.database import parse_file, parse_string


def pdf_mod(in_path: Union[str, list, tuple],
            out_path: Optional[str] = None,
            custom_pages: Union[list, int, slice, None] = None,
            delete_keys: Union[tuple, bool, None] = None,
            **kwargs):
    """
    Utility to adds metadata, including bibtex or any custom key,
        to delete selected pages or metadata keys, to join multiple pdfs
    in_path         if list, joins pdfs, keeps only metadata and links for the first.
    out_path        if None, overwrite in_path or in_path[0]
    custom_pages    range to keep: None: all
                        int     single page
                        list    pages in list
                        slice   pages in range (0, None), 
    delete_keys     from pdf.metadata, True deletes all metadata.
    kwargs:         All kwargs get added as pdf metadata
        author
        year
        title
        subject
        bibtex      if bibtex: author, year, title are overwritten
            any
    """
    # validate io paths
    join_paths = []
    if isinstance(in_path, (list, tuple)):
        join_paths = in_path[1:]
        in_path = in_path[0]
        _valid = [_ext_assert(path, ".pdf") for path in join_paths]
    _ext_assert(in_path, ".pdf")
    if out_path is None:
        out_path = in_path
    else:
        os.makedirs(osp.expanduser(osp.abspath(osp.dirname(out_path))), exist_ok=True)
        if osp.splitext(out_path)[-1].lower() != ".pdf":
            out_path += ".pdf"

    # clone first pdf
    reader, writer = _clone(in_path)

    # modify pages, metadata entries, keys
    _remove_pages(writer, custom_pages)
    metadata = _parse_metadata(reader, **kwargs)
    _delete_keys(metadata, delete_keys)
    # add metadata field
    writer.add_metadata(metadata)

    # join pdfs
    for path in join_paths:
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            writer.add_page(page)

    writer.compress_identical_objects()

    with open(out_path, 'wb') as output_file:
        writer.write(output_file)

def _clone(path):
    reader = pypdf.PdfReader(path)
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(reader)
    return reader, writer


def _remove_pages(writer:  pypdf._writer.PdfWriter,
                  pages: Union[None, int, list, tuple, slice] = None) -> None:
    """remove pages not in list, from back to front
    """
    if pages is not None:
        num = len(writer.pages)
        if isinstance(pages, int):
            pages = [pages]
        elif isinstance(pages, tuple):
            pages = list(pages)
        elif isinstance(pages, slice):
            pages = list(range(pages.start or 0, pages.stop or num))
        # allow negative indexing
        _num_pages = len(pages)
        pages = [p%num for p in pages if p < num]
        # only
        if len(pages):
            for i in range(num-1, -1, -1):
                if i not in pages:
                    writer.remove_page(i, clean=True)
        elif _num_pages:
            print(f"Returning all pages, custom pages out of range(0, {num})")
            # should use warning logging, i know


def _parse_bib(bib: str, bib_format: str = 'bibtex'):
    """bib formats bibtex, yaml
        ris, nbib requires plugin install"""
    if osp.isfile(bib):
        return parse_file(bib, bib_format=bib_format)
    return parse_string(bib, bib_format=bib_format)

def _bib_entry_to_dict(record, entry):
    out = {}
    if 'type' in entry .__dict__ and 'fields' in entry.__dict__:
        out = dict(entry.fields.items())
        out.update(record=record, entry_type=entry.type)
        out.update(**_bib_entry_persons(entry))
    return out

def _bib_entry_persons(entry):
    out = {}
    for ptype, names in entry.persons.items():
        out[ptype] = "and ".join([_get_name(n) for n in names])
    return out

def _get_name(names):
    out = ""
    if names.last_names:
        out += " ".join(names.last_names)+", "
    for m in names.first_names:
        out += m
        if m[-1] != ".":
            out += " "
    for m in names.middle_names:
        out += m
        if m[-1] != ".":
            out += " "
    return out

def bib_to_dict(in_bib: str, idx: Optional[int] = 0, bib_format: str = 'bibtex') -> Optional[dict]:
    """ return single bib 
    bib formats bibtex, yaml
        requires plugin install ) ris, """
    if idx is None:
        return bibs_to_dict(in_bib, bib_format)

    bib = _parse_bib(in_bib, bib_format)
    if idx < len(bib.entries):
        record, entry = list(bib.entries.items())[idx]
        if 'title' in entry.fields:
            return _bib_entry_to_dict(record, entry)
    return {}


def bibs_to_dict(in_bib: str, bib_format: str = 'bibtex', key='title') -> Optional[dict]:
    """ return all bibs as a dict of entries {name:{bib etnries}}
    """
    bib = _parse_bib(in_bib, bib_format)
    _msg = ""
    out = {}
    for record, entry in bib.entries.items():
        if 'title' in entry.fields:
            _entry = _bib_entry_to_dict(record, entry)
            item = record if key not in _entry else _entry[key]
            out[item.replace('{', '').replace('}','')] = _entry
    return out


def _import_bib(metadata, bib_format = 'bibtex'):
    bib = _get_bib(metadata)
    if bib is not None:
        bibdic = bib_to_dict(bib, bib_format=bib_format)
        if osp.isfile(bib):
            with open(bib, 'r', encoding='utf8') as fi:
                bib = fi.read()
        metadata["/Bibtex"] = bib

        author = bibdic.get('author')
        if len(author.split(' and ')) > 2:
            author = author.split(' and ')[0] + " et.al."
            author += " " + bibdic.get('year', '')
            metadata['/Author'] = author

        for key in ['title', 'year', 'url', 'code']:
            if key in bibdic:
                metadata[_format_pdf_key(key)] = bibdic[key]

def _get_bib(metadata):
    bib = None
    _keys = ["/Bib", "/Bibtex"]
    bibkey = [key for key in metadata if key in _keys]
    if bibkey:
        bib = metadata.pop(bibkey[0])
    return bib

def _parse_metadata(reader, **kwargs) -> dict:
    # get existing metadata
    metadata = dict(reader.metadata) if reader.metadata is not None else {}
    # cleanup metadata keys
    _format_pdf_keys(kwargs)
    _remove_none_keys(kwargs)
    # read bibtex
    _import_bib(kwargs)
    metadata.update(**kwargs)
    return metadata

def _delete_keys(metadata: dict, keys: Union[str, list, tuple, bool, None] = None):
    """removes unwanted metadata keys"""
    if keys is None:
        return
    if keys is True:
        keys = list(metadata.keys())
    elif isinstance(keys, str):
        keys = [keys]
    for key in keys:
        key = _format_pdf_key(key)
        if key in metadata:
            del metadata[key]

def _format_pdf_key(key):
    if key[0] != '/':
        key =  '/' + key[0].upper()+key[1:]
    return key

def _format_pdf_keys(metadata: dict):
    """pdf metadata expects keys as /Capitalfirstinitial """
    keys = list(metadata.keys())
    for k in keys:
        key = k
        key = _format_pdf_key(k)
        if k != key:
            metadata[key] = metadata.pop(k)

def _remove_none_keys(metadata: dict):
    keys = list(metadata.keys())
    for key in keys:
        if metadata[key] is None:
            metadata.pop(key)

def _ext_assert(path, ext):
    ext = ext.lower()
    assert osp.isfile(path), f"file <{path}> not found"
    assert osp.splitext(path)[-1].lower() == ext, f"invalid extension <{path}>, expects {ext}"


def get_pdf_info(pdf: str, page: Optional[int] = None, verbose: bool = False) -> Optional[dict]:
    """ {'pages':<int>, 'height': <float, int, list>, 'width':<float, int, list>,
         **pdf.metadata}
    Args
        pdf     (str)
        page    (int [None]) page number to get info from / if w and h vary
        verbose (bool [Fales]) if True pprint() and return None

    linux native pdfinfo is more complete, this is for internal use
    """
    assert osp.isfile(pdf)
    with open(pdf, 'rb') as _fi:
        red = pypdf.PdfReader(_fi)
        num = len(red.pages)
        if page is None:
            height = [p.mediabox.height for p in red.pages]
            width = [p.mediabox.width for p in red.pages]
            if len(set(height)) == 1 and len(set(width)) == 1:
                height = height[0]
                width = width[0]
        else:
            height = red.pages[page % num].mediabox.height
            width = red.pages[page % num].mediabox.width
        metadata = dict(red.metadata) if red.metadata is not None else {}
    out = {'pages':num, 'width':width, 'height':height, **metadata}
    if verbose:
        if '/Bibtex' in out:
            bibtex = out.pop('/Bibtex')
            print(f"\n/Bibtex\n{bibtex}")
        pprint(out)
        return None
    return out


def get_pdfs(folder: str, key: Optional[str] = None) -> list:
    """ get pdfs from local folder
    """
    pdfs = [f.path for f in os.scandir(folder) if f.name.endswith(".pdf")]
    if key:
        pdfs = [f for f in pdfs if key in f]
    return pdfs


def split_pdf(pdf: str, outname: Optional[str] = None):
    """ saves one pdf per page
    """
    reader = pypdf.PdfReader(pdf)
    num = len(reader.pages)
    outname = osp.splitext(outname or pdf)[0]
    outname = f"{outname}_%0{len(str(num))}d.pdf"
    for i, page in enumerate(reader.pages):
        writer = pypdf.PdfWriter()
        writer.add_page(page)
        with open(outname%i, 'wb') as output_pdf:
            writer.write(output_pdf)


# def _sizes(size, dpi: Optional[int] = None):
#     out = {
#         'a0': (841, 1189),
#         'a1': (594, 841),
#         'a2': (420, 594),
#         'a3': (297, 420),
#         'a4': (210, 297),
#         'a5': (128, 210),
#         'a6': (105, 148),
#         'ansi a': (216, 297),
#         'letter': (216, 297),
#         'legal' : (216, 356),
#         'ledger': (279, 432),
#         'ansi b': (279, 432),
#         'ansi c': (432, 559),
#         'ansi d': (559, 864),
#         'ansi e': (864, 1118),
#         'arch a': (229, 305),
#         'arch b': (305, 457),
#         'arch c': (457, 610),
#         'arch d': (610, 914),
#         'arch e': (914, 1219)
#     }
#     assert size.lower() in out, f"size name '{size.lower}' not found in {list(out.keys())}"
#     size = out[size.lower()]
#     if dpi is not None:
#         size = [round(size[0]*dpi/25.41), round(size[1]*dpi/25.41)]
    # return size

def convert_page_size(pdf: str,
                      size: Union[tuple, list, str, float, int],
                      outname: Optional[str] = None):
    """
    size A0, --A8,
    outname None, overwrites original.
    """
    reader = pypdf.PdfReader(pdf)
    num = len(reader.pages)
    width = [p.mediabox.width for p in reader.pages]
    height = [p.mediabox.height for p in reader.pages]
    width = np.unique(width)[np.argmin(np.abs(np.unique(width) - np.mean(width)))]
    height = np.unique(height)[np.argmin(np.abs(np.unique(height) - np.mean(height)))]

    if isinstance(size, (float, int)):
        size = (round(size*width), round(size*float))
    if isinstance(size, str):
        # size = _sizes(size, dpi)
        size = tuple(pypdf.PaperSize.__dict__[size])
    assert isinstance(size, (tuple, list)) and len(size) == 2, f"invalid size spec '{size}', tuple in mm reqd."
    size = list(size)
    if width > height:
        size = size[::-1]

    writer = pypdf.PdfWriter()
    for i, page in enumerate(reader.pages):
        page.scale_by(size[0]/width)
        writer.add_page(page)

    with open(outname, 'wb') as output:
        writer.write(output)

##
# pdf manipulations sketchbook
#
def rotate(pdf: str,
           outname: Optional[str] = None,
           angle: int = 90,
           pages: Union[list, tuple, int, None] = None):
    """ rotate multiples of 90
    outname None, overwrites original.
    """
    assert angle % 90, f'multiples of 90, clockwise, got {angle}'
    reader = pypdf.PdfReader(pdf)
    writer = pypdf.PdfWriter()
    if isinstance(pages, tuple):
        pages = list(pages)
    elif isinstance(pages, int):
        pages = [pages]
    for i, page in enumerate(reader.pages):
        if pages is None or i in pages:
            writer.add_page(page.rotate(90))
        else:
            writer.add_page(page)
    with open(outname, 'wb') as output:
        writer.write(output)


def _getmeanpage(reader):
    w, h = np.stack([np.array(reader.pages[i].mediabox[2:]) for i in range(len(reader.pages))]).T
    if len(np.unique(w)) > 1:
        w_ = w[np.abs(w - w.mean()) < w.std()]
        w_mean = w_.mean() if len(np.unique(w_)) > 1 else w_[0]
    else:
        w_mean = w[0]
    if len(np.unique(h)) > 1:
        h_ = w[np.abs(h - h.mean()) < h.std()]
        h_mean = h_.mean() if len(np.unique(h_)) > 1 else h_[0]
    else:
        h_mean = h[0]
    return w_mean, h_mean

def _add_suffix(suffix, fname):
    return fname.replace('.',f'{suffix}.')

def _write_pdf(wr, fname, suffix=''):
    with open(_add_suffix(suffix, fname) , 'wb') as fi:
        wr.write(fi)

# pylint: disable=no-member
def doublepage(input_path, suffix='_2page', edge=0):
    """ converts to 2 page view

    """
    reader = pypdf.PdfReader(input_path)
    num = len(reader.pages)
    w,h = _getmeanpage(reader)
    if not edge:
        w_t = float(w)
        h_t = 0
        w = pypdf.generic._base.FloatObject(float(w*2))
    else:
        w_t = 0
        h_t = float(h)
        h = pypdf.generic._base.FloatObject(float(h*2))
    writer = pypdf.PdfWriter()
    for i, page in enumerate(reader.pages):
        if not i%2:
            p = writer.add_blank_page(w, h)
            writer.pages[-1].merge_page(reader.pages[i])
            if i < num -1:
                writer.pages[-1].merge_translated_page(reader.pages[i+1],
                                                       w_t, h_t, over=True,
                                                       expand=True)
    _write_pdf(writer, input_path, suffix)
