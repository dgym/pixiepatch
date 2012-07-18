import urllib2


class Reader(object):
    def get(self, version, name):
        raise IOError()


class URLReader(Reader):
    def __init__(self, prefix='', format_string=None, chunk_size=None, report_callback=None):
        self.prefix = prefix
        self.format_string = format_string
        self.chunk_size = chunk_size
        self.report_callback = report_callback

    def get(self, version, name):
        try:
            if self.format_string:
                url = self.format_string.format(version=version, name=name)
            else:
                url = self.prefix + version + '/' + name

            with urlopen(url) as f:
                if self.chunk_size and self.report_callback:
                    contents = ''
                    while True:
                        some = f.read(self.chunk_size)
                        if len(some) < 1:
                            return contents
                        self.report_callback(len(some))
                        contents += some
                else:
                    return f.read()
        except urllib2.URLError:
            raise IOError()


class urlopen(object):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        self.file = urllib2.urlopen(*self.args, **self.kwargs)
        return self.file

    def __exit__(self, type, value, traceback):
        self.file.close()
