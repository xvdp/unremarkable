"""@xvdp
pdf utilities
"""
from typing import Optional, Union
import os
import os.path as osp
from pprint import pprint
import pypdf
from pybtex.database import parse_file, parse_string

# rewrite pdfs with metadata , locally
def add_pdf_metadata(pdf: str,
                     author: Optional[str] = None,
                     title: Optional[str] = None,
                     year: Union[str, int, None] = None,
                     subject: Optional[str] = None,
                     keywords: Optional[str] = None,
                     suffix: Union[bool, str] = False,
                     delete_keys: Union[tuple, bool, None] = None,
                     custom_pages: Union[int, tuple, list, range, slice, None] = None,
                     bibtex: Optional[str] = None,
                     bib_format: str = 'bibtex',
                     **kwargs):
    """
    Args
        pdf:         (str) valid pdf
        author:      (str) author list
    Optional Args
        title        (str)
        year         (int, str)
        keywords     (str)
        suffix       (str, bool[False]) # if True add '_mod', if str '_{suffix}'
        delete_keys  (str, tuple, bool) delete unwanted keys if found 
        custom_pages (int, tuple, range, slice)
        bibtex       (str) bibtex file, or bibtex string
        bib_format   (str ['bibtex']) if bibtex passed as string, spec format
    kwargs: 
        any custom metadata keys 

    Example:
    # add only custom metadata keys: will be saved as
    >>> metadata = {'Species': 'Extra-Terrestrial', # -> '/Species'
                    'Reference': '8dc72c41-b276-403b-81ff' # -> '/Reference'
                    }
    >>> add_pdf_metadata(filename, author=None, **metadata)

    # delete some existing metadata
    >>> delete_keys =['/CreationDate', '/Producer']
    >>> add_pdf_metadata(filename, delete_keys=delete_keys)

    # remove first pages and save new file with suffix 
    >>> for f in pdf_folder:
    >>>     pages = get_pdf_info(pdfs[0])['pages']
    >>>     add_pdf_metadata(f, custom_pages=range(1,pages), suffix="nocover")

    # add bibtex to custom data
    >>> for f in pdf_folder:
    >>>     add_pdf_metadata(filename.pdf, bibtex=filename.bib)
    # see bibtext
    $ pdfinfo filename.pdf -custom

    """
    if not any([author, title, year, subject, keywords, delete_keys, custom_pages, bibtex, kwargs]):
        print("no args passed, exiting")
        return None
    assert osp.isfile(pdf), f"file not found {pdf}"

    reader = pypdf.PdfReader(pdf)
    writer = pypdf.PdfWriter()
    metadata = dict(reader.metadata) if reader.metadata is not None else {}

    # add standard keys
    if year is not None and author is not None:
        author = f"{author}, {year}"
    add_keys = {'/Author': author, "/Title": title, '/Subject': subject, '/Keywords': keywords}
    add_keys = {k:v for k,v in add_keys.items() if v is not None}

    # add custom keys from kwargs
    for key, val in kwargs.items():
        _key = f"/{key}"
        add_keys[_key] = kwargs[key]
    for key, val in add_keys.items():
        metadata[key] = val

    if isinstance (bibtex, str):
        if osp.isfile(bibtex):
            bibtex = parse_file(bibtex).to_string('bibtex')
        else:
            bibtex = parse_string(bibtex, bib_format=bib_format).to_string('bibtex')
        print(bibtex)
        metadata['/Bibtex'] = bibtex

    # delete
    if delete_keys is not None:
        if delete_keys is True:
            delete_keys = [k for k in metadata.keys() if k not in add_keys]
        elif isinstance(delete_keys, str):
            delete_keys = [delete_keys]
        for key in delete_keys:
            if key in metadata:
                del metadata[key]

    # add metadata field
    writer.add_metadata(metadata)

    # copy pages
    if custom_pages is None:
        custom_pages = range(len(reader.pages))
    elif isinstance(custom_pages, int):
        custom_pages = (custom_pages,)
    elif isinstance(custom_pages, slice):
        custom_pages = range(len(reader.pages))[custom_pages]
    for i, page in enumerate(reader.pages):
        if i in custom_pages:
            writer.add_page(page)

    if suffix:
        if isinstance(suffix, str):
            suffix = suffix if suffix[0] == "_" else f"_{suffix}"
        else:
            suffix = "_mod"
        out_pdf = suffix.join(osp.splitext(pdf))
    else:
        out_pdf = pdf

    with open(out_pdf, 'wb') as output_pdf:
        writer.write(output_pdf)
        print(f"Writing file {out_pdf}")

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
        pprint(out)
        print(f"\n/Bibtex\n{bibtex}")
        return None
    return out


def get_pdfs(folder: str, key: Optional[str] = None) -> list:
    """ get pdfs from local folder
    """
    pdfs = [f.path for f in os.scandir(folder) if f.name.endswith(".pdf")]
    if key:
        pdfs = [f for f in pdfs if key in f]
    return pdfs
