"""@xvdp
pdf utilities

# .pdf utility functions:
    pdf_mod() # add metadata, bibtex, url, author ...modify page range

# entry point to 
    __main__.pdf_bibtex / pdfbib
    __main__.pdf_metadata / pdfmeta 
    TODO replace all by pdfmeta -should

# non metadata & links preserving
    
    split_pdf()     # create one pdf per page
    rotate()        # rotate all pages in a pdf
    doublepage()    # joins pages side to side for 2 page view
    convert_page_size() # scale sizes

make_pdf()  Make pdf from multiple pdfs or img files, include metadata
    # Does not:
        preserve pdfs internal links if existing
.bib utilities
    reformat_bib() converts bib using "" to {}
    
"""
from typing import Optional, Union, Any, Tuple
import os
import os.path as osp
import re
from pprint import pprint
import numpy as np
import pypdf
from pypdf import PdfReader, PdfWriter
from pybtex.database import parse_file, parse_string
from PIL import Image

FloatType = Union[float, np.float64]


def pdf_mod(in_path: Union[str, list, tuple],
            out_path: Optional[str] = None,
            custom_pages: Union[list, int, slice, None] = None,
            delete_keys: Union[tuple, bool, None] = None,
            **kwargs) -> None:
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
        require     required keys for bibtex to be imported, e.g. 'title'
        size        tuple or str:
                        "common":   resize to most common page size 
                        "mean":     resize to mean page 
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
    writer.add_metadata(metadata)


    # join pdfs
    for path in join_paths:
        reader = PdfReader(path)
        for page in reader.pages:
            writer.add_page(page)

    # resize pages
    resize = kwargs.get("size", None)
    if resize is not None:
        newsize, vary = _get_resize_params(writer, resize)
        _resize_pdf_pages(writer, newsize, vary)

    writer.compress_identical_objects()

    with open(out_path, 'wb') as output_file:
        writer.write(output_file)

def _resize_pdf_pages(writer, size, checkall):
    """ """
    if size is not None:
        for _, page in enumerate(writer.pages):
            _size = _get_page_size(page)
            if _size[0] == size[0] and _size[1] == size[1]:
                if not checkall:
                    continue
            else:
                page.scale(size[0]/_size[0], size[1]/_size[1])


def _get_resize_params(reader, size) -> tuple:
    _presets =  [k for k in pypdf.PaperSize.__dict__ if k[0] != "_"]
    sizes = get_page_sizes(reader)
    vary = "mean" in sizes
    if isinstance(size, str):
        if size == "common":
            size = sizes["size"]
        elif size == "mean":
            size = sizes["size"] if not vary else sizes[size]
        elif size[0] != "__" and size in _presets:
            size = tuple(pypdf.PaperSize.__dict__[size])

    assert size is None or isinstance(size, (tuple, np.ndarray, list)) and len(size)==2, \
        f"size: expects, tuple (number, number) | str in {['size', 'common']+_presets}, got {size}"
    return size, vary


def _clone(path: str) -> Tuple[PdfReader, PdfWriter]:
    reader = PdfReader(path)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    return reader, writer


