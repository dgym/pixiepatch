import bz2

from compressor import Compressor

class BZ2Compressor(Compressor):
    def compress(self, contents):
        return bz2.compress(contents)

    def decompress(self, contents):
        return bz2.decompress(contents)

    compressed_extension = '.bz2'
