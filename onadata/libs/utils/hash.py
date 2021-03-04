# coding: utf-8
import hashlib
import os
from typing import Union, BinaryIO

import requests
from django.conf import settings


def get_hash(source: Union[str, bytes, BinaryIO],
             algorithm: str = 'md5',
             prefix: bool = False,
             fast: bool = False) -> str:
    """
    Calculates the hash for an object.

    :param source: string, bytes or FileObject. Files must be opened in binary mode  # noqa
    :param algorithm: Can be 'md5' or 'sha1'. Default: 'md5'.
    :param prefix: Prefix the return value with the algorithm, e.g.: 'md5:34523'
    :param fast: If True, only calculate on 3 small pieces of the object.
                 Useful with big (remote) files.
    """

    supported_algorithm = ['md5', 'sha1']

    if algorithm not in supported_algorithm:
        raise NotImplementedError('Only `{algorithms}` are supported'.format(
            algorithms=', '.join(supported_algorithm)
        ))

    if algorithm == 'md5':
        hashlib_def = hashlib.md5
    else:
        hashlib_def = hashlib.sha1

    def _prefix_hash(hex_digest: str) -> str:
        if prefix:
            return f'{algorithm}:{hex_digest}'
        return hex_digest

    # If `source` is a string, it can be a URL or real string
    if isinstance(source, str):
        if not source.startswith('http'):
            hashable = source.encode()
        else:
            # Ensure we do not receive a gzip response.
            headers = {'Accept-Encoding': None}
            # Get remote file size
            # `requests.get(url, stream=True)` only gets headers. Body is
            # only retrieved when `response.content` is called.
            # It avoids making a second request to get the body
            # (i.e.: vs `requests.head()`).
            response = requests.get(source, stream=True, headers=headers)
            response.raise_for_status()
            file_size = int(response.headers['Content-Length'])
            # If the remote file is smaller than the threshold or smaller than
            # 3 times the chunk, we retrieve the whole file to avoid extra
            # requests.
            if (
                not fast
                or file_size < settings.HASH_BIG_FILE_SIZE_THRESHOLD
                or file_size < 3 * settings.HASH_BIG_FILE_CHUNK
            ):
                hashable = response.content
            else:
                # We fetch 3 parts of the file.
                # - One chunk at the beginning
                # - One chunk in the middle
                # - One chunk at the end
                # It should be accurate enough to detect whether big files
                # over the network have changed without locking uWSGI workers
                # for a long time.
                # Drawback on this solution, it relies on the remote server to
                # support `Accept-Ranges`. If it does not, it returns the whole
                # file. In that case, we calculate on the URL itself, not its
                # content

                # 1) First part
                range_ = f'0-{settings.HASH_BIG_FILE_CHUNK - 1}'
                headers['Range'] = f'bytes={range_}'
                response = requests.get(source, stream=True, headers=headers)
                response.raise_for_status()
                try:
                    response.headers['Content-Range']
                except KeyError:
                    # Remove server does not support ranges
                    hex_digest = hashlib_def(source.encode()).hexdigest()
                    return _prefix_hash(hex_digest=hex_digest)

                hashable = response.content

                # 2) Second part
                range_lower_bound = file_size // 2
                range_upper_bound = (range_lower_bound
                                     + settings.HASH_BIG_FILE_CHUNK - 1)
                range_ = f'{range_lower_bound}-{range_upper_bound}'
                headers['Range'] = f'bytes={range_}'
                response = requests.get(source, headers=headers)
                response.raise_for_status()
                hashable += response.content

                # 3) Last part
                range_lower_bound = file_size - settings.HASH_BIG_FILE_CHUNK
                range_upper_bound = file_size - 1
                range_ = f'{range_lower_bound}-{range_upper_bound}'
                headers['Range'] = f'bytes={range_}'
                response = requests.get(source, headers=headers)
                response.raise_for_status()
                hashable += response.content

        return _prefix_hash(hashlib_def(hashable).hexdigest())

    try:
        source.read(settings.HASH_BIG_FILE_CHUNK)
    except AttributeError:
        # Source is `bytes`, just return its hash
        return _prefix_hash(hashlib_def(source).hexdigest())

    # Get local file size
    source.seek(0, os.SEEK_END)
    file_size = source.tell()
    source.seek(0, os.SEEK_SET)

    # If the local file is smaller than the threshold or smaller than
    # 3 times the chunk, we retrieve the whole file to avoid error when seeking
    # out of bounds.
    if (
        not fast
        or file_size < settings.HASH_BIG_FILE_SIZE_THRESHOLD
        or file_size < 3 * settings.HASH_BIG_FILE_CHUNK
    ):
        hashable = hashlib_def()
        while chunk := source.read(settings.HASH_BIG_FILE_CHUNK):
            hashable.update(chunk)

        return _prefix_hash(hashable.hexdigest())

    hashable = source.read(settings.HASH_BIG_FILE_CHUNK)
    source.seek(file_size // 2, os.SEEK_SET)
    hashable += source.read(settings.HASH_BIG_FILE_CHUNK)
    source.seek(-settings.HASH_BIG_FILE_CHUNK, os.SEEK_END)
    hashable += source.read(settings.HASH_BIG_FILE_CHUNK)

    return _prefix_hash(hashlib_def(hashable).hexdigest())
