from os import stat, link, unlink, walk, makedirs, sep
from os.path import join, dirname, exists, relpath
import simplejson
import hashlib
import re

from compressor import Compressor
from signer import Signer, VerificationError
from differ import Differ, DiffError
from reader import Reader


class PixiePatch(object):
    def __init__(self, compressor=None, differ=None, signer=None, reader=None):
        self.compressor = compressor or Compressor()
        self.differ = differ or Differ()
        self.signer = signer or Signer()
        self.reader = reader or Reader()
        self.archive_handlers = {}
        self.ignore = []

    def register_archive_handler(self, extension, handler):
        self.archive_handlers[extension] = handler

    def register_ignore_pattern(self, pattern):
        if isinstance(pattern, basestring):
            pattern = re.compile(pattern)
        self.ignore.append(pattern)

    def make_distribution(self, version, source_dir, target_dir, previous_target_dir=None):
        previous_manifest = None
        if previous_target_dir:
            with open(join(previous_target_dir, self.compressor.add_extension('manifest')), 'r') as f:
                previous_manifest = self.parse_manifest(f.read())

        entries = {}
        for rel_name, contents in self.__walk(source_dir):
            hash = hashlib.sha256(contents).hexdigest()
            dest_name = self.compressor.add_extension(join(target_dir, rel_name))
            delta_name = self.differ.add_extension(join(target_dir, rel_name))
            ensure_dir(dirname(dest_name))

            linked = False
            delta = None
            compressed = None

            if previous_manifest:
                previous_name = self.compressor.add_extension(join(previous_target_dir, rel_name))
                last = previous_manifest['files'].get(rel_name)
                if last and last['hash'] == hash:
                    # file not changed
                    if exists(dest_name):
                        unlink(dest_name)
                    link(previous_name, dest_name)
                    linked = True
                    compressed_size = stat(dest_name).st_size
                    delta = last['delta']
                elif last:
                    # create a diff
                    try:
                        with open(previous_name, 'r') as f:
                            previous_contents = self.compressor.decompress(f.read())
                        delta_contents = self.compressor.compress(self.differ.diff(previous_contents, contents))
                        size = len(delta_contents)

                        compressed = self.compressor.compress(contents)
                        if size < len(compressed):
                            with open(delta_name, 'w') as f:
                                f.write(delta_contents)
                            delta = {'version': version, 'size': size, 'old_hash': last['hash'], 'old_version': last['delta'] and last['delta']['version']}
                    except DiffError:
                        pass

                
            if not linked:
                if compressed is None:
                    compressed = self.compressor.compress(contents)
                compressed_size = len(compressed)
                with open(dest_name, 'w') as f:
                    f.write(compressed)

                if delta and delta['size'] >= compressed_size:
                    delta = None

            entries[rel_name] = {'hash': hash, 'dlsize': compressed_size, 'delta': delta}

        manifest = {}
        manifest['version'] = version
        manifest['files'] = entries
        manifest = simplejson.dumps(manifest, sort_keys=True, indent=4) + '\n'

        with open(join(target_dir, self.compressor.add_extension('manifest')), 'w') as f:
            f.write(self.compressor.compress(self.signer.sign(manifest)))

        with open(join(target_dir, 'version'), 'w') as f:
            f.write(version + '\n')

    def parse_manifest(self, manifest):
        decomp = self.compressor.decompress(manifest)
        message = self.signer.verify(decomp)
        return simplejson.loads(message)

    def read_manifest(self, filename):
        with open(filename, 'r') as f:
            return self.parse_manifest(f.read())

    def create_client_manifest(self, version, source_dir):
        entries = {}
        for rel_name, contents in self.__walk(source_dir):
            hash = hashlib.sha256(contents).hexdigest()
            entries[rel_name] = {'hash': hash}

        manifest = {}
        manifest['version'] = version
        manifest['files'] = entries
        return manifest

    def get_patch_plan(self, client_manifest, target_version):
        manifests = {}
        def get_manifest(version):
            if version in manifests:
                return manifests[version]
            try:
                contents = self.reader.get(version, self.compressor.add_extension('manifest'))
            except IOError:
                return
            contents = self.compressor.decompress(contents)
            contents = self.signer.verify(contents)
            contents = simplejson.loads(contents)
            manifests[version] = contents
            return contents

        if client_manifest['version'] == target_version:
            return

        target_manifest = get_manifest(target_version)
        if not target_manifest:
            raise IOError()

        local = set(client_manifest['files'].keys())
        remote = set(target_manifest['files'].keys())
        local_only = local.difference(remote)
        remote_only = remote.difference(local)
        common = local.intersection(remote)

        delete = list(local_only)
        download = list(remote_only)
        patch = []
        size = sum([target_manifest['files'][file]['dlsize'] for file in remote_only])

        for name in common:
            local = client_manifest['files'][name]
            remote = target_manifest['files'][name]
            if local['hash'] != remote['hash']:
                chain = []
                if remote['delta']:
                    delta = remote['delta']
                    # chain patches if required
                    old_manifest = target_manifest
                    chain = [delta['version']]
                    chain_size = delta['size']
                    while delta['old_hash'] != local['hash']:
                        m = delta['old_version'] and get_manifest(delta['old_version'])
                        if m and name in m['files'] and m['files'][name].get('delta'):
                            delta = m['files'][name].get('delta')
                            chain.insert(0, delta['version'])
                            chain_size += delta['size']

                            # give up on deltas if they are bigger than the whole
                            # file
                            if chain_size >= remote['dlsize']:
                                chain = []
                                break
                        else:
                            chain = []
                            break
                    
                if chain:
                    patch.append((name, chain))
                    size += chain_size
                else:
                    download.append(name)
                    size += remote['dlsize']

        return {'delete': delete, 'download': download, 'patch': patch, 'size': size, 'manifest': target_manifest}


    def patch(self, directory, patch_plan):
        manifest = patch_plan['manifest']
        version = manifest['version']

        # delete entries
        for name in patch_plan['delete']:
            handler, archive, member = self.__get_file_handler(directory, name)
            handler.delete(archive, member)

        # download new entries
        for name in patch_plan['download']:
            contents = self.reader.get(version, self.compressor.add_extension(name))
            contents = self.compressor.decompress(contents)
            if hashlib.sha256(contents).hexdigest() != manifest['files'][name]['hash']:
                raise VerificationError()
            handler, archive, member = self.__get_file_handler(directory, name)
            handler.set(archive, member, contents)

        # download patches
        for name, versions in patch_plan['patch']:
            handler, archive, member = self.__get_file_handler(directory, name)
            contents = handler.get(archive, member)

            for v in versions:
                patch = self.reader.get(v, self.differ.add_extension(name))
                patch = self.compressor.decompress(patch)
                contents = self.differ.patch(contents, patch)

            if hashlib.sha256(contents).hexdigest() != manifest['files'][name]['hash']:
                raise VerificationError()
            handler.set(archive, member, contents)

    def __walk(self, source_dir):
        for root, dirs, files in walk(source_dir):
            for file in files:
                name = join(root, file)
                rel_name = relpath(name, source_dir)

                for ext, handler in self.archive_handlers.items():
                    if name.endswith(ext):
                        for member, contents in handler.walk(name):
                            member_name = join(rel_name, member)
                            if not self.__ignore(member_name):
                                yield member_name, contents
                        break
                else:
                    if not self.__ignore(rel_name):
                        with open(name, 'r') as f:
                            contents = f.read()
                        yield rel_name, contents

    def __ignore(self, name):
        for pattern in self.ignore:
            if pattern.match(name):
                return True
        return False

    def __get_file_handler(self, directory, name):
        parts = name.split(sep)
        for i, part in enumerate(parts):
            for ext, handler in self.archive_handlers.items():
                if part.endswith(ext):
                    return handler, join(directory, *parts[:i+1]), join(*parts[i+1:])
        return DummyHandler(), None, join(directory, name)


def ensure_dir(name):
    if name and not exists(name):
        makedirs(name)


class DummyHandler(object):
    def get(self, archive, name):
        with open(name, 'r') as f:
            return f.read()

    def set(self, archive, name, contents):
        ensure_dir(dirname(name))
        with open(name, 'w') as f:
            f.write(contents)

    def delete(self, archive, name):
        unlink(name)
