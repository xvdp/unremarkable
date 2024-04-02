# unremarkable
## reMarkable tablet IO via SSH, without app.
### `pdf_to_remarkable` upload local pdf to reMarkable
### `remarkable_backup` rsync from reMarkable to local
### `remarkable_ls` print directory of backup files as visibleNames:uuids / From backup
### `remarkable_export_annotated` merges v.6 annotations with pdf - only lines, no text
### `remarkable_restart` restarts xochitl service

I wrote these code snippets in order to use the reMarkable tablet similar to its behavior prior to version 3.5.  I stopped automatic updates after v3.5 to prevent any surprises.

Other possible useful functions available through python
```python
#
# console command's mirrors
from unremarkable import remarkable_backup, export_annotated_pdf, upload_pdf

# upload pdf to remarkable folder
upload_pdf('Topology_Second_Edition.pdf', 'Maths')

#
# python only
from unremarkable import add_authors, pdf_metadata, get_annotated, remarkable_name

# on local backup: resolve uuid and visible name from uuid or sufficiently unique partial name
remarkable_name("perturbation inactivation")
[*] ('98934bc7-2278-4e43-b2ac-1b1675690074', 'Perturbation Inactivation Based Adversarial Defense for Face Recognition')

# on local backup: add author names to .content
# upload to remarkable to show authors in UI, tablet file must be closed
# filename can be uuid, or partial unique name, use `remarkable_name(filename)` to check
add_authors(filename, authors=('J. Doe', 'P. Einstein'), year=2122, restart=True) 

# on local pdf: add metadata keys to a local pdf
pdf_metadata(filename, [author], [title], [year], [delete_keys], overwrite=True, kwargs)

# on local backup: return a list with all annotated files in backup
pprint.pprint(get_annotated())


```



## TODO
- [ ] Tests
- [ ] Validate on MacOS

## info
Works with tablet
* `Settings > General > Software > Version 3.5.2.1807`
* `hostnamectl  Operating System: Codex Linux 3.1.266-2 (dunfell) Kernel: Linux 5.4.70-v1.3.4-rm11x`
* `.rm` files version 6 - code adapted from https://github.com/ricklupton/rmscene to run with python 3.9

Before v 3.5 reMarkable could upload files by drag and drop to a browser pointed to the tablet ip `10.11.99.1`. That was deprecated in favour of an app - which annoyed me as going against the rules of opensource. Requests to reinstate that were denied by reMarkable.

The tablet uses a linux operating system 'Codex Linux' based on 'openembedded', therefore uploading and downloading should be simple using ssh.

The only nuance is that the filesystem is not a linux folder structure but a flat directory with files stored as uuids and metadata saved as json files. All data is stored in 
`~/.local/share/remarkable/xochitl/`

All pdfs are renamed to `<some_uuid>.pdf`

In order for uploads to be visible by the UI they need at least two companion json files 
* `<some_uuid>.pdf` needs
* `<some_uuid>.metadata` # at least containing `pageCount` and `sizeInBytes`. Without `pageCount` the UI shows a single blank page.
* `<some_uuid>.content` # at least containing `visibleName` & `parent`

There are other json files as well under that uuid but they are created by the tablet.
 

# Installation
1. install openssh-server in linux or openssh in Mac
2. generate a public ssh key and upload it to .shh/authorized_keys  - to do so youll need to access the tablet through `ssh root@10.11.99.1`  using the password which can be found in `Settings > Help > Copyrights and licenses`
3. cd unremarkable && pip install .

Installation creates console entry points.

# Use

### info
``` bash
remarkable_help
```

### upload: local .pdf to reMarkable
```bash
#!/bin/bash
pdf_to_remarkable <localfile.pdf|*> [parent folder name] --name <visible name> --no_restart
# Args
#   <local pdf str | *>  existingfile or * 
# Optional args
#   <parent str>        name of remarkable parent folder, must exist if passed, default -> "" -> MyFiles
# Optional kwargs
#   --name  <str>       visible name of pdf on remarmable, default to pdf name with no extension
#   --no_restart        by default upload restarts xochitl service to show pdf on file list   
```
### download: export merged .pdf and .rm annotations; rm v6 files only
``` bash
remarkable_export_annotated <uuid or name> [page] [folder] [out_name] [xochitl folder]
# exports annotated pdf from local backup
# only file name is required
# Only version 6 .rm supported
```

### download: reMarkable to local incremental backup
```bash
#!/bin/bash
remarkable_backup [<local_folder>]
#   local_folder arg optional, default None -> stored path in ~/.xochitl or '.'
#       if folder passed it must exist.
#    stores folder to ~/.xochitl file
# backup is done with incremental rsync -avzhP --update
    # archive, verbose, compress, human-readable, partial, progress, newer files only
```
### info: local backed up reMarkable, info,
```bash
#!/bin/bash
# print reMarkable visible_name file graph on local backup
remarkable_ls [<local_folder>] # default [.]
# Example: print uuid of file with visible name "God of Carnage" in local folder
remarkable_ls . | grep "God of Carnage"
#         'God of Carnage': '1e6d7bc7-6893-436c-b1e6-99925097cf92',

remarkable_read_rm <.rm annotation file> 
# Example
remarkable_read_rm '3bb743f8-15b9-45a5-87a1-1369dff6769c/6bf1e7b6-8c34-4c7e-85d3-ff9b01039cb0.rm'
```

### info. local pdf num pages, width, height
```bash
#!/bin/bash
pdf_info <mypdffile.pdf> [page number]
# prints {'pages': num_pages, 'width': [widths], 'height': [heights]}
# if optional arg page is entered returns width and height for single page
```

