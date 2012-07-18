import os
import tempfile
import shutil
from zipfile import ZipFile


class ZIPHandler(object):
    def walk(self, archive):
        with ZipFile(archive, 'r') as zip:
            for name in zip.namelist():
                if not name.endswith('/'):
                    contents = zip.read(name)
                    yield name, contents, None

    def get(self, archive, name):
        with ZipFile(archive, 'r') as zip:
            return zip.read(name)

    def set(self, archive, name, contents, mode=None):
        d = os.path.dirname(archive)
        if d and not os.path.exists(d):
            os.makedirs(d)

        with ZipFile(archive, 'a') as zip:
            zip.writestr(name, contents)

    def delete(self, archive, name):
        fd, tmp = tempfile.mkstemp()
        try:
            shutil.copy(archive, tmp)
            with ZipFile(tmp, 'r') as old_zip:
                with ZipFile(archive, 'w') as new_zip:
                    for member in old_zip.namelist():
                        if member != name:
                            new_zip.writestr(member, old_zip.read(member))
        except:
            os.close(fd)
            os.unlink(tmp)
