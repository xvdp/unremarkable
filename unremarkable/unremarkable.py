"""
uploads pdfs to reMarkable tablet
ENTRY POINTS:

$ pdf_to_remarkable path/to/file.pdf ["remarkable folder name"] ["file visible name"]
$ backup_remarkable [path/to/backup/folder]

TODO:
* export folder structure tuple dicts folder:{uuid:uuid, name:uuid, ..., subfolder:{}}
* test: inverse functions: get_uuid_from_name(name) -> get_folder_name(id), ensure it is folder
* test: after uploading pdf, content, metadata, check that they are there.
"""
from typing import Optional
import os
import os.path as osp
import subprocess as sp
import tempfile
import uuid
import json
import pypdf
from .annotations import remarkable_rm_to_svg, remarkable_rm_to_pdf

##
# config
#
def get_host_user_path(host: str = '10.11.99.1',
                       user: str = 'root',
                       path: str = '.local/share/remarkable/xochitl') -> tuple:
    """ default user and folder as of version 3.5.2.1807
    Args
        host    (str ['10.11.99.1']) change if running thru wifi
        user    (str ['root']) remarkable default
        path    (str [ '.local/share/remarkable/xochitl'])) remarkable default
    """
    return host, user, path

def _kwargs_get(items=('host', 'user', 'path'), **kwargs):
    return {k:v for k,v in kwargs.items() if k in items}


def _is_host_reachable(ip='10.11.99.1', packets=5) -> bool:
    command = ['ping', '-w', str(packets), ip]
    try:
        sp.run(command, stdout=sp.DEVNULL, stderr=sp.DEVNULL, check=True)
        return True
    except sp.CalledProcessError:
        return False


##
# Main upload process
#
def upload_pdf(pdf: str,
               folder: str = "",
               visible_name: Optional[str] = None,
               restart: bool = True,
               **kwargs) -> None:
    """ remarkable pdf upload requires min 3 filesn w/o which it won't show pdf
            <uuid>.pdf
            <uuid>.content: pageCount, sizeInBytes, Optional[orientation]
            <uuid>.metadata: visibleName, parent (uuid folder), Optional[lastModified]
        locally it creates other files, .pagedata, .local and a folder
    Args
        pdf             (str) name of valid pdf file to upload, or *
        folder          (str ['']) destination folder name, existing only, default ""
        visible_name    (str [None]) if none, file will be uploaded as pdf basename
        restart         (bool [True]) restarts xochitl service to scan folders
    kwargs:
        host    (str ['10.11.99.1']) remarkable usbc port, change if using wifi
        user    (str ['root']) remarkable default
        path    (str [ '.local/share/remarkable/xochitl])) remarkable default
    """
    # TODO also allow epub
    _kw = _kwargs_get(**kwargs)
    host, user, path = get_host_user_path(**_kw)
    if not _is_host_reachable(host, packets=2):
        print (f"host <{host}> is not reachable")
        return None

    if osp.basename(pdf) == "*":
        pdfs = [f.path for f in os.scandir(osp.dirname(pdf) or None)
                if f.name.lower().endswith(".pdf")]
        if pdfs:
            print(f"Uploading {len(pdfs)} files to reMarkable")
            for pdf in pdfs:
                upload_pdf(pdf, folder, visible_name, False, **kwargs)
            if restart:
                _restart_xochitl(**kwargs)
        else:
            print(f"No pdfs found in {osp.abspath(osp.expanduser(osp.dirname(pdf)))}")
    else:

        assert osp.isfile(pdf) and pdf.lower().endswith(".pdf"), f"pdf expected {pdf}, not found"

        # generate new file name uuid
        uuids = list_remote(**_kw)
        uid = gen_uuid(uuids)

        # find uuid of folder, if not found use MyFiles
        uuidfolder = folder
        if folder:
            uuidfolder = get_uuid_from_name(folder,  target_type = "CollectionType", **_kw)
            uuidfolder = uuidfolder or ""
            if uuidfolder == "":
                print(f"folder <{folder}> not found, uploading to 'MyFiles'")

        # image visible name from pdf name
        if visible_name is None:
            visible_name = osp.basename(osp.splitext(pdf)[0])
            visible_name = visible_name.replace('_', ' ')

        # create .content and .metadata files
        content = make_content(pdf)
        metadata = make_metadata(pdf, visible_name, uuidfolder)

        # uploads uuid fullname
        name = osp.join(path, uid)
        # upload pdf and if success, write json files
        print(f"Uploading\n\t{osp.basename(pdf)}\n\t as '{folder}/{visible_name}'\n\t uuid {uid}")
        ret = _rsync_pdf(pdf, name, **_kw)
        if not ret:
            ssh_json(content, f"{name}.content", **_kw)
            ssh_json(metadata, f"{name}.metadata", **_kw)

        # check files were uploaded
        uploads = [f for f in list_remote(None, keep_ext=True, **_kw) if uid in f]
        if uploads:
            uploads = '\n\t'.join(uploads)
            print(f"files uploaded \n\t{uploads}")
        else:
            print("no files uploaded")

        # rescan the folder structure
        if restart:
            _restart_xochitl(**kwargs)

