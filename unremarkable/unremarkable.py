"""
uploads pdfs to 

TODO:
* backup
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
import pypdf

def get_host_user_path(host: str = '10.11.99.1',
                       user: str = 'root',
                       path: str = '.local/share/remarkable/xochitl') -> tuple:
    """ default user and folder as of version 3.5.2.1807
    Args
        host    (str ['10.11.99.1']) change if running thru wifi
        user    (str ['root']) remarkable default
        path    (str [ '.local/share/remarkable/xochitl])) remarkable default
    """
    return host, user, path

def _kwargs_get(items=('host', 'user', 'path'), **kwargs):
    return {k:v for k,v in kwargs.items() if k in items}

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
    assert osp.isfile(pdf) and pdf.lower().endswith(".pdf"), f"pdf expected {pdf}, not found"
    _kw = _kwargs_get(**kwargs)
    host, user, path = get_host_user_path(**_kw)
    uuids = list_remote(**_kw)
    uid = gen_uuid(uuids)

    uuidfolder = folder
    if folder:
        uuidfolder = get_uuid_from_name(folder, **_kw)
        if uuidfolder is None:
            uuidfolder = ""
            print(f"folder <{folder}> not found, uploading to 'MyFiles'")

    if visible_name is None:
        visible_name = osp.basename(osp.splitext(pdf)[0])
        visible_name = visible_name.replace('_', ' ')
    # create .content and .metadata files
    content = make_content(pdf)
    metadata = make_metadata(pdf, visible_name, uuidfolder)

    name = osp.join(path, uid)

    print(f"Uploading pdf\n\t{osp.basename(pdf)}\n\t as '{folder}/{visible_name}'\n\t uuid {uid}")
    ret = _rsync_pdf(pdf, name, **_kw)
    if not ret:
        ssh_json(content, f"{name}.content", **_kw)
        ssh_json(metadata, f"{name}.metadata", **_kw)
    uploads = [f for f in list_remote(None, keep_ext=True, **_kw) if uid in f]
    if uploads:
        uploads = '\n\t'.join(uploads)
        print(f"files uploaded \n\t{uploads}")
    else:
        print("no files uploaded")

    if restart:
        _restart_xochitl(**kwargs)

def _restart_xochitl(**kwargs):
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    cmd = ['ssh', f'{user}@{host}', 'systemctl', 'restart', 'xochitl.service']
    try:
        result = sp.run(cmd, check=True, shell=False, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        print("rsync output:", result.stdout)
        _err = result.stderr
        if _err:
            print("Error output!!", result.stderr)
        return 0
    except sp.CalledProcessError as e:
        print("An error occurred:", e.stderr)
    return 1

def _rsync_pdf(pdf: str,
               name: str,
               **kwargs):
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    name = f'{name}.pdf'
    cmd = ['rsync',
           '-avzhP',   # archive, verbose, compress, human-readable, partial, progress
           '--update',  # Skip files that are newer on the receiver
           pdf, f'{user}@{host}:{name}']
    try:
        result = sp.run(cmd, check=True, shell=False, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        print("rsync output:", result.stdout)
        _err = result.stderr
        if _err:
            print("Error output!!", result.stderr)
        return 0
    except sp.CalledProcessError as e:
        print("An error occurred:", e.stderr)
    return 1

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
    """ return basenames of existing files
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


def get_uuid_from_name(name: str,
                       target_type = "CollectionType",
                       **kwargs) -> Optional[str]:
    """ returns uuid from a folder visibleName
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


def ssh_json(json_str: str, name: str, **kwargs) -> str:
    """ upload a json string to ssh, defaults to remarkable defaults
    """
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    cmd = f'echo {json.dumps(json_str)} > {name}'
    # Construct the full SSH command as a list
    cmd = ['ssh', f'{user}@{host}', cmd]
    # Execute the SSH command without using shell=True
    try:
        result = sp.run(cmd, check=True, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        if result.stderr:
            print("Error:", result.stderr)
        else:
            print(f"> {name} created")
    except sp.CalledProcessError as e:
        print("SSH command failed:", e)


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

def backup_tablet(folder: str = ".", **kwargs):
    """ backup script
    """
    assert osp.isdir(folder), f"local backup folder '{folder}' not found, nothing done."

    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))

    cmd = ['rsync',
           '-avzhrP',   # archive, verbose, compress, human-readable, recursivek partial, progress
           '--update',  # Skip files that are newer on the receiver
           f'{user}@{host}:{path}', folder]
    try:
        result = sp.run(cmd, check=True, shell=False, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        print("rsync output:", result.stdout)
        _err = result.stderr
        if _err:
            print("Error output!!", result.stderr)
        return 0
    except sp.CalledProcessError as e:
        print("An error occurred:", e.stderr)
    return 1

#
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
