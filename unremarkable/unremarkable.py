"""
uploads pdfs to reMarkable tablet
ENTRY POINTS:

$ pdf_to_remarkable path/to/file.pdf ["remarkable folder name"] ["file visible name"]
$ backup_remarkable [path/to/backup/folder]
"""
from typing import Optional, Union
import os
import os.path as osp
import subprocess as sp
import uuid
import json
import pypdf
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


def _is_host_reachable(ip='10.11.99.1', packets=5, msg=None) -> bool:
    command = ['ping', '-w', str(packets), ip]
    try:
        sp.run(command, stdout=sp.DEVNULL, stderr=sp.DEVNULL, check=True)
        return True
    except sp.CalledProcessError:
        if msg is not None:
            print(msg)
        return False

def _visible_name(name):
    return osp.basename(osp.splitext(name)[0]).replace('_', ' ')

##
# Main upload process
#
def upload_pdf(pdf: str,
               folder: str = "",
               visible_name: Optional[str] = None,
               restart: bool = True,
               force: bool = False,
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
        force           (bool [False]) if True and file found, don't upload
    kwargs:
        host    (str ['10.11.99.1']) remarkable usbc port, change if using wifi
        user    (str ['root']) remarkable default
        path    (str [ '.local/share/remarkable/xochitl])) remarkable default
    """
    # TODO also allow epub
    _kw = _kwargs_get(**kwargs)
    host, user, path = get_host_user_path(**_kw)
    if not _is_host_reachable(host, packets=2, msg=f"host <{host}> is not reachable"):
        return None

    # multiple files
    if osp.basename(pdf) == "*":
        pdfs = [f.path for f in os.scandir(osp.dirname(pdf) or None)
                if f.name.lower().endswith(".pdf")]
        if pdfs:
            print(f"Uploading {len(pdfs)} files to reMarkable")
            for pdf in pdfs:
                upload_pdf(pdf, folder, visible_name, restart=False, force=force, **kwargs)
            if restart:
                restart_xochitl(**kwargs)
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
            visible_name = _visible_name(pdf)

        # check that file hasnt already been uploaded
        if not force:
            file_uuid = get_uuid_from_name(visible_name, target_type='DocumentType', **kwargs)
            if file_uuid:
                _R="\033[31m"
                _Y="\033[32m"
                _A="\033[0m"
                parent_uuid, parent_name = get_remote_parent(file_uuid, False, **kwargs)
                _msg = f" {_R}exists, nothing done: pass force=True (-f) to override{_A}"
                print(f"{_R}file {_Y}{parent_name}/{visible_name}{_A} ({file_uuid}.pdf){_msg}")
                return

        # create .content and .metadata files
        content = make_content(pdf)
        metadata = make_metadata(pdf, visible_name, uuidfolder)

        print(f"Upload\n\t{osp.basename(pdf)}\n\t as '{folder}/{visible_name}'\n\t uuid {uid}")
        ret = _rsync_up(pdf, name=f"{uid}.pdf", **_kw)
        # upload pdf and if success, write json files
        if not ret: # generate content and metadata files on device
            name = osp.join(path, uid)
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
            restart_xochitl(**kwargs)


def restart_xochitl(**kwargs) -> int:
    """ serivce is restarted on reboot
    """
    host, user, _ = get_host_user_path(**_kwargs_get(**kwargs))
    cmd = ['ssh', f'{user}@{host}', 'systemctl', 'restart', 'xochitl.service']
    return _run_cmd(cmd, check=True, shell=False)


def _rsync_up(fname: str,
              sync_args: str = '-avzhP',
              update: bool = True,
              **kwargs) -> int:
    """  upload file to xochitl path
    Args
        fname       (str) file to upload
        sync_args   (str) ['-avzhP'])
            archive, verbose, compress, human-readable, partial, progress
        update      (bool [True]) skip newer files on receiver
    kwargs
        name        (str) store with different name than filename
    default xochitl override
        host    (str) ['10.11.99.1']
        user    (str) ['root]
        path    (str) ['local/share/remarkable/xochitl']
    TODO replace _rsync pdf"""
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))

    if not _is_host_reachable(host, packets=2, msg=f"host <{host}> is not reachable"):
        return 1
    name = osp.join(path, osp.basename(kwargs.get('name', fname)))
    sync_args = (sync_args, '--update') if update else (sync_args,)

    cmd = ['rsync', *sync_args, fname, f'{user}@{host}:{name}']
    return _run_cmd(cmd, check=True, shell=False)


def gen_uuid(uuids=()):
    """generate uuid ensuring uniqueness in set"""
    uid = str(uuid.uuid4())
    if uid in uuids:
        uid = gen_uuid(uuids)
    return uid


def runcmd(cmd: list,
           shell: bool = False,
           text: bool = True,
           check: bool = False,
           verbose: bool = True) -> sp.CompletedProcess:
    """ default run
    Args
        cmd     (list, str)     # to run str set shell: True
        shell   (bool [False])  # shell=False, prevent injections
        text    (bool [True])   # text=True, return ascii
        check   (bool [False])  # check=False, failure tolerant
    """
    result = sp.run(cmd, shell=shell,   # shell=False, prevent injections
                stdout=sp.PIPE, stderr=sp.PIPE,
                text=text,          # text=True, return ascii
                check=check)        # check=False, failure tolerant
    if not result.returncode:
        return result.stdout
    else:
        if verbose:
            print(f"cmd {cmd} -> return code {result.returncode}, error {result.stderr}")
        return None

def get_remote_files(name: Union[str, tuple],
                     parent: bool = False,
                     verbose: bool = True,
                     **kwargs) -> dict:
    """check if  remote file/files exist, return dict with format provided
    
    { 'nonexist':[name ..],
      'exist: {name: {'uuid':uuid, 'parent_name': parent_name, 'parent_uuid': parent_uuid}}
    }
    
    """
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    out = {'nonexist': [], 'exist': {}}
    if not _is_host_reachable(host, packets=2, msg=f"host <{host}> is not reachable"):
        return out
    if isinstance(name, str):
        name = (name,)

    for i, n in enumerate(name):
        if verbose:
            print(f"checking [{i}/{len(name)}] {n},")
        _basename = osp.basename(n)
        if _is_uuid(osp.splitext(_basename)[0]):
            file_uuid = uuid_exists(_basename, **kwargs)
        else:
            file_uuid = get_uuid_from_name( _visible_name(n), target_type='DocumentType', **kwargs)

        if not file_uuid:
            if verbose:
                print("  -> NOT FOUND")
            out['nonexist'] += [n]
        else:
            if verbose:
                print("  -> exists")
            out['exist'][n] = {'uuid': file_uuid}
            if parent:
                print(f"get parent of {file_uuid}, {n}")
                parent_uuid, parent_name = get_remote_parent(file_uuid, False, **kwargs)
                out['exist'][n]['parent_name'] = parent_name
                out['exist'][n]['parent_uuid'] = parent_uuid
    return out


def get_remote_parent(uuid_name: str, check_reachable: bool = True, **kwargs) -> tuple:
    """return uuid and visible name of remote parent
    # 1 looks at uuid metadata, gets 'parent' field -> uuid
    # 2 looks at parent uuid, gets visibleName field
    Args
        uuid                (str) file uuid
        check_reachable     (bool [True]) if False , assumes connection is good
    kwargs host, user, path
    """
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    if check_reachable and not _is_host_reachable(host, packets=2,
                                                  msg=f"host <{host}> is not reachable"):
        return None

    out = runcmd(['ssh', f'{user}@{host}', 'cat', f"{path}/{uuid_name}.metadata"])
    if out is None: # no uuid_name.metadata file
        return None, ''

    parent_uuid = json.loads(out).get('parent')
    if parent_uuid is None: #  metadata contains no 'parent' field
        return None, ''

    out = runcmd(['ssh', f'{user}@{host}', 'cat', f"{path}/{parent_uuid}.metadata"])
    if out is None: # no parent_uuid.metadata file
        return None, ''

    return parent_uuid, json.loads(out).get('visibleName', '')


def list_remote(ext: Optional[str] = '.pdf', **kwargs) -> Optional[list]:
    """ return basenames of existing pdf files in reMarkable
    result = sp.run(cmd, shell=False, stdout=sp.PIPE, stderr=sp.PIPE, text=True,check=False) 
    """
    keep_ext = kwargs.get('keep_ext', False)
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    if not _is_host_reachable(host, packets=2, msg=f"host <{host}> is not reachable"):
        return None
    path = path if ext is None else osp.join(path, f"*{ext}")
    cmd = ['ssh', f'{user}@{host}', 'ls', path]
    out = runcmd(cmd)
    if out is not None:
        out = out.split("\n")[:-1]
        if len(out) == 1 and not out[0]:
            out = []
        out = [osp.basename(o) for o in out]
        if not keep_ext:
            out = [osp.splitext(o)[0] for o in out]
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


def uuid_exists(uuid_name: str, **kwargs) -> Optional[str]:
    """ check if file exists in remote folder
    """
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    cmd = ['ssh', f'{user}@{host}', f'''[ -e {path}/{uuid_name} ] && echo {path}/{uuid_name} || echo ''']
    out = ''
    try:
        result = sp.run(cmd, check=True, stdout=sp.PIPE, stderr=sp.PIPE, text=True)
        if result.stdout:
            out = osp.basename(osp.splitext(result.stdout.strip())[0])
    except sp.CalledProcessError as e:
        pass
    return out


def get_uuid_from_name(name: str, target_type = "CollectionType", **kwargs) -> Optional[str]:
    """ returns uuid from a folder or file visibleName - ON remarkable tablet
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

# pylint: disable=no-member
def make_content(pdf):
    """ .content pageCount and sizeInBytes are important
            orientation is useful
    """
    with open(pdf, 'rb') as _fi:
        red = pypdf.PdfReader(_fi)
        num = len(red.pages)
        orientation = 'landscape'
        if red.pages[0].mediabox.height > red.pages[0].mediabox.width:
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


def backup_tablet(folder: Optional[str] = None, **kwargs) -> int:
    """ backup script
    Args
        folder [None] - if /xochitl folder is registered in ~/xochitl, else "."
            '?' search for existing recursively '.', do not thing if not found
            '<valid folder>
        saves xochitl folder in ~/.xochilt test file
    """
    # 1. is remarkable plugged in
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    if not _is_host_reachable(host, packets=2, msg=f"host <{host}> is not reachable"):
        return 1

    if folder is None:
        folder = _get_xochitl()
        if folder is None:
            folder = "."

    # 2. get folder
    if folder == "?":
        folder = _get_xochitl()
        if folder is None:
            folder = _find_folder('xochitl')
            if folder is None:
                return None

    # a bit messy, the update command needs the parent of xochitl.
    assert osp.isdir(folder), f"local backup folder '{folder}' not found, nothing done."
    folder = osp.abspath(osp.expanduser(folder))
    if osp.basename(folder) == 'xochitl':
        folder = osp.abspath(osp.expanduser(osp.join(folder, '..')))

    xochitl = osp.join(folder, 'xochitl')
    if not osp.isdir(xochitl):
        print(f"Creating new remarkable backup {xochitl}")
    else:
        print(f"backup to existing xochitl folder: {xochitl}")

    cmd = ['rsync',
           '-avzhrP',   # archive, verbose, compress, human-readable, recursive partial, progress
           '--update',  # Skip files that are newer on the receiver
           f'{user}@{host}:{path}', folder]
    out = _run_cmd(cmd, check=True, shell=False)
    _set_xochitl(xochitl)
    return out

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


def build_file_graph(folder: Optional[str] = None, dir_type: bool = False) -> Optional[dict]:
    """ builds uuid and name graph from local reMarkable backup
    Args
        folder      (str) local folder:  'xochitl', parent to xochitl, or ?
        dir_type    (bool [False]) only list folders
    """
    kinship = {}

    if folder == "?" or folder is None:
        folder = _get_xochitl()
        if folder is None:
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


    print(f"\033[32mreMarkable backup dir: \033[34m{osp.abspath(osp.expanduser(folder))} \033[0m")
    if dir_type:
        print("  \033[31mlisting folders \033[0m" )
    for file in files:
        with open(file, 'r', encoding='utf8') as fi:
            x = json.load(fi)
        if dir_type and x['type'] != "CollectionType":
            continue
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

def _find_folder(name: str, root: str = '.') -> Optional[str]:
    """recursively finds  folder of a given name"""
    for dirpath, dirnames, _ in os.walk(root):
        if name in dirnames:
            folder = os.path.join(dirpath, name)
            return osp.abspath(osp.expanduser(folder))
    print(f"No existing folder {name} under {os.getcwd()}, nothing done")
    return None

def _get_xochitl(**kwargs):
    """get backup name  from ~/.xochitl"""
    _root = osp.abspath(osp.expanduser(kwargs.get('root', '~')))
    _xochitl = osp.join(_root, '.xochitl')
    if osp.isfile(_xochitl):
        with open(_xochitl, 'r', encoding='utf') as _fi:
            out = _fi.read().split("\n")[0]
            assert osp.isdir(out), f"xochitl stored but not found <{out}>"
            return out
    return None

def _set_xochitl(folder: str, **kwargs):
    """ set backup folder """
    folder = osp.abspath(osp.expanduser(folder))
    assert osp.isdir(folder), f"folder {folder} invalid"

    # store information in root/.xochitl
    _root = osp.abspath(osp.expanduser(kwargs.get('root', '~')))
    _xochitl = osp.join(_root, '.xochitl')
    with open(_xochitl, 'w', encoding='utf') as _fi:
        _fi.write(folder)

def replace_pdf(pdf, visible_name, **kwargs) -> int:
    """
    replaces pdf in remarkable with local pdf
    TODO: fix number of pages, file size.
    TODO: how do i insert a missing page. shift the content
    """
    host, user, path = get_host_user_path(**_kwargs_get(**kwargs))
    if not _is_host_reachable(host, packets=2, msg=f"host <{host}> is not reachable"):
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