def _remove_pages(writer: PdfWriter,
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


def _parse_bib(bib: str, bib_format: str = 'bibtex') -> Any:
    """bib formats bibtex, yaml
        ris, nbib requires plugin install"""
    if osp.isfile(bib):
        return parse_file(bib, bib_format=bib_format).lower()
    return parse_string(bib, bib_format=bib_format).lower()

def _bib_entry_to_dict(record, entry) -> dict:
    out = {}
    if 'type' in entry .__dict__ and 'fields' in entry.__dict__:
        out = dict(entry.fields.items())
        out.update(record=record, entry_type=entry.type)
        out.update(**_bib_entry_persons(entry))
    return out

def _bib_entry_persons(entry) -> dict:
    out = {}
    for ptype, names in entry.persons.items():
        out[ptype] = "and ".join([_get_name(n) for n in names])
    return out

def _get_name(names) -> str:
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
    out = {}
    if idx is None:
        out = bibs_to_dict(in_bib, bib_format)
    else:
        bib = _parse_bib(in_bib, bib_format)
        if idx < len(bib.entries):
            record, entry = list(bib.entries.items())[idx]
            out = _bib_entry_to_dict(record, entry)
    return out


def bibs_to_dict(in_bib: str, bib_format: str = 'bibtex', key: str = 'title') -> Optional[dict]:
    """ return all bibs as a dict of entries {<key arg>:{bib entries}}
    """
    bib = _parse_bib(in_bib, bib_format)
    out = {}
    for record, entry in bib.entries.items():
        _entry = _bib_entry_to_dict(record, entry)
        item = record if key not in _entry else _entry[key]
        out[item.replace('{', '').replace('}','')] = _entry
    return out


def _format_bib(bib: str):
    def _bib_brackets(match):
        return f'{match.group(1)}{{{match.group(2)}}}'
    def _bib_lowercase(match):
        return match.group(1) + match.group(2).lower() + "{"

    _quotes =  r'(\n\s*[^=]+=\s*)"(.*?)"'
    _upper = r'(^|\n)(.*?)\{'
    bib = re.sub(_quotes, _bib_brackets, bib)
    return re.sub(_upper, _bib_lowercase, bib)


def format_bib(bib: str) -> str:
    '''replace "<value>", with, {<value>}, in
        .bib files or bibtext str
    '''
    if osp.isfile(bib):
        bibname = bib
        with open(bib, 'r', encoding='utf8') as fi:
            bib = _format_bib(fi.read())
        with open(bibname, 'w', encoding='utf8') as fi:
            fi.write(bib)
    else:
        bib = _format_bib(bib)
    return bib


def _import_bib(metadata: dict,
                bib_format: str = 'bibtex',
                require: Union[list, tuple, str, None] = None) -> None:
    bib = _get_bib(metadata)
    if bib is not None:
        bibdic = bib_to_dict(bib, bib_format=bib_format)
        if osp.isfile(bib):
            with open(bib, 'r', encoding='utf8') as fi:
                bib = fi.read()

        if require is not None:
            if isinstance(require, str):
                require = [require]
            for key in require:
                if bibdic.get(key, None) is None:
                    print(f'required key {key} missing in {bibdic}, bibtex not added')
                    return
        # bib = re.sub(r'(\n[^=]+=)"(.*?)"', _bib_brackets, bib)
        # bib = re.sub(r'(^|\n)(.*?)\{', _bib_lowercase, bib)

        metadata["/Bibtex"] = _format_bib(bib)
        author = bibdic.get('author')

        if author is not None and len(author.split(' and ')) > 2:
            author = author.split(' and ')[0] + " et.al."
            author += " " + bibdic.get('year', '')
            metadata['/Author'] = author

        for key in ['title', 'year', 'url', 'code']:
            if key in bibdic:
                metadata[_format_pdf_key(key)] = bibdic[key]


def _get_bib(metadata: dict) -> dict:
    bib = None
    _keys = ["/Bib", "/Bibtex"]
    bibkey = [key for key in metadata if key in _keys]
    if bibkey:
        bib = metadata.pop(bibkey[0])
    return bib


def _parse_metadata(reader: PdfReader, **kwargs) -> dict:
    # get existing metadata
    metadata = dict(reader.metadata) if reader.metadata is not None else {}
    return _collect_metadata(metadata=metadata, **kwargs)


def _collect_metadata(**kwargs):
    metadata = kwargs.pop('metadata', {})
    # cleanup metadata keys
    _format_pdf_keys(kwargs)
    _remove_none_keys(kwargs)
    # read bibtex
    _import_bib(kwargs)
    metadata.update(**kwargs)
    if "/Author" in metadata:
        if isinstance(metadata["/Author"], list):
            metadata["/Author"] = ", ".join(metadata["/Author"])
    for k, v in metadata.items():
        if (k in "/Title" or k in "/Author" )and ("}" in v or "{" in v):
            metadata[k] = v.replace("}", "").replace("{", "")
    return metadata


def _delete_keys(metadata: dict, keys: Union[str, list, tuple, bool, None] = None) -> None:
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


def _format_pdf_key(key: str) -> str:
    if key[0] != '/':
        key =  '/' + key[0].upper()+key[1:]
    return key


def _format_pdf_keys(metadata: dict) -> None:
    """pdf metadata expects keys as /Capitalfirstinitial """
    keys = list(metadata.keys())
    for k in keys:
        key = k
        key = _format_pdf_key(k)
        if k != key:
            metadata[key] = metadata.pop(k)


def _remove_none_keys(metadata: dict) -> None:
    keys = list(metadata.keys())
    for key in keys:
        if metadata[key] is None:
            metadata.pop(key)


def _ext_assert(path: str, ext: str) -> None:
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

    TODO: internalize  for special cases,
    native pdfinfo is more complete
    """
    assert osp.isfile(pdf)
    with open(pdf, 'rb') as _fi:
        red = PdfReader(_fi)
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


def split_pdf(pdf: str, outname: Optional[str] = None) -> None:
    """ saves one pdf per page
    """
    reader = PdfReader(pdf)
    num = len(reader.pages)
    outname = osp.splitext(outname or pdf)[0]
    outname = f"{outname}_%0{len(str(num))}d.pdf"
    for i, page in enumerate(reader.pages):
        writer = PdfWriter()
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
                      outname: Optional[str] = None) -> None:
    """
    size A0, --A8,
    outname None, overwrites original.
    TODO use _clone and test , scaleby should work
    """
    reader = PdfReader(pdf)
    # num = len(reader.pages)
    width = [p.mediabox.width for p in reader.pages]
    height = [p.mediabox.height for p in reader.pages]
    width = np.unique(width)[np.argmin(np.abs(np.unique(width) - np.mean(width)))]
    height = np.unique(height)[np.argmin(np.abs(np.unique(height) - np.mean(height)))]
    _Sz = pypdf.PaperSize.__dict__

    if isinstance(size, (float, int)):
        size = (round(size*width), round(size*float))
    elif isinstance(size, str):
        assert size in _Sz, f"invalid size {size}, {[k for k in _Sz if k[0] != '_']}"
        size = tuple(_Sz[size])
    assert isinstance(size, (tuple, list)) and len(size) == 2, \
            f"invalid size spec '{size}', tuple in mm reqd."
    size = list(size)
    if width > height:
        size = size[::-1]

    writer = PdfWriter()
    for _, page in enumerate(reader.pages):
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
           pages: Union[list, tuple, int, None] = None) -> None:
    """ rotate multiples of 90
    outname None, overwrites original.
    """
    assert angle % 90, f'multiples of 90, clockwise, got {angle}'
    reader = PdfReader(pdf)
    writer = PdfWriter()
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

def get_page_sizes(pdf: Union[PdfReader, str], verbose: bool = False) -> dict:
    """ get statistics for page sizes of unevenly sized pages
        pdf: filename or reader
        verbose: pretty print stats
        >>> get_page_sizes("mypdffile.pdf", verbose=Treu)
    """
    if isinstance(pdf, str):
        pdf = PdfReader(pdf)
    wh = np.stack([np.array(pdf.pages[i].mediabox[2:]) for i in range(len(pdf.pages))])
    page_sizes = _page_size_stats(wh)
    if verbose:
        pprint(page_sizes)
    return page_sizes

def _page_size_stats(wh) -> dict:
    """ returns {
            'size'      : tuple, most common page size
            'page_count':   -> int, if all pages are the same
        # if more than one page size found
            'page_count':   -> {tuple: int, ...}
            'size_perc':    -> % of most common size
            # excluding outliers
            'mean':         -> mean of page sizes, tuple
            'size_diff':    -> abs(size - mean), tuple
    }
    """
    out = {}
    # if all pages are the same
    if np.all(wh == wh[0]):
        out['size'] = wh[0]
        out['page_count'] = len(wh)
    else:
        pairs, counts = np.unique(wh, axis=0, return_counts=True)
        out['size'] = pairs[np.argmax(counts)]
        out['mean'] = np.mean(wh, axis=0)
        out['page_count']  = {tuple(pair): count for pair, count in zip(pairs, counts)}
        out['size_perc'] = 100 * counts[np.argmax(counts)]/len(wh)
        std = np.std(wh, axis=0)

        if np.max(counts) / len(wh) <= 0.5: # mean excluding outliers using zscore
            z_treshold = 1.5
            excluded = 0
            while excluded < 0.5: # at least 50%
                std = np.std(wh, axis=0)
                if np.any(std == 0):
                    break
                mask = np.abs(wh - np.mean(wh, axis=0))/std < z_treshold
                mask = mask[:, 0] & mask[:, 1]
                excluded = np.sum(mask) / len(mask)
                z_treshold += 0.5
                out['mean'] = np.mean(wh[mask], axis=0)
                std = np.std(wh[mask], axis=0)
        out['size_diff'] = np.abs(out['size']  - out['mean'])
    return out

def _getmeanpage(reader: PdfReader) -> Tuple[FloatType, FloatType]:
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

def _add_suffix(suffix: str, fname: str) -> str:
    return fname.replace('.',f'{suffix}.')

def _write_pdf(wr: PdfWriter, fname: str, suffix: str = '') -> None:
    with open(_add_suffix(suffix, fname) , 'wb') as fi:
        wr.write(fi)

# pylint: disable=no-member
def doublepage(input_path: str, suffix: str = '_2page', edge: int = 0) -> None:
    """ converts to 2 page view
    """
    reader = PdfReader(input_path)
    num = len(reader.pages)
    w,h = _getmeanpage(reader)
    if not edge:
        w_t = float(w)
        h_t = 0
        w = pypdf.generic.FloatObject(float(w*2))
    else:
        w_t = 0
        h_t = float(h)
        h = pypdf.generic.FloatObject(float(h*2))
    writer = PdfWriter()
    for i, _ in enumerate(reader.pages):
        if not i%2:
            writer.add_blank_page(w, h)
            writer.pages[-1].merge_page(reader.pages[i])
            if i < num -1:
                writer.pages[-1].merge_translated_page(reader.pages[i+1],
                                                       w_t, h_t, over=True,
                                                       expand=True)
    _write_pdf(writer, input_path, suffix)


def _get_files(path: Union[str, tuple, list, None] = None,
                  sort_order: Optional[str] = None,
                  exts: Union[tuple, list] = ('.pdf', '.jpg','.jpeg', '.png')) -> list:
    """
    sort_order:     None, getctime, getmtime, getsize
    """
    if path is None:
        path = os.getcwd()

    if isinstance(path, str):
        assert osp.isdir(path), f'path {path} not a folder'
        path = osp.expanduser(osp.abspath(path))
        path = [f.path for f in os.scandir(path)
                if osp.splitext(f.name)[-1].lower() in exts]
        kw = {"key": lambda x:  getattr(osp, sort_order)(x)} if isinstance(sort_order, str) else {}
        path = sorted(path, **kw)
    elif isinstance(path, (list, tuple)):
        path = [osp.expanduser(osp.abspath(p)) for p in path]
        for p in path:
            assert osp.isfile(p), f"{p} is not a valid file"
            _ext = osp.splitext(p)[-1]
            assert _ext.lower() in exts, f"file {p} has invalid ext, expected {exts}"
    assert isinstance(path, (list, tuple)), f"expected list of files, found type {type(path)}"
    return path


def make_pdf(path: Union[str, tuple, list, None] = None,
             out_path: Optional[str] = None,
             sort_order: Optional[str] = None,
             size: Union[tuple, list, str, bool] = False,
             **kwargs):
    """ Make pdf from multiple pdfs or img files, include metadata
    # Does not:
        preserve pdfs internal links if existing
    
    path        None:           current path
                str:            folder
                list | tuple:   files/  pdfs jpgs, pngs
    out_path    None:   folder name
    sort_order  None:   if input path is not a list, alphabetical
                str:    getctime, getmtime
    size        bool        True    resizes to first page
                str         A0-A7, C4 from  pypdf.PaperSize.__dict__
                list, tuple (with, height)
    kwargs
        url, author, year, bibtex, 
    """
    exts = ['.pdf', '.jpg','.jpeg', '.png']
    paths = _get_files(path, sort_order, exts)
    if not paths:
        print('no valid files found, exiting ...')
        return

    if out_path is None:
        out_path = f"{osp.split(paths[0])[0]}.pdf"
    else:
        out_path = osp.expanduser(osp.abspath(out_path))
    assert not osp.isfile(out_path), f"file conflict, {out_path} exists, nothing done."

    if size:
        if isinstance(size, str):
            _sizes = [k for k in pypdf.PaperSize.__dict__ if k[0] != "_"]
            assert size in _sizes, f"requested size {size} not in {_sizes}"
            size = list(pypdf.PaperSize.__dict__['A4']) # pypdf is W H
        if isinstance(size, tuple):
            size = list(size)
        assert isinstance(size, (list, bool)), f"invalid size spec type {type(size)}, {size}"


    writer = PdfWriter()
    for i, path in enumerate(paths):
        _tmppdf = None
        if osp.splitext(path)[-1].lower() != '.pdf':
            im = Image.open(path)
            _tmppdf = "__".join([osp.splitext(path)[0], '.pdf'])
            im.save(_tmppdf,'PDF', resolution=100)
            path = _tmppdf
        reader = PdfReader(path)
        for _, page in enumerate(reader.pages):
            page = _resize_pdf_page(page, size)
            writer.add_page(page)
        if _tmppdf:
            os.remove(_tmppdf)

    metadata = _collect_metadata(metadata={}, **kwargs)
    if metadata:
        writer.add_metadata(metadata)
    _write_pdf(writer, out_path)


def _resize_im(im, size):
    if size:
        _size = list(im.size)
        if size is True:
            size = _size
        elif size != _size:
            scaleby = min(size[0]/_size[0],  size[1]/_size[1])
            im = im.resize((round(_size[0]*scaleby), round(_size[1]*scaleby)))
    return im, size

def _get_page_size(page):
    return page['/MediaBox'][-2:]

def _resize_pdf_page(page, size):
    if size:
        _size = page['/MediaBox'][-2:]
        if size is True:
            size = _size
        elif size[0] != _size[0] and size[1] != _size[1]:
            scaleby = min(size[0]/_size[0],  size[1]/_size[1])
            page.scale_by(scaleby)
    return page


def reformat_bib(fname):
    """ swap quotations for brackets in .bib
    """
    assert fname.lower().endswith('.bib') or fname.lower().endswith('.bibtex'),\
          ".bib file expected, got  {fname}"
    out = []

    with open(fname, 'r', encoding='utf8') as fi:
        lines = fi.read().split('\n')
    for i, line in enumerate(lines):
        if not line:
            continue
        key = ''
        if "=" in line:
            key, line = line.split("=")
            key = "    " + key + " = "
        line = line.strip()
        if line[0] == '"':
            line = '{'+ line[1:]
        line = re.sub(r'(?<!\\)"', '}', line)
        out.append(key+line)
    with open(fname, 'w', encoding='utf8') as fi:
        fi.write("\n".join(out))
    return out