def _restart_xochitl(**kwargs) -> int:
    """ serivce is restarted on reboot
    """
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    cmd = ['ssh', f'{user}@{host}', 'systemctl', 'restart', 'xochitl.service']
    return _run_cmd(cmd, check=True, shell=False)


def _rsync_pdf(pdf: str,
               name: str,
               **kwargs) -> int:
    """ functional for main pdf upload"""
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    if not _is_host_reachable(host, packets=2):
        print (f"host <{host}> is not reachable")
        return 1

    name = f'{name}.pdf'
    cmd = ['rsync',
           '-avzhP',   # archive, verbose, compress, human-readable, partial, progress
           '--update',  # Skip files that are newer on the receiver
           pdf, f'{user}@{host}:{name}']
    return _run_cmd(cmd, check=True, shell=False)


def gen_uuid(uuids=()):
    """generate uuid ensuring uniqueness in set"""
    uid = str(uuid.uuid4())
    if uid in uuids:
        uid = gen_uuid(uuids)
    return uid

def list_remote(ext: Optional[str] = '.pdf', **kwargs) -> Optional[list]:
    """ return basenames of existing pdf files in reMarkable
    """
    keep_ext = kwargs.get('keep_ext', False)
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    if not _is_host_reachable(host, packets=2):
        print (f"host <{host}> is not reachable")
        return None
    path = path if ext is None else osp.join(path, f"*{ext}")
    # cmd = f'ssh {user}@{host} ls {path}'      # shell=True
    cmd = ['ssh', f'{user}@{host}', 'ls', path] # simple list cmd -> shell=False

    result = sp.run(cmd, shell=False,   # shell=False, prevent injections
                    stdout=sp.PIPE, stderr=sp.PIPE,
                    text=True,          # text=True, return ascii
                    check=False)        # check=False, failure tolerant
    out = None
    if result.returncode == 0:
        out = result.stdout.split("\n")[:-1]
        if len(out) == 1 and not out[0]:
            out = []
        out = [osp.basename(o) for o in out]
        if not keep_ext:
            out = [osp.splitext(o)[0] for o in out]
    else:
        print(f"Cannot Access {user}@{host}, check connection, error: {result.stderr}")
    return out

def _is_uuid(name: str):
    try:
        uuid.UUID(name)
        return True
    except ValueError:
        return False


