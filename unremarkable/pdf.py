"""@xvdp
pdf utilities
"""
from typing import Optional, Union
import os
import os.path as osp
from pprint import pprint
import numpy as np
import pypdf
from pypdf.generic import PdfObject, NameObject, DictionaryObject
from pybtex.database import parse_file, parse_string


def _clone(path):
    reader = pypdf.PdfReader(path)
    writer = pypdf.PdfWriter()
    writer.clone_document_from_reader(reader)
    return reader, writer

def _remove_pages(writer, fro=0, to=None, custom_pages=None):
    """to, fro | or custom_pages, not both"""
    if isinstance(custom_pages, slice):
        fro = custom_pages.start
        to = custom_pages.stop
    elif isinstance(custom_pages, int):
        fro = custom_pages
        to = custom_pages + 1
    elif isinstance(custom_pages, list):
        custom_pages.sort()
        num_pages = len(writer.pages)
        j = 0
        for i in range(num_pages):
            if i not in custom_pages:
                del writer.pages[j]
            else:
                j +=1
        return
    if to is not None:
        to = -to % len(writer.pages)
        while to:
            del writer.pages[-1]
            to -= 1
    fro = fro%len(writer.pages)
    while fro:
        del writer.pages[0]
        fro -=1

def _parse_bib(metadata):
    bib = _get_bib(metadata)
    if bib is not None:
        if osp.isfile(bib):
            bib = parse_file(bib)
        else:
            bib = parse_string(bib, bib_format='bibtex')

        metadata["/Bibtex"] = bib.to_string('bibtex')
        nbentries = len(bib.entries.values())
        assert nbentries == 1, f"expected 1 bib entry, got {nbentries}"

        authors = []
        for entry in bib.entries.values():
            for author in entry.persons['author']:
                fn = ".".join([f[0] for f in author.first_names])
                ln = " ".join([f for f in author.last_names])
                authors.append(f"{fn}. {ln}")
            year = entry.fields.get('year', '')
            title = entry.fields.get('title', None)
            authors = ', '.join(authors)
            url = entry.fields.get('url', '')
            code = entry.fields.get('code', '')
            if year:
                authors = ' '.join([authors, year])
        if authors:
            metadata['/Author'] = authors
        if title:
            metadata['/Title'] = title
        if year:
            metadata['/Year'] = year
        if url:
            metadata['/Url'] = url
        if code:
            metadata['/Code'] = code

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
    _parse_bib(kwargs)
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
        key =  '/' + key
    return key[0]+key[1].upper()+key[2:]

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

def pdf_mod(in_path: Union[str, list, tuple],
            out_path: Optional[str] = None,
            fro: int = 0,
            to: Optional[int] = None,
            custom_pages: Union[list, int, slice, None] = None,
            delete_keys: Union[tuple, bool, None] = None,
            **kwargs):
    """
    Utility to adds metadata, including bibtex or any custom key,
        to delete selected pages or metadata keys, to join multiple pdfs
    in_path         if list, joins pdfs, keeps only metadata and links for the first.
    out_path        if None, overwrite in_path or in_path[0]
    fro, to         page range to keep   
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
    _remove_pages(writer, fro, to, custom_pages)
    metadata = _parse_metadata(reader, **kwargs)
    _delete_keys(metadata, delete_keys)
    # add metadata field
    writer.add_metadata(metadata)

    # join pdfs
    for path in join_paths:
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            writer.add_page(page)

    with open(out_path, 'wb') as output_file:
        writer.write(output_file)


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
                      outname: str,
                      size: Union[tuple, list, str, float, int],):

    """
    size A0, --A8,
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
