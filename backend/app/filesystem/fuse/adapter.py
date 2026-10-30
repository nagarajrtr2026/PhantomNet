import errno
import importlib.util
import os
import stat
import sys
import time
from typing import Any

from app.filesystem.virtual_fs import VirtualFilesystem
from app.services.llm import LLMUnavailableError


FUSE_AVAILABLE = sys.platform == "linux" and importlib.util.find_spec("pyfuse3") is not None

if FUSE_AVAILABLE:
    import pyfuse3

    class PhantomFuseOperations(pyfuse3.Operations):
        def __init__(self, filesystem: VirtualFilesystem, session_id: str) -> None:
            super().__init__()
            self.filesystem = filesystem
            self.session_id = session_id
            self.inodes: dict[int, str] = {pyfuse3.ROOT_INODE: ""}
            self.paths: dict[str, int] = {"": pyfuse3.ROOT_INODE}
            self.next_inode = pyfuse3.ROOT_INODE + 1

        def _inode(self, path: str) -> int:
            if path not in self.paths:
                self.paths[path] = self.next_inode
                self.inodes[self.next_inode] = path
                self.next_inode += 1
            return self.paths[path]

        def _attributes(self, inode: int, is_directory: bool, size: int = 0) -> Any:
            attributes = pyfuse3.EntryAttributes()
            attributes.st_ino = inode
            attributes.st_mode = (stat.S_IFDIR | 0o555) if is_directory else (stat.S_IFREG | 0o444)
            attributes.st_nlink = 2 if is_directory else 1
            attributes.st_size = size
            attributes.st_ctime_ns = attributes.st_mtime_ns = attributes.st_atime_ns = int(time.time() * 1e9)
            attributes.st_uid = os.getuid()
            attributes.st_gid = os.getgid()
            attributes.st_blksize = 4096
            attributes.st_blocks = (size + 511) // 512
            attributes.generation = 0
            attributes.entry_timeout = 1
            attributes.attr_timeout = 1
            return attributes

        async def lookup(self, parent_inode: int, name: bytes, ctx: Any) -> Any:
            del ctx
            parent = self.inodes.get(parent_inode)
            if parent is None:
                raise pyfuse3.FUSEError(errno.ENOENT)
            try:
                child = await self.filesystem.stat(
                    self.session_id, f"{parent}/{name.decode('utf-8')}".strip("/")
                )
            except LLMUnavailableError:
                raise pyfuse3.FUSEError(errno.EIO) from None
            except (UnicodeDecodeError, ValueError):
                raise pyfuse3.FUSEError(errno.EINVAL) from None
            inode = self._inode(child.path)
            return self._attributes(inode, child.is_directory, len((child.content or "").encode()))

        async def getattr(self, inode: int, ctx: Any = None) -> Any:
            del ctx
            path = self.inodes.get(inode)
            if path is None:
                raise pyfuse3.FUSEError(errno.ENOENT)
            try:
                node = await self.filesystem.stat(self.session_id, path)
            except LLMUnavailableError:
                raise pyfuse3.FUSEError(errno.EIO) from None
            except (ValueError, LookupError):
                raise pyfuse3.FUSEError(errno.ENOENT) from None
            return self._attributes(inode, node.is_directory, len((node.content or "").encode()))

        async def opendir(self, inode: int, ctx: Any) -> int:
            del ctx
            try:
                node = await self.filesystem.stat(self.session_id, self.inodes[inode])
                if not node.is_directory:
                    raise pyfuse3.FUSEError(errno.ENOTDIR)
                return inode
            except LLMUnavailableError:
                raise pyfuse3.FUSEError(errno.EIO) from None
            except KeyError:
                raise pyfuse3.FUSEError(errno.ENOENT) from None

        async def readdir(self, fh: int, start_id: int, token: Any) -> None:
            path = self.inodes.get(fh)
            if path is None:
                raise pyfuse3.FUSEError(errno.ENOENT)
            try:
                names = await self.filesystem.list_directory(self.session_id, path)
            except LLMUnavailableError:
                raise pyfuse3.FUSEError(errno.EIO) from None
            for index, name in enumerate(names, start=1):
                if index <= start_id:
                    continue
                child_path = f"{path}/{name}" if path else name
                try:
                    node = await self.filesystem.stat(self.session_id, child_path)
                except LLMUnavailableError:
                    raise pyfuse3.FUSEError(errno.EIO) from None
                inode = self._inode(child_path)
                if not pyfuse3.readdir_reply(
                    token,
                    name.encode("utf-8"),
                    self._attributes(inode, node.is_directory, len((node.content or "").encode())),
                    index,
                ):
                    break

        async def open(self, inode: int, flags: int, ctx: Any) -> Any:
            del flags, ctx
            path = self.inodes.get(inode)
            if path is None:
                raise pyfuse3.FUSEError(errno.ENOENT)
            try:
                node = await self.filesystem.stat(self.session_id, path)
                if node.is_directory:
                    raise pyfuse3.FUSEError(errno.EISDIR)
            except LLMUnavailableError:
                raise pyfuse3.FUSEError(errno.EIO) from None
            except LookupError:
                raise pyfuse3.FUSEError(errno.ENOENT) from None
            return pyfuse3.FileInfo(fh=inode)

        async def read(self, fh: int, off: int, size: int) -> bytes:
            path = self.inodes.get(fh)
            if path is None:
                raise pyfuse3.FUSEError(errno.ENOENT)
            try:
                content = await self.filesystem.read_file(self.session_id, path)
            except LLMUnavailableError:
                raise pyfuse3.FUSEError(errno.EIO) from None
            except IsADirectoryError:
                raise pyfuse3.FUSEError(errno.EISDIR) from None
            return content.encode("utf-8")[off : off + size]

    async def mount_filesystem(
        filesystem: VirtualFilesystem, session_id: str, mountpoint: str
    ) -> None:
        operations = PhantomFuseOperations(filesystem, session_id)
        options = set(pyfuse3.default_options)
        options.add("fsname=phantomnet")
        pyfuse3.init(operations, mountpoint, options)
        try:
            await pyfuse3.main()
        finally:
            pyfuse3.close(unmount=True)
else:

    class PhantomFuseOperations:
        def __init__(self, filesystem: VirtualFilesystem, session_id: str) -> None:
            del filesystem, session_id
            raise RuntimeError("FUSE mounting is supported only on Linux with pyfuse3 installed.")

    async def mount_filesystem(
        filesystem: VirtualFilesystem, session_id: str, mountpoint: str
    ) -> None:
        del filesystem, session_id, mountpoint
        raise RuntimeError("FUSE mounting is supported only on Linux with pyfuse3 installed.")