def get_parent(name: str, folder: str = '.') -> tuple:
    """ return parent to a file, given uuid or name
    Args:
        name    (str) vaild uuid in xochitl hierarchy or visible name in said hierary
        folder  (str ['.'])  arg ignored if name is file fullname
    """
    parentname = parentuuid = None
    _folder, _name = osp.split(name)
    if osp.isfile(name) and _folder:
        folder = _folder
    _name, _ext = osp.splitext(_name)
    uuidname = _name
    # check if _name is visibleName - find metadata file with..
    if not _is_uuid(_name):
        files = [f.path for f in os.scandir(folder) if f.name.endswith('.metadata')]
        for f in files:
            with open(f, 'r', encoding='utf8') as fi:
                t = json.load(fi)
            if t['visibleName'] == _name:
                name = t['visibleName']
                uuidname = osp.splitext(osp.basename(f))[0]
                parentuuid = t['parent']
            break
        if parentuuid is None:
            print(f"no file with visibleName {_name} found in {folder}")
            return None

    else: # find .metadata with _name: uuidname
        metadata = osp.join(folder, _name+".metadata")
        assert osp.isfile(metadata), f" metadata file {metadata} not found"
        with open(metadata, 'r', encoding='utf8') as fi:
            t = json.load(fi)
        name = t['visibleName']
        uuidname = _name
        parentuuid = t['parent']

    # find .metadata for parentuuid, fails if nonexistent
    metadata = osp.join(folder, parentuuid+".metadata")
    assert osp.isfile(metadata), f"parent metadata file {metadata} not found"
    with open(metadata, 'r', encoding='utf8') as fi:
        t = json.load(fi)
        parentname = t['visibleName']
    return {"file":{uuidname, name}, "parent":(parentuuid, parentname)}



def get_uuid_from_name(name: str, target_type = "CollectionType", **kwargs) -> Optional[str]:
    """ returns uuid from a folder or file visibleName
    Args:
        name    (str) visible name in remarkable
        target_type (str [ CollectionType]) | DocumentType

    kwargs
        user    (str ['root']) remarkable default
        host    (str ['10.11.99.1']) remarkable usb default
        path    (str)

    TODO VALIDATE check=True, shell=False
    shell=True should work, false should not yet it does.
    """
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    cmd = f'''
    find {path} -type f -name "*.metadata" | while read file; do
    grep -q "\\"type\\": \\"{target_type}\\"" "$file" && \
    grep -q "\\"visibleName\\": \\"{name}\\"" "$file" && \
    echo "$file" && exit 0
    done
    '''
    cmd = ['ssh', f'{user}@{host}', cmd]

    # Execute the SSH command
    out = None
    try:
        result = sp.run(cmd, check=True, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        if result.stdout:
            out = osp.basename(osp.splitext(result.stdout.strip())[0])
    except sp.CalledProcessError as e:
        pass
    return out

##
# .metadata and .content,  necessary files to view pdf in reMarkable
#
def ssh_json(json_str: str, name: str, **kwargs) -> int:
    """ write json string to ssh
    """
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    cmd = f'echo {json.dumps(json_str)} > {name}'
    # Construct the full SSH command as a list
    cmd = ['ssh', f'{user}@{host}', cmd]
    return _run_cmd(cmd, check=True, shell=False)


def make_content(pdf):
    """ .content pageCount and sizeInBytes are important
            orientation is useful
    """
    with open(pdf, 'rb') as _fi:
        red = pypdf.PdfReader(_fi)
        num = len(red.pages)
        orientation = 'landscape'
        if red.pages[1].mediabox.height > red.pages[1].mediabox.width:
            orientation = 'portrait'
    size = os.stat(pdf).st_size

    content = {
        "coverPageNumber": 0,
        "documentMetadata": {},
        "dummyDocument": False,
        "extraMetadata": {},
        "fileType": "pdf",
        "fontName": "",
        "formatVersion": 1,
        "lineHeight": -1,
        "margins": 125,
        "orientation": orientation,
        "originalPageCount": num,
        "pageCount": num,
        "pageTags": [],
        "sizeInBytes": size,
        "tags": [],
        "textAlignment": "justify",
        "textScale": 1
    }
    return json.dumps(content)


def make_metadata(pdf, name, parent=""):
    """ .metadata, parent, DocumentType, and name
    """
    mtime = int(os.stat(pdf).st_mtime)
    metadata = {
        "deleted": False,
        "lastModified": mtime,
        "lastOpened": "0",
        "lastOpenedPage": 0,
        "metadatamodified": False,
        "modified": False,
        "parent": parent,
        "pinned": False,
        "synced": False,
        "type": "DocumentType",
        "version": 0,
        "visibleName": name
    }
    return json.dumps(metadata)

##
# rsync backup of ./local/share/remarkable/xochitl
#
def backup_tablet(folder: str = ".", **kwargs) -> int:
    """ backup script
    Args
        folder ['.'] - if /xochitl exists, sync, else, create new xochitl folder
            if folder == '?' search for existing backup under current tree
    """
    if folder == "?":
        folder = _find_folder('xochitl')
        if folder is None:
            return None

    assert osp.isdir(folder), f"local backup folder '{folder}' not found, nothing done."
    folder = osp.abspath(osp.expanduser(folder))
    if osp.basename(folder) == 'xochitl':
        folder = osp.abspath(osp.expanduser(osp.join(folder, '..')))

    xochitl = osp.join(folder, 'xochitl')
    if not osp.isdir(xochitl):
        print(f"Creating new remarkable backup {xochitl}")

    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))

    cmd = ['rsync',
           '-avzhrP',   # archive, verbose, compress, human-readable, recursive partial, progress
           '--update',  # Skip files that are newer on the receiver
           f'{user}@{host}:{path}', folder]
    return _run_cmd(cmd, check=True, shell=False)

