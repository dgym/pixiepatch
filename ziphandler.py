import os
import tempfile
import shutil
from zipfile import ZipFile
from pixiepatch import netpath


class ZIPHandler(object):
    def walk(self, archive):
        with ZipFile(archive, 'r') as zip:
            for name in zip.namelist():
                if not name.endswith('/'):
                    contents = zip.read(name)
                    yield name, contents, None

    def get(self, archive, name):
        with ZipFile(archive, 'r') as zip:
            return zip.read(netpath(name))

    def set(self, archive, name, contents, mode=None):
        d = os.path.dirname(archive)
        if d and not os.path.exists(d):
            os.makedirs(d)

        if os.path.exists(archive):
            with ZipFile(archive, 'r') as zip:
                delete = netpath(name) in zip.namelist()
            if delete:
                self.delete(archive, name)

        with ZipFile(archive, 'a') as zip:
            zip.writestr(netpath(name), str(contents))

    def delete(self, archive, name):
        name = netpath(name)
        fd, tmp = tempfile.mkstemp()
        try:
            shutil.copy(archive, tmp)
            with ZipFile(tmp, 'r') as old_zip:
                with ZipFile(archive, 'w') as new_zip:
                    for member in old_zip.namelist():
                        if member != name:
                            new_zip.writestr(member, old_zip.read(member))
        finally:
            os.close(fd)
            os.unlink(tmp)
