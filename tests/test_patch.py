from os import mkdir, stat
from os.path import join, exists
import tempfile
import shutil
import sys
import hashlib
import bz2
import difflib
from zipfile import ZipFile
from subprocess import Popen, PIPE

from nose.tools import *
import unittest

from pixiepatch import *
from pixiepatch.bz2compressor import BZ2Compressor
from pixiepatch.ziphandler import ZIPHandler
from pixiepatch.reader import URLReader


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.sources = [join(self.dir, 'source-%i' % i) for i in range(1, 4)]
        self.dists = [join(self.dir, 'dist-%i' % i) for i in range(1, 4)]
        for name in self.sources + self.dists:
            mkdir(name)

    def tearDown(self):
        shutil.rmtree(self.dir)


class TextDiffer(Differ):
    def diff(self, source, target):
        return '\n'.join(difflib.unified_diff(source.split('\n'), target.split('\n')))

    def patch(self, source, patch):
        with tempfile.NamedTemporaryFile('w') as f:
            f.write(source)
            f.flush()
            return Popen(['patch', '-o', '-', f.name], stdin=PIPE, stdout=PIPE, stderr=PIPE).communicate(patch)[0]

    extension = '.patch'


class TestPatch(Base):
    def setUp(self):
        Base.setUp(self)
        self.pp = PixiePatch(differ=TextDiffer(), reader=URLReader(self.dir + '/dist-'))

        with open(join(self.sources[0], 'a'), 'w') as f:
            f.write('test\n' * 100)
        with open(join(self.sources[0], 'b'), 'w') as f:
            f.write('v1\n' * 100)
        with open(join(self.sources[0], 'c'), 'w') as f:
            f.write(''.join(['test %i\n' % i for i in range(100)]))
            f.write('v1\n')
        with open(join(self.sources[0], 'd'), 'w') as f:
            f.write('test\n' * 100)
        with open(join(self.sources[0], 'e'), 'w') as f:
            f.write(''.join(['test %i\n' % i for i in range(100)]))
            f.write('v1\n')

        with open(join(self.sources[1], 'a'), 'w') as f:
            f.write('test\n' * 100)
        with open(join(self.sources[1], 'b'), 'w') as f:
            f.write('v2\n' * 100)
        with open(join(self.sources[1], 'c'), 'w') as f:
            f.write(''.join(['test %i\n' % i for i in range(100)]))
            f.write('v2\n')
        with open(join(self.sources[1], 'e'), 'w') as f:
            f.write(''.join(['test %i\n' % i for i in range(100)]))
            f.write('v2\n')
        with open(join(self.sources[1], 'f'), 'w') as f:
            f.write('test\n' * 100)

        with open(join(self.sources[2], 'a'), 'w') as f:
            f.write('test\n' * 100)
        with open(join(self.sources[2], 'b'), 'w') as f:
            f.write('v2\n' * 100)
        with open(join(self.sources[2], 'c'), 'w') as f:
            f.write(''.join(['test %i\n' % i for i in range(100)]))
            f.write('v3\n')
        with open(join(self.sources[2], 'e'), 'w') as f:
            f.write(''.join(['test %i\n' % i for i in range(100)]))
            f.write('v2\n')
        with open(join(self.sources[2], 'f'), 'w') as f:
            f.write('test\n' * 100)

        self.pp.make_distribution('1', self.sources[0], self.dists[0])
        self.pp.make_distribution('2', self.sources[1], self.dists[1], self.dists[0])
        self.pp.make_distribution('3', self.sources[2], self.dists[2], self.dists[1])

    def test_plans(self):
        # version 1 -> 2
        client_manifest = self.pp.create_client_manifest('1', self.sources[0])
        plan = self.pp.get_patch_plan(client_manifest, '2')
        assert set(plan['download']) == set(['b', 'f'])
        assert set(plan['delete']) == set(['d'])
        assert set([p[0] for p in plan['patch']]) == set(['c', 'e'])

        # version 2 -> 3
        client_manifest = self.pp.create_client_manifest('2', self.sources[1])
        plan = self.pp.get_patch_plan(client_manifest, '3')
        assert set(plan['download']) == set([])
        assert set(plan['delete']) == set([])
        assert set([p[0] for p in plan['patch']]) == set(['c'])
        assert plan['patch'][0][1] == ['3']


        # version 1 -> 3
        client_manifest = self.pp.create_client_manifest('1', self.sources[0])
        plan = self.pp.get_patch_plan(client_manifest, '3')
        assert set(plan['download']) == set(['b', 'f'])
        assert set(plan['delete']) == set(['d'])
        assert set([p[0] for p in plan['patch']]) == set(['c', 'e'])
        for name, chain in plan['patch']:
            if name == 'c':
                assert chain == ['2', '3']
            else:
                assert chain == ['2']

    def test_patch_1_to_2(self):
        client_manifest = self.pp.create_client_manifest('1', self.sources[0])
        plan = self.pp.get_patch_plan(client_manifest, '2')
        self.pp.patch(self.sources[0], plan)
        diff = Popen(['diff', '-ru', self.sources[0], self.sources[1]], stdout=PIPE).communicate()[0]
        self.assertEqual(diff, '')

    def test_patch_2_to_3(self):
        client_manifest = self.pp.create_client_manifest('2', self.sources[1])
        plan = self.pp.get_patch_plan(client_manifest, '3')
        self.pp.patch(self.sources[1], plan)
        diff = Popen(['diff', '-ru', self.sources[1], self.sources[2]], stdout=PIPE).communicate()[0]
        self.assertEqual(diff, '')

    def test_patch_1_to_3(self):
        client_manifest = self.pp.create_client_manifest('1', self.sources[0])
        plan = self.pp.get_patch_plan(client_manifest, '3')
        self.pp.patch(self.sources[0], plan)
        diff = Popen(['diff', '-ru', self.sources[0], self.sources[2]], stdout=PIPE).communicate()[0]
        self.assertEqual(diff, '')


