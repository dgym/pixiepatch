class DiffError(Exception):
    pass


class Differ(object):
    '''A diff interface.'''

    def diff(self, source, target):
        raise DiffError()

    def patch(self, source, patch):
        raise DiffError()

    def add_extension(self, filename):
        return filename + self.extension

    def remove_extension(self, filename):
        if self.extension and filename.endswith(self.extension):
            return filename[:-len(self.extension)]

    extension = ''
