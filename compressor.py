class Compressor(object):
    '''A file compression interface.'''

    def compress(self, contents):
        return contents

    def decompress(self, contents):
        return contents

    def add_extension(self, filename):
        return filename + self.compressed_extension

    def remove_extension(self, filename):
        if self.compressed_extension and filename.endswith(self.compressed_extension):
            return filename[:-len(self.compressed_extension)]

    compressed_extension = ''