##
# build visible name graph from backup # local scripts
#
def build_uuid_graph(node_name, kinship):
    """ recursively build uuid graph
    """
    if node_name not in kinship or not kinship[node_name]:
        return node_name
    return {name: build_uuid_graph(name, kinship) for name in kinship[node_name]}


def build_name_graph(uidgraph, folder, graph):
    """ convert uuid graph to name graph
    """
    for key, value in uidgraph.items():
        with open(osp.join(folder, f"{key}.metadata"), 'r', encoding='utf8') as fi:
            x = json.load(fi)
            if isinstance(value, str):
                graph[x['visibleName']] = key
            else:
                graph[x['visibleName']] = {'uuid': key}
                build_name_graph(value, folder, graph[x['visibleName']])


def build_file_graph(folder: str) -> Optional[dict]:
    """ builds uuid and name graph from local reMarkable backup
    Args
        folder      str local folder must be either be 'xochitl', parent to xochitl or ? to find it
    """
    kinship = {}
    if folder == "?":
        folder = _find_folder('xochitl')
    if not osp.isdir(folder or  ""):
        print(f"folder <{folder}> not found, pass valid folder.")
        return None

    files = [f.path for f in os.scandir(folder) if f.name.endswith('.metadata')]
    if folder == "." and not files:
        xochitl = osp.join(folder, 'xochitl')
        if osp.isdir(xochitl):
            files = [f.path for f in os.scandir(xochitl) if f.name.endswith('.metadata')]
            if files:
                folder = xochitl

    if not files:
        print(f"no .metadata files found in folder <{folder}> pass valid remarkable backup folder")
        return None


    print(f"backup folder: \033[34m {osp.abspath(osp.expanduser(folder))} \033[0m" )
    for file in files:
        with open(file, 'r', encoding='utf8') as fi:
            x = json.load(fi)
        parent = x["parent"]
        name = osp.basename(osp.splitext(file)[0])
        if parent not in kinship:
            kinship[parent] = set()
        kinship[parent].add(name)

    # Second Pass: Build graph starting from root nodes (nodes with parent '')
    root_nodes = kinship.pop('', None)
    uidgraph = {node: build_uuid_graph(node, kinship) for node in root_nodes}

    # convert to Name graph
    graph = {}
    build_name_graph(uidgraph, folder, graph)
    return graph

##
# miscelaneous
#
def get_pdf_info(pdf: str, page: Optional[int] = None):
    """ get number of pages and page sizes"""
    with open(pdf, 'rb') as _fi:
        red = pypdf.PdfReader(_fi)
        num = len(red.pages)
        if page is None:
            height = [p.mediabox.height for p in red.pages]
            width = [p.mediabox.width for p in red.pages]
        else:
            height = red.pages[page % num].mediabox.height
            width = red.pages[page % num].mediabox.width
    return {'pages':num, 'width':width, 'height':height}


def get_pdfs(folder: str, key: Optional[str] = None) -> list:
    """ get pdfs from local folder
    """
    pdfs = [f.path for f in os.scandir(folder) if f.name.endswith(".pdf")]
    if key:
        pdfs = [f for f in pdfs if key in f]
    return pdfs

