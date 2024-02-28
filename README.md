# unremarkable
## upload to reMarkable with ssh, without app 
I wrote these code snippets in order to use the reMarkable tablet similar to its behavior prior to version 3.5.  I stopped automatic updates after v3.5 to prevent any surprises - if anyone! tries this on a newer tablet, let me know if it still works - I would probably then update mine.

Works with tablet
* `Settings > General > Software > Version 3.5.2.1807`
* `hostnamectl  Operating System: Codex Linux 3.1.266-2 (dunfell) Kernel: Linux 5.4.70-v1.3.4-rm11x`

Before v 3.5 reMarkable could upload files by drag and drop to a browser pointed to the tablet ip `10.11.99.1`. That was deprecated in favour of an app - which annoyed me as going against the rules of opensource. Requests to reinstate that were denied by reMarkable.

The tablet uses a linux operating system 'Codex Linux' based on 'openembedded', therefore uploading and downloading should be simple using ssh.

The only nuance is that the filesystem is not a linux folder structure but a flat directory with files stored as uuids and metadata saved as json files. All data is stored in 
`~/.local/share/remarkable/xochitl/`

All pdfs are renamed to `<some_uuid>.pdf`

In order for uploads to be visible by the UI they need at least two companion json files 
* `<some_uuid>.pdf` needs
* `<some_uuid>.metadata` # at least containing `pageCount` and `sizeInBytes`. Without `pageCount` the UI shows a single blank page.
* `<some_uuid>.content` # at least containing `visibleName` & `parent`


There are other json files as well under that uuid but they are created by

# Install
1. install openssh-server in linux or openssh in Mac
2. generate a public ssh key and upload it to .shh/authorized_keys  - to do so youll need to access the tablet through `ssh root@10.11.99.1`  using the password which can be found in `Settings > Help > Copyrights and licenses`
3. cd unremarkable && pip install .

Installation creates two console entry points:
pdf_to_remarkable and backup_remarkable

# Use
```bash
#!/bin/bash
# upload pdf file
pdf_to_remarkable <somefile.pdf> [<remarkable_visible_name>] [<rename>]
# optional args:
#   remarkable_visible_name: if no folder or inexistent folder is passed, file will be uploaded to myFiles
#   rename: if not passed uses prettyfied filename ( no ext, .replace('_',' '))
# xochitl.service should restart and show new files, if not reboot the reMarkable

# backup reMarkable tablet to folder [default '.']
backup_remarkable [<existing_local_folder>]

# print reMarkable visible name file graph on local backup
remarkable_file_graph [<local_backup_folder>]
# Example: print uuid of file with visible name "God of Carnage" in local folder
remarkable_file_graph . | grep "God of Carnage"
#         'God of Carnage': '1e6d7bc7-6893-436c-b1e6-99925097cf92',
```

# TODO
- [ ] Tests
- [ ] Validate on MacOS
- [ ] Add rm support, look at https://github.com/reHackable/maxio/blob/master/tools/rM2svg