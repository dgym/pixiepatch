class VerificationError(Exception):
    pass


class Signer(object):
    '''A digital signature interface.'''

    def sign(self, contents):
        '''Signs a message and returns the message and signature.'''
        return contents

    def verify(self, contents):
        '''Verifies a signed message and returns the original message.

        Raises a VerificationError if the signature is not valid.'''
        return contents