class TestZipPatch(Base):
    def setUp(self):
        Base.setUp(self)
        self.pp = PixiePatch(differ=TextDiffer(), reader=URLReader(self.dir + '/dist-'))
        self.pp.register_archive_handler('.zip', ZIPHandler())

        with ZipFile(join(self.sources[0], 'a.zip'), 'w') as f:
            f.writestr('a', 'test\n' * 100)
            f.writestr('b', 'v1\n' * 100)
            f.writestr('c', ''.join(['test %i\n' % i for i in range(100)]) + 'v1\n')
            f.writestr('d','test\n' * 100)
            f.writestr('e', ''.join(['test %i\n' % i for i in range(100)]) + 'v1\n')

        with ZipFile(join(self.sources[1], 'a.zip'), 'w') as f:
            f.writestr('a', 'test\n' * 100)
            f.writestr('b', 'v2\n' * 100)
            f.writestr('c', ''.join(['test %i\n' % i for i in range(100)]) + 'v2\n')
            f.writestr('e', ''.join(['test %i\n' % i for i in range(100)]) + 'v2\n')
            f.writestr('f', 'test\n' * 100)

        with ZipFile(join(self.sources[2], 'a.zip'), 'w') as f:
            f.writestr('a', 'test\n' * 100)
            f.writestr('b', 'v2\n' * 100)
            f.writestr('c', ''.join(['test %i\n' % i for i in range(100)]) + 'v3\n')
            f.writestr('e', ''.join(['test %i\n' % i for i in range(100)]) + 'v2\n')
            f.writestr('f', 'test\n' * 100)

        self.pp.make_distribution('1', self.sources[0], self.dists[0])
        self.pp.make_distribution('2', self.sources[1], self.dists[1], self.dists[0])
        self.pp.make_distribution('3', self.sources[2], self.dists[2], self.dists[1])

    def read_zip(self, archive):
        entries = set()
        with ZipFile(archive, 'r') as zip:
            for name in zip.namelist():
                info = zip.getinfo(name)
                entries.add((name, info.CRC))
        return entries

    def test_plans(self):
        # version 1 -> 2
        client_manifest = self.pp.create_client_manifest('1', self.sources[0])
        plan = self.pp.get_patch_plan(client_manifest, '2')
        assert set(plan['download']) == set(['a.zip/b', 'a.zip/f'])
        assert set(plan['delete']) == set(['a.zip/d'])
        assert set([p[0] for p in plan['patch']]) == set(['a.zip/c', 'a.zip/e'])

        # version 2 -> 3
        client_manifest = self.pp.create_client_manifest('2', self.sources[1])
        plan = self.pp.get_patch_plan(client_manifest, '3')
        assert set(plan['download']) == set([])
        assert set(plan['delete']) == set([])
        assert set([p[0] for p in plan['patch']]) == set(['a.zip/c'])
        assert plan['patch'][0][1] == ['3']


        # version 1 -> 3
        client_manifest = self.pp.create_client_manifest('1', self.sources[0])
        plan = self.pp.get_patch_plan(client_manifest, '3')
        assert set(plan['download']) == set(['a.zip/b', 'a.zip/f'])
        assert set(plan['delete']) == set(['a.zip/d'])
        assert set([p[0] for p in plan['patch']]) == set(['a.zip/c', 'a.zip/e'])
        for name, chain in plan['patch']:
            if name == 'a.zip/c':
                assert chain == ['2', '3']
            else:
                assert chain == ['2']

    def test_patch_1_to_2(self):
        client_manifest = self.pp.create_client_manifest('1', self.sources[0])
        plan = self.pp.get_patch_plan(client_manifest, '2')
        self.pp.patch(self.sources[0], plan)
        patched = self.read_zip(join(self.sources[0], 'a.zip'))
        target = self.read_zip(join(self.sources[1], 'a.zip'))
        self.assertEqual(patched, target)

    def test_patch_2_to_3(self):
        client_manifest = self.pp.create_client_manifest('2', self.sources[1])
        plan = self.pp.get_patch_plan(client_manifest, '3')
        self.pp.patch(self.sources[1], plan)
        patched = self.read_zip(join(self.sources[1], 'a.zip'))
        target = self.read_zip(join(self.sources[2], 'a.zip'))
        self.assertEqual(patched, target)

    def test_patch_1_to_3(self):
        client_manifest = self.pp.create_client_manifest('1', self.sources[0])
        plan = self.pp.get_patch_plan(client_manifest, '3')
        self.pp.patch(self.sources[0], plan)
        patched = self.read_zip(join(self.sources[0], 'a.zip'))
        target = self.read_zip(join(self.sources[2], 'a.zip'))
        self.assertEqual(patched, target)
