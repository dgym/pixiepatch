import urllib


class Reader(object):
    def get(self, version, name):
        raise IOError()


class URLReader(Reader):
    def __init__(self, prefix):
        self.prefix = prefix

    def get(self, version, name):
        with urlopen(self.prefix + version + '/' + name) as f:
            return f.read()


class urlopen(object):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        self.file = urllib.urlopen(*self.args, **self.kwargs)
        return self.file

    def __exit__(self, type, value, traceback):
        self.file.close()
