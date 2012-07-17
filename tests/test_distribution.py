from os import mkdir, stat
from os.path import join, exists
import tempfile
import shutil
import sys
import hashlib
import bz2
from zipfile import ZipFile
from nose.tools import *

from pixiepatch import *
from pixiepatch.bz2compressor import BZ2Compressor
from pixiepatch.ziphandler import ZIPHandler


class Base(object):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.sources = join(self.dir, 'source-1'), join(self.dir, 'source-2')
        self.dists = join(self.dir, 'dist-1'), join(self.dir, 'dist-2')
        for name in self.sources + self.dists:
            mkdir(name)

    def tearDown(self):
        shutil.rmtree(self.dir)


class TestPlainEmpty(Base):
    def setUp(self):
        Base.setUp(self)
        self.pp = PixiePatch()
        self.pp.make_distribution('1', self.sources[0], self.dists[0])

    def test_version(self):
        version_file = join(self.dists[0], 'version')
        assert exists(version_file)
        with open(version_file, 'r') as f:
            assert f.read() == '1\n'
    
    def test_manifest(self):
        manifest_file = join(self.dists[0], 'manifest')
        assert exists(manifest_file)
        manifest = self.pp.read_manifest(manifest_file)
        assert manifest['version'] == '1'
        assert len(manifest['files']) == 0


class TestPlainSingle(Base):
    def setUp(self):
        Base.setUp(self)
        self.pp = PixiePatch()
        with open(join(self.sources[0], 'a'), 'w') as f:
            f.write('test\n' * 100)
        self.pp.make_distribution('1', self.sources[0], self.dists[0])

    def test_version(self):
        version_file = join(self.dists[0], 'version')
        assert exists(version_file)
        with open(version_file, 'r') as f:
            assert f.read() == '1\n'
    
    def test_manifest(self):
        manifest_file = join(self.dists[0], 'manifest')
        assert exists(manifest_file)
        manifest = self.pp.read_manifest(manifest_file)
        assert manifest['version'] == '1'
        assert len(manifest['files']) == 1
        a = manifest['files']['a']
        assert a['hash'] == hashlib.sha256('test\n' * 100).hexdigest()
        assert a['dlsize'] == 500
        assert a['delta'] is None
        with open(join(self.dists[0], 'a'), 'r') as f:
                assert f.read() == 'test\n' * 100


class TestPlainDelta(Base):
    def setUp(self):
        Base.setUp(self)
        self.pp = PixiePatch()
        with open(join(self.sources[0], 'a'), 'w') as f:
            f.write('test\n' * 100)
        with open(join(self.sources[0], 'b'), 'w') as f:
            f.write('v1\n' * 100)
        with open(join(self.sources[1], 'a'), 'w') as f:
            f.write('test\n' * 100)
        with open(join(self.sources[1], 'b'), 'w') as f:
            f.write('v2\n' * 100)
        self.pp.make_distribution('1', self.sources[0], self.dists[0])
        self.pp.make_distribution('2', self.sources[1], self.dists[1], self.dists[0])

    def test_version(self):
        version_file = join(self.dists[1], 'version')
        assert exists(version_file)
        with open(version_file, 'r') as f:
            assert f.read() == '2\n'
    
    def test_manifest(self):
        manifest_file = join(self.dists[1], 'manifest')
        assert exists(manifest_file)
        manifest = self.pp.read_manifest(manifest_file)
        assert manifest['version'] == '2'
        assert len(manifest['files']) == 2
        a = manifest['files']['a']
        assert a['hash'] == hashlib.sha256('test\n' * 100).hexdigest()
        assert a['dlsize'] == 500
        assert a['delta'] is None
        b = manifest['files']['b']
        assert b['hash'] == hashlib.sha256('v2\n' * 100).hexdigest()
        assert b['dlsize'] == 300
        assert b['delta'] is None


class SimpleSigner(Signer):
    def __init__(self, sig):
        self.sig = sig

    def sign(self, contents):
        return contents + self.sig

    def verify(self, contents):
        if not contents.endswith(self.sig):
            raise VerificationError()
        return contents[:-len(self.sig)]


class TestSigner(Base):
    def setUp(self):
        Base.setUp(self)
        self.pp = PixiePatch(signer=SimpleSigner('valid'))
        self.pp.make_distribution('1', self.sources[0], self.dists[0])

    def test_manifest(self):
        manifest_file = join(self.dists[0], 'manifest')
        assert exists(manifest_file)
        with open(manifest_file, 'r') as f:
            assert f.read().endswith('valid')
        manifest = self.pp.read_manifest(manifest_file)
        assert manifest['version'] == '1'
        assert len(manifest['files']) == 0

    @raises(VerificationError)
    def test_verification(self):
        try:
            self.pp.signer.sig = 'invalid'
            manifest_file = join(self.dists[0], 'manifest')
            self.pp.read_manifest(manifest_file)
        finally:
            self.pp.signer.sig = 'valid'


class TestCompressor(Base):
    def setUp(self):
        Base.setUp(self)
        with open(join(self.sources[0], 'a'), 'w') as f:
            f.write('test\n' * 100)
        self.pp = PixiePatch(compressor=BZ2Compressor())
        self.pp.make_distribution('1', self.sources[0], self.dists[0])

    def test_compressed(self):
        file = join(self.dists[0], 'a.bz2')
        assert exists(file)
        file_size = stat(file).st_size
        assert file_size < 500

        manifest_file = join(self.dists[0], 'manifest.bz2')
        manifest = self.pp.read_manifest(manifest_file)
        assert manifest['files']['a']['dlsize'] == file_size


class TestZipHandler(Base):
    def setUp(self):
        Base.setUp(self)
        with ZipFile(join(self.sources[0], 'a.zip'), 'w') as f:
            f.writestr('a', 'test\n' * 100)
            f.writestr('b', 'b\n' * 100)
        self.pp = PixiePatch()
        self.pp.register_archive_handler('.zip', ZIPHandler())
        self.pp.make_distribution('1', self.sources[0], self.dists[0])

    def test_archives(self):
        file = join(self.dists[0], 'a.zip', 'a')
        assert exists(file)
        with open(file, 'r') as f:
            assert f.read() == 'test\n' * 100

        manifest_file = join(self.dists[0], 'manifest')
        manifest = self.pp.read_manifest(manifest_file)
        assert len(manifest['files']) == 2