def _find_folder(name: str, root: str = '.') -> Optional[str]:
    for dirpath, dirnames, _ in os.walk(root):
        if name in dirnames:
            return os.path.join(dirpath, name)
    print(f"No existing folder {name} under {os.getcwd()}, nothing done")
    return None

def replace_pdf(pdf, visible_name, **kwargs) -> int:
    """
    replaces pdf in remarkable with local pdf
    TODO: fix number of pages, file size.
    TODO: how do i insert a missing page. shift the content
    """
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    if not _is_host_reachable(host, packets=2):
        print (f"host <{host}> is not reachable")
        return 1

    uidname = get_uuid_from_name(visible_name, "DocumentType", **kwargs)

    cmd = ['rsync', '-avz', pdf, f'{user}@{host}:{osp.join(path, uidname)}']
    return _run_cmd(cmd, check=True, shell=False)


def _run_cmd(cmd, check=True, shell=False, text=True) -> int:
    """ TODO replace other functions sp.run, test and validate
    """
    try:
        result = sp.run(cmd, check=check, shell=shell, stdout=sp.PIPE, stderr=sp.PIPE, text=text)
        print("rsync output:", result.stdout)
        _err = result.stderr
        if _err:
            print("Error output!!", _err)
        return 0
    except sp.CalledProcessError as e:
        print("An error occurred:", e.stderr)
    return 1


def export_rm(rm_file: str,
              out: str,
              width: Optional[float] = None,
              height: Optional[float] = None) -> None:
    """ exports single rm markup file to svg or pdf
    Args
        rm_file     (str)   remarkable .rm file version 6
        out         (str)   <name>.svg or <name>.pdf
        width       (int)
    """
    assert out.endswith(".pdf") or out.endswith(".svg"), f"expected .pdf or .svg got <{out}>"

    if out.endswith(".pdf"):
        remarkable_rm_to_pdf(rm_file, out)
    else:
        remarkable_rm_to_svg(rm_file, out)


def _get_page_data(content: dict, force: bool = False) -> list:
    """ return a list of page uuids based on uuid.content
        annotations can appear as 'pages':[uuids, ..]
        or 'cPages':{'pages':[{'id':uuid}, ..]}
    """
    pages = []
    page_ids = [] # page uuids
    if 'cPages' in content and 'pages' in content['cPages']:
        pages = content['cPages']['pages']
    elif 'pages' in content:
        pages = content['pages']

    for i, page in enumerate(pages):
        if isinstance(page, str) and _is_uuid(page):
            page_ids.append(page)
        elif isinstance(page, dict) and 'id' in page and _is_uuid(page['id']):
            page_ids.append(page['id'])
        else:
            assert False, f"cannot recognize annotation pages {pages}"
    assert not force or page_ids, f"expecting content with annotations, got none? {content}"
    return page_ids


def get_annotation_files(pdf: str) -> tuple:
    """ return {page_n:uuid/annot_uuid.rm}, num_pages
    Args
        pdf     (str) uuid.pdf of remarkable fomat
    reads uuid.content containing annotation page info 
    """
    content = pdf.replace('.pdf', '.content')
    folder = osp.splitext(pdf)[0]
    assert osp.isfile(content), f"<{content}> file not found, cannot aligned rm files"
    with open(content, 'r', encoding='utf8') as fi:
        cont = json.load(fi)
    num_pages = cont["pageCount"]

    # orientation = cont['orientation']
    # _info = get_pdf_info(pdf)

    pages = _get_page_data(cont)
    assert num_pages == len(pages), f"num_pages {num_pages}  len(pages) {len(pages)}"

    # build dictionary page_:file.rm
    annotation_files = {i:osp.join(folder, f"{pages[i]}.rm")
                        for i in range(num_pages)
                        if osp.isfile(osp.join(folder, f"{pages[i]}.rm"))}

    return annotation_files, num_pages

