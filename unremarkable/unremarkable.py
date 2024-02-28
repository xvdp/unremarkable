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
import argparse
from typing import Optional
import os
import os.path as osp
import subprocess as sp
import uuid
import json
import pprint
import pypdf
from .rm import rm2svg, rm2pdf

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
        pdf     (str) name of valid pdf file to upoad
        folder  (str ['']) folder visibleName, on tablet, existing only, default "", 
        visible_name (str [None]) if none, file will be uploaded as pdf basename
    kwargs:
        host    (str ['10.11.99.1']) remarkable usbc port, change if using wifi
        user    (str ['root']) remarkable default
        path    (str [ '.local/share/remarkable/xochitl])) remarkable default
    """
    # todo also allow epub
    assert osp.isfile(pdf) and pdf.lower().endswith(".pdf"), f"pdf expected {pdf}, not found"
    _kw = _kwargs_get(**kwargs)
    host, user, path = get_host_user_path(**_kw)

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
    print(f"Uploading pdf\n\t{osp.basename(pdf)}\n\t as '{folder}/{visible_name}'\n\t uuid {uid}")
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

def _restart_xochitl(**kwargs):
    """ serivce is restarted on reboot
    """
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    cmd = ['ssh', f'{user}@{host}', 'systemctl', 'restart', 'xochitl.service']
    return _run_cmd(cmd, check=True, shell=False)


def _rsync_pdf(pdf: str,
               name: str,
               **kwargs):
    """ functional for main pdf upload"""
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    name = f'{name}.pdf'
    cmd = ['rsync',
           '-avzhP',   # archive, verbose, compress, human-readable, partial, progress
           '--update',  # Skip files that are newer on the receiver
           pdf, f'{user}@{host}:{name}']
    return _run_cmd(cmd, check=True, shell=False)


def get_pdfs(folder: str, key: Optional[str] = None) -> list:
    """ get pdfs from local folder
    """
    pdfs = [f.path for f in os.scandir(folder) if f.name.endswith(".pdf")]
    if key:
        pdfs = [f for f in pdfs if key in f]
    return pdfs

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
def ssh_json(json_str: str, name: str, **kwargs) -> str:
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
def backup_tablet(folder: str = ".", **kwargs):
    """ backup script
    """
    assert osp.isdir(folder), f"local backup folder '{folder}' not found, nothing done."

    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))

    cmd = ['rsync',
           '-avzhrP',   # archive, verbose, compress, human-readable, recursive partial, progress
           '--update',  # Skip files that are newer on the receiver
           f'{user}@{host}:{path}', folder]
    return _run_cmd(cmd, check=True, shell=False)

##
# build visible name graph from backup
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

def build_file_graph(folder: str) -> dict:
    """ builds uuid and name graph from local reMarkable backup
    """
    kinship = {}
    files = [f.path for f in os.scandir(folder) if f.name.endswith('.metadata')]
    assert files, f"no .metadata files found in {folder}, pass valid remarkable backup folder"
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
def replace_pdf(pdf, visible_name, **kwargs):
    """
    replaces pdf in remarkable with local pdf
    TODO: fix number of pages, file size.
    TODO: how do i insert a missing page. shift the content
    """
    uidname = get_uuid_from_name(visible_name, "DocumentType", **kwargs)
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))

    cmd = ['rsync', '-avz', pdf, f'{user}@{host}:{osp.join(path, uidname)}']
    return _run_cmd(cmd, check=True, shell=False)


def _run_cmd(cmd, check=True, shell=False, text=True):
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

##
# console entry points
#
def backup_remarkable_fun():
    """console entry point to command backup_remarkable"""
    parser = argparse.ArgumentParser(description='Backup tablet')
    parser.add_argument('folder', type=str, nargs='?', default='.', help='parent of tablet backup')
    args = parser.parse_args()
    backup_tablet(args.folder)


def pdf_to_remarkable_fun():
    """console entry point to pdf_to_remarkable"""
    parser = argparse.ArgumentParser(description='Upload pdf')
    parser.add_argument('pdf', type=str, help='valid .pdf file')
    parser.add_argument('parent', type=str, nargs='?', default='', help='parent folder')
    parser.add_argument('--name', type=str, default=None, help='visible name, optional')
    # Parse arguments
    args = parser.parse_args()
    upload_pdf(args.pdf, args.parent, args.name)

def print_file_graph_fun():
    """console entry point to print remarkable backup file graph"""
    parser = argparse.ArgumentParser(description='Upload pdf')
    parser.add_argument('folder', type=str, help='folder with remarkable backup')
    args = parser.parse_args()
    graph = build_file_graph(args.folder)
    pprint.pprint(graph)

def export_rm_fun():
    """console entry point to convert .rm file to pdf or sfg"""
    parser = argparse.ArgumentParser(description='rm to pdf converter')
    parser.add_argument('rm_file', type=str, help='v6 .remarkable file')
    parser.add_argument('out', type=str, help='out pdf/sfg')
    args = parser.parse_args()
    assert args.out.endswith(".pdf") or args.out.endswith(".svd"), f"expected .pdf or .svg output got {args.out}"
    if args.out.endswith(".pdf"):
        rm2pdf(args.rm_file, args.out)
    else:
        rm2svg(args.rm_file, args.out)