def export_merged_pdf(pdf: str,
                      folder: Optional[str] = ".",
                      name: Optional[str] = None,
                      page: Optional[int] = None,
                      stroke_scale: float = 0.6,
                      annotation_scale: float = 1.0) -> Optional[str]:
    """ Exports pdf merged with remarkable annotations as pdf
    Args
        pdf     (str) .pdf file in remarkable format: uuid.pdf with
            uuid.metadata, uuid.content & uuid/*.rm  exported to local backup
        folder  (str ['.']) output folder
        name    (str [None]) if None -> visible_name.replace(" ", "_")+".pdf"
        page    (int [None]) if None export all pages
        stroke_scale (float [0.6]) svg is improperly scaled atm, rescale
    TODO: does orientation, customZoom parameters matter?
    .content contains annotation notes in diferent formats:
        'pages'
        '3bb743f8-15b9-45a5-87a1-1369dff6769c'
            "coverPageNumber": 0,
            "customZoomCenterX": 0,
            "customZoomCenterY": 936,
            "customZoomOrientation": "portrait",
            "customZoomPageHeight": 1872,
            "customZoomPageWidth": 1404,
            "customZoomScale": 1,
        'cPages'
        # file ='3c50b5d6-e9b3-4dae-8280-42c5490b83f3.pdf'
            "customZoomCenterX": -4.984733205774539,
            "customZoomCenterY": 1338.400865750464,
            "customZoomOrientation": "portrait",
            "customZoomPageHeight": 2654,
            "customZoomPageWidth": 1877,
            "customZoomScale": 0.802450168319183,
        """
    if (not osp.isfile(pdf) or not pdf.endswith('.pdf')
        or not _is_uuid(osp.splitext(osp.basename(pdf))[0])):
        print(f"pass valid remarkable uuid.pdf file, got <{pdf}> \
              isfile: {osp.isfile(pdf)}, {len(osp.basename(pdf))} ?= 40 ")
        return None

    # resolve output name from visibleName in uuid.metadata
    if name is None:
        metadata = pdf.replace('pdf', 'metadata')
        assert osp.isfile(metadata), f"<{metadata}> file not found, pass explicit name"
        with open (metadata, 'r', encoding='utf8') as fi:
            m = json.load(fi)
            name = m['visibleName'].replace(' ', '_')
    if name[-4:] != '.pdf':
        name += '.pdf'
    name = osp.join(folder, "_annotated".join(osp.splitext(name)))

    # get annotations from uuid.content
    # TODO get zoom, and other infos
    annotations, num_pages = get_annotation_files(pdf)
    if not annotations:
        print(f"file {pdf} has no annotations")
        return None

    temp_pdf = tempfile.NamedTemporaryFile().name + ".pdf"
    _info = get_pdf_info(pdf)

    if page is not None:
        if page in annotations:
            name = f"_{page:03d}".join(osp.splitext(name))
            # temp_pdf = "temp_pdf.pdf"
            remarkable_rm_to_pdf(annotations[page], outfile=temp_pdf, width=_info['width'][page],
                                 height=_info['height'][page], thick=stroke_scale,
                                 rescale=annotation_scale)
            main = pypdf.PdfReader(pdf)
            overlay = pypdf.PdfReader(temp_pdf)
            mainpage = main.pages[page]
            pdf_writer = pypdf.PdfWriter()
            mainpage.merge_page(overlay.pages[0])
            pdf_writer.add_page(mainpage)
            with open(name, 'wb') as fi:
                pdf_writer.write(fi)

        else:
            print(f"page {page} has no annotations")
            return None
    else:
        main = pypdf.PdfReader(pdf)
        pdf_writer = pypdf.PdfWriter()
        for i in range(num_pages):
            mainpage = main.pages[i]
            if i in annotations:
                remarkable_rm_to_pdf(annotations[i], outfile=temp_pdf, width=_info['width'][i],
                                    height=_info['height'][i], thick=stroke_scale,
                                    rescale=annotation_scale)
                overlay = pypdf.PdfReader(temp_pdf)
                mainpage.merge_page(overlay.pages[0])
            pdf_writer.add_page(mainpage)
        with open(name, 'wb') as fi:
            pdf_writer.write(fi)

    return name
