#!/usr/bin/env python3
"""Race-safe, repository-contained filesystem access for docdna helpers."""

import hashlib
import errno
import json
import os
import secrets
import stat

_LISTDIR = os.listdir
_LISTDIR_SUPPORTED = _LISTDIR in os.supports_fd
MAX_CONTROL_BYTES = 5 * 1024 * 1024
MANIFEST_STAGES = ("frame", "decide", "design", "build", "verify", "assure", "operate",
                   "serve", "govern", "retire")


def parse_json(text, source):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError, UnicodeError) as error:
        raise ValueError("%s is not valid bounded JSON: %s" % (source, error))


def _require_read_support():
    if (not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")
            or not hasattr(os, "fchdir")
            or os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd
            or os.stat not in os.supports_follow_symlinks):
        raise ValueError("this platform cannot guarantee race-safe repository reads")


def _require_write_support():
    _require_read_support()
    if (os.mkdir not in os.supports_dir_fd or os.rename not in os.supports_dir_fd
            or os.unlink not in os.supports_dir_fd or os.link not in os.supports_dir_fd
            or os.link not in os.supports_follow_symlinks):
        raise ValueError("this platform cannot guarantee race-safe repository writes")


class RepositoryRoot(str):
    def __new__(cls, root, descriptor):
        value = str.__new__(cls, os.path.abspath(root))
        value.descriptor = descriptor
        return value

    def close(self):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


def _open_root_path(root):
    _require_read_support()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    requested = os.path.abspath(root)
    try:
        before = os.stat(requested)
        canonical = os.path.realpath(requested)
    except OSError as error:
        raise ValueError("refused unsafe repository root %s: %s" % (root, error))
    descriptor = None
    try:
        descriptor = os.open(os.path.sep, flags)
        for part in [item for item in canonical.split(os.sep) if item]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("refused unsafe repository root %s: %s" % (root, error))
    try:
        if os.path.realpath(requested) != canonical:
            raise ValueError("repository root changed while it was opened: %s" % root)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("repository root changed while it was opened: %s" % root)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def open_root(root):
    if isinstance(root, RepositoryRoot):
        if root.descriptor is None:
            raise ValueError("repository root binding is closed: %s" % root)
        return os.dup(root.descriptor)
    return _open_root_path(root)


def bind_root(root):
    return RepositoryRoot(root, _open_root_path(root))


def root_identity(root):
    descriptor = open_root(root)
    try:
        details = os.fstat(descriptor)
        return details.st_dev, details.st_ino
    finally:
        os.close(descriptor)


def root_is_current(root):
    if not isinstance(root, RepositoryRoot):
        return True
    expected = root_identity(root)
    try:
        descriptor = _open_root_path(str(root))
    except ValueError:
        return False
    try:
        details = os.fstat(descriptor)
        return expected == (details.st_dev, details.st_ino)
    finally:
        os.close(descriptor)


def require_root_identity(root, claimed, source="input"):
    device, inode = root_identity(root)
    if (not isinstance(claimed, dict)
            or type(claimed.get("device")) is not int
            or type(claimed.get("inode")) is not int
            or claimed.get("device") != device or claimed.get("inode") != inode):
        raise ValueError("%s repository identity does not match the bound root" % source)


def require_mapping(value, source, schema=None):
    if not isinstance(value, dict):
        raise ValueError("%s must be a JSON object" % source)
    if schema is not None and (type(value.get("schema")) is not int
                               or value.get("schema") != schema):
        raise ValueError("%s declares schema %s, expected %s"
                         % (source, value.get("schema"), schema))
    return value


def require_shape(value, source, schema=None, mapping_fields=(), object_list_fields=(),
                  string_fields=(), object_map_fields=()):
    require_mapping(value, source, schema)
    for field in mapping_fields:
        if field in value and value[field] is not None and not isinstance(value[field], dict):
            raise ValueError("%s field %s must be a JSON object" % (source, field))
    for field in object_list_fields:
        if field not in value or value[field] is None:
            continue
        rows = value[field]
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("%s field %s must be an array of objects" % (source, field))
    for field in string_fields:
        if field in value and value[field] is not None and not isinstance(value[field], str):
            raise ValueError("%s field %s must be a string" % (source, field))
    for field in object_map_fields:
        if field not in value or value[field] is None:
            continue
        rows = value[field]
        if not isinstance(rows, dict) or any(not isinstance(row, dict) for row in rows.values()):
            raise ValueError("%s field %s must be an object of objects" % (source, field))
    return value


def _require_string_fields(value, fields, source):
    for field in fields:
        if field in value and value[field] is not None and not isinstance(value[field], str):
            raise ValueError("%s field %s must be a string" % (source, field))


def _require_present_string_fields(value, fields, source):
    for field in fields:
        if not isinstance(value.get(field), str):
            raise ValueError("%s field %s must be a non-null string" % (source, field))


def _require_string_list_fields(value, fields, source):
    for field in fields:
        if field in value and value[field] is not None:
            items = value[field]
            if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                raise ValueError("%s field %s must be an array of strings" % (source, field))


def _require_predicate(node, source, depth=0):
    if depth > 100 or not isinstance(node, dict) or not node:
        raise ValueError("%s must be a non-empty predicate object" % source)
    for key in ("all", "any"):
        if key in node:
            children = node[key]
            if not isinstance(children, list):
                raise ValueError("%s field %s must be an array of predicate objects"
                                 % (source, key))
            for index, child in enumerate(children):
                _require_predicate(child, "%s %s[%d]" % (source, key, index), depth + 1)
    if "not" in node:
        _require_predicate(node["not"], "%s not" % source, depth + 1)
    for field in ("signal", "answer", "archetype", "overlay", "document", "is", "state"):
        if field in node and not isinstance(node[field], str):
            raise ValueError("%s field %s must be a string" % (source, field))
    if "gte" in node and type(node["gte"]) is not int:
        raise ValueError("%s field gte must be an integer" % source)
    if "in" in node and (not isinstance(node["in"], list)
                         or any(not isinstance(item, str) for item in node["in"])):
        raise ValueError("%s field in must be an array of strings" % source)
    for field in ("always", "never"):
        if field in node and type(node[field]) is not bool:
            raise ValueError("%s field %s must be a boolean" % (source, field))


def require_manifest(value, source, schema):
    require_shape(value, source, schema, mapping_fields=("archetype",),
                  object_list_fields=("documents", "excluded", "assumptions",
                                      "open_questions", "drift"),
                  string_fields=("root", "repo_head", "generated_by", "generated_at"),
                  object_map_fields=("interview",))
    row_strings = ("id", "title", "stage", "path", "found_at", "state", "action",
                   "verdict", "write_status", "owner_candidate", "cadence")
    for collection in ("documents", "excluded", "assumptions", "open_questions", "drift"):
        for index, row in enumerate(value.get(collection) or []):
            row_source = "%s %s[%d]" % (source, collection, index)
            _require_string_fields(row, row_strings, row_source)
            if collection == "documents":
                _require_present_string_fields(row, ("id", "title", "stage"), row_source)
                if row["stage"] not in MANIFEST_STAGES:
                    raise ValueError("%s field stage is outside the lifecycle vocabulary"
                                     % row_source)
                _require_string_list_fields(row, ("audiences", "because", "cite", "evidence",
                                                  "rules", "satisfies"), row_source)
            elif collection == "excluded":
                _require_present_string_fields(row, ("id", "title", "because", "rule"),
                                               row_source)
                _require_string_fields(row, ("because", "rule"), row_source)
                _require_string_list_fields(row, ("cite",), row_source)
                if "revisit_when" in row:
                    _require_predicate(row["revisit_when"], "%s revisit_when" % row_source)
            elif collection in ("assumptions", "open_questions"):
                _require_string_list_fields(row, ("added", "cite", "evidence"), row_source)
    archetype = value.get("archetype") or {}
    _require_string_fields(archetype, ("primary", "confidence"), "%s archetype" % source)
    if "overlays" in archetype and (not isinstance(archetype["overlays"], list)
                                    or any(not isinstance(item, str)
                                           for item in archetype["overlays"])):
        raise ValueError("%s archetype overlays must be an array of strings" % source)
    return value


def require_scan(value, source, schema):
    require_shape(value, source, schema,
                  mapping_fields=("inventory", "ownership", "scan", "root_identity"),
                  object_list_fields=("signals", "drift", "unknown"),
                  string_fields=("root", "tool", "commit", "generated", "content_fingerprint"))
    if value.get("tool") != "docdna_scan" or not isinstance(value.get("root"), str):
        raise ValueError("%s does not carry a valid docdna_scan root" % source)
    fingerprint = value.get("content_fingerprint")
    if (not isinstance(fingerprint, str)
            or not fingerprint.startswith("sha256:") or len(fingerprint) != 71):
        raise ValueError("%s does not carry a valid content fingerprint" % source)
    inventory = require_shape(value.get("inventory"), "%s inventory" % source,
                              mapping_fields=("counts",),
                              object_list_fields=("docs", "opaque"))
    for collection in ("docs", "opaque"):
        for index, row in enumerate(inventory.get(collection) or []):
            row_source = "%s inventory %s[%d]" % (source, collection, index)
            _require_present_string_fields(row, ("path",), row_source)
            _require_string_fields(row, ("kind", "id"), row_source)
            if ("bytes" in row and row["bytes"] is not None
                    and type(row["bytes"]) is not int):
                raise ValueError("%s inventory %s[%d] bytes must be an integer"
                                 % (source, collection, index))
    counts = inventory.get("counts") or {}
    for field in ("total", "opaque", "with_frontmatter", "stale_over_365d", "broken_links"):
        if field in counts and type(counts[field]) is not int:
            raise ValueError("%s inventory counts field %s must be an integer" % (source, field))
    ownership = require_shape(value.get("ownership") or {}, "%s ownership" % source,
                              object_list_fields=("top_authors",))
    for index, row in enumerate(ownership.get("top_authors") or []):
        _require_string_fields(row, ("name", "email"),
                               "%s ownership top_authors[%d]" % (source, index))
    for index, row in enumerate(value.get("signals") or []):
        row_source = "%s signals[%d]" % (source, index)
        _require_present_string_fields(row, ("id", "state"), row_source)
        _require_string_fields(row, ("label", "note"), row_source)
        if "hits" in row and type(row["hits"]) is not int:
            raise ValueError("%s signals[%d] hits must be an integer" % (source, index))
        if "detail" in row and row["detail"] is not None:
            detail = row["detail"]
            if not isinstance(detail, dict):
                raise ValueError("%s signals[%d] detail must be a JSON object" % (source, index))
            _require_string_fields(detail, ("spdx",), "%s signals[%d] detail" % (source, index))
            _require_string_list_fields(detail, ("distinct", "entities"),
                                        "%s signals[%d] detail" % (source, index))
        if "evidence" in row:
            evidence = row["evidence"]
            if not isinstance(evidence, list) or any(not isinstance(item, dict)
                                                     for item in evidence):
                raise ValueError("%s signals[%d] evidence must be an array of objects"
                                 % (source, index))
            for number, item in enumerate(evidence):
                _require_string_fields(item, ("path", "symbol", "text"),
                                       "%s signals[%d] evidence[%d]"
                                       % (source, index, number))
                if ("line" in item and item["line"] is not None
                        and type(item["line"]) is not int):
                    raise ValueError("%s signals[%d] evidence[%d] line must be an integer"
                                     % (source, index, number))
    for index, row in enumerate(value.get("drift") or []):
        _require_string_fields(row, ("doc", "kind", "detail"),
                               "%s drift[%d]" % (source, index))
        if "line" in row and row["line"] is not None and type(row["line"]) is not int:
            raise ValueError("%s drift[%d] line must be an integer" % (source, index))
    scan_stats = value.get("scan") or {}
    if "drift" in scan_stats and not isinstance(scan_stats["drift"], dict):
        raise ValueError("%s scan drift must be a JSON object" % source)
    drift_stats = scan_stats.get("drift") or {}
    if "discarded" in drift_stats and not isinstance(drift_stats["discarded"], dict):
        raise ValueError("%s scan drift discarded must be a JSON object" % source)
    return value


def require_config(value, source):
    require_mapping(value, source)
    for field in ("exclude_dirs", "assurance_set"):
        if field in value and (not isinstance(value[field], list)
                               or any(not isinstance(item, str) for item in value[field])):
            raise ValueError("%s field %s must be an array of strings" % (source, field))
    for field in ("regulated", "safety_critical"):
        if field in value and type(value[field]) is not bool:
            raise ValueError("%s field %s must be a boolean" % (source, field))
    return value


def _parts(root, candidate):
    root_path = os.path.abspath(root)
    root_real = os.path.realpath(root_path)
    if os.path.isabs(candidate):
        target = os.path.abspath(candidate)
        bases = (root_path, root_real)
        rel = None
        for base in bases:
            try:
                if os.path.commonpath([base, target]) == base:
                    rel = os.path.relpath(target, base)
                    break
            except ValueError:
                pass
        if rel is None:
            raise ValueError("repository path resolves outside the root: %s" % candidate)
    else:
        target = os.path.abspath(os.path.join(root_path, candidate))
        try:
            if os.path.commonpath([root_path, target]) != root_path:
                raise ValueError("repository path resolves outside the root: %s" % candidate)
        except ValueError:
            raise ValueError("repository path resolves outside the root: %s" % candidate)
        rel = os.path.relpath(target, root_path)
    parts = [part for part in rel.split(os.sep) if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("repository path leaves the root: %s" % candidate)
    return root_path, parts


def _open_parent(root, candidate, create=False, root_descriptor=None):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = None
    try:
        if root_descriptor is None:
            descriptor = open_root(root)
        else:
            current = open_root(root)
            try:
                expected = os.fstat(root_descriptor)
                actual = os.fstat(current)
                if (expected.st_dev, expected.st_ino) != (actual.st_dev, actual.st_ino):
                    raise ValueError("repository root changed during the operation: %s" % root)
            finally:
                os.close(current)
            descriptor = os.dup(root_descriptor)
        _, parts = _parts(root, candidate)
        if not parts:
            raise ValueError("repository file path is empty: %s" % candidate)
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, 0o777, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("refused unsafe repository path %s: %s" % (candidate, error))
    except ValueError:
        if descriptor is not None:
            os.close(descriptor)
        raise


def _open_regular(root, candidate):
    _require_read_support()
    parent, name = _open_parent(root, candidate)
    descriptor = None
    try:
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("repository input is not a regular file: %s" % candidate)
        if before.st_nlink != 1:
            raise ValueError("refused multiply linked repository input: %s" % candidate)
        descriptor = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                             dir_fd=parent)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("repository input is not a regular file: %s" % candidate)
        if details.st_nlink != 1:
            raise ValueError("refused multiply linked repository input: %s" % candidate)
        if (before.st_dev, before.st_ino) != (details.st_dev, details.st_ino):
            raise ValueError("repository input changed while it was opened: %s" % candidate)
        return descriptor, details
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError("refused unsafe repository input %s: %s" % (candidate, error))
    except ValueError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    finally:
        os.close(parent)


def read_text_with_identity(root, candidate, encoding="utf-8", errors="strict", max_bytes=None):
    descriptor, details = _open_regular(root, candidate)
    if max_bytes is not None and details.st_size > max_bytes:
        os.close(descriptor)
        raise FileTooLarge(details.st_size)
    try:
        handle = os.fdopen(descriptor, "rb")
    except Exception:
        os.close(descriptor)
        raise
    with handle:
        raw = handle.read() if max_bytes is None else handle.read(max_bytes + 1)
    if max_bytes is not None and len(raw) > max_bytes:
        raise FileTooLarge(len(raw))
    identity = (details.st_dev, details.st_ino, len(raw), hashlib.sha256(raw).hexdigest())
    return raw.decode(encoding, errors), identity


def read_text(root, candidate, encoding="utf-8", errors="strict", max_bytes=None):
    text, _ = read_text_with_identity(root, candidate, encoding, errors, max_bytes)
    return text


def read_bounded_path(candidate, max_bytes, encoding="utf-8", errors="strict"):
    _require_read_support()
    descriptor = None
    try:
        descriptor = os.open(candidate, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("input is not a regular file: %s" % candidate)
        if details.st_size > max_bytes:
            raise FileTooLarge(details.st_size)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise FileTooLarge(len(raw))
        return raw.decode(encoding, errors)
    except OSError as error:
        raise ValueError("refused unsafe input %s: %s" % (candidate, error))
    finally:
        if descriptor is not None:
            os.close(descriptor)


def file_size(root, candidate):
    descriptor, details = _open_regular(root, candidate)
    os.close(descriptor)
    return details.st_size


def path_stat(root, candidate):
    _require_read_support()
    try:
        parent, name = _open_parent(root, candidate)
    except ValueError:
        return None
    try:
        details = os.stat(name, dir_fd=parent, follow_symlinks=False)
        return details
    except OSError:
        return None
    finally:
        os.close(parent)


def path_exists(root, candidate):
    return path_stat(root, candidate) is not None


def control_file_exists(root, candidate):
    """Return False only for an absent control file, and reject every unsafe shape."""
    _require_read_support()
    descriptor = open_root(root)
    try:
        _, parts = _parts(root, candidate)
        if not parts:
            raise ValueError("repository control-file path is empty: %s" % candidate)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        for part in parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                return False
            except OSError as error:
                raise ValueError("refused unsafe repository control file %s: %s"
                                 % (candidate, error))
            os.close(descriptor)
            descriptor = child
        try:
            details = os.stat(parts[-1], dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ValueError("refused unsafe repository control file %s: %s"
                             % (candidate, error))
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("repository control file is not a regular file: %s" % candidate)
        if details.st_nlink != 1:
            raise ValueError("refused multiply linked repository control file: %s" % candidate)
        return True
    finally:
        os.close(descriptor)


def is_file(root, candidate):
    details = path_stat(root, candidate)
    return (details is not None and stat.S_ISREG(details.st_mode)
            and details.st_nlink == 1)


def is_dir(root, candidate):
    details = path_stat(root, candidate)
    return details is not None and stat.S_ISDIR(details.st_mode)


def is_symlink(root, candidate):
    _require_read_support()
    parent = None
    try:
        parent, name = _open_parent(root, candidate)
        details = os.stat(name, dir_fd=parent, follow_symlinks=False)
        return stat.S_ISLNK(details.st_mode)
    except (OSError, ValueError):
        return False
    finally:
        if parent is not None:
            os.close(parent)


def listdir(root, candidate):
    _require_read_support()
    if not _LISTDIR_SUPPORTED:
        raise ValueError("this platform cannot guarantee race-safe directory reads")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = open_root(root)
    try:
        _, parts = _parts(root, candidate)
        for part in parts:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return _LISTDIR(descriptor)
    except OSError as error:
        raise ValueError("refused unsafe repository directory %s: %s" % (candidate, error))
    finally:
        if descriptor is not None:
            os.close(descriptor)


def walk_paths(root, prune=None):
    _require_read_support()
    if not _LISTDIR_SUPPORTED:
        raise ValueError("this platform cannot guarantee race-safe directory reads")
    files = []
    pruned = set()
    frames = []
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        descriptor = open_root(root)
        frames.append(["", descriptor, [], 0])
        frames[0][2] = sorted(_LISTDIR(descriptor))
        while frames:
            parent_rel, descriptor, names, index = frames[-1]
            if index >= len(names):
                os.close(descriptor)
                frames.pop()
                continue
            name = names[index]
            frames[-1][3] += 1
            rel = os.path.join(parent_rel, name) if parent_rel else name
            try:
                details = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except OSError as error:
                if error.errno == errno.ENOENT:
                    continue
                raise ValueError("refused unsafe repository entry %s: %s" % (rel, error))
            if not stat.S_ISDIR(details.st_mode):
                files.append(rel.replace(os.sep, "/"))
                continue
            if prune is not None and prune(name, parent_rel):
                pruned.add(name)
                continue
            child = None
            try:
                child = os.open(name, flags, dir_fd=descriptor)
                child_names = sorted(_LISTDIR(child))
                frames.append([rel, child, child_names, 0])
            except OSError as error:
                if child is not None:
                    os.close(child)
                raise ValueError("refused unsafe repository directory %s: %s" % (rel, error))
    finally:
        for _, descriptor, _, _ in frames:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return sorted(set(files)), pruned


def write_text(root, candidate, text, encoding="utf-8", root_descriptor=None):
    _require_write_support()
    parent, name = _open_parent(root, candidate, create=True,
                                root_descriptor=root_descriptor)
    temp_name = None
    try:
        try:
            existing = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if not stat.S_ISREG(existing.st_mode):
                raise ValueError("refused unsafe repository output %s" % candidate)
        temp_name = ".%s.docdna-%s.tmp" % (name, secrets.token_hex(12))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = None
        try:
            descriptor = os.open(temp_name, flags, 0o666, dir_fd=parent)
            if existing is not None:
                os.fchmod(descriptor, stat.S_IMODE(existing.st_mode))
            handle = os.fdopen(descriptor, "w", encoding=encoding)
            descriptor = None
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
            raise
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.rename(temp_name, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
        temp_name = None
    except OSError as error:
        raise ValueError("refused unsafe repository output %s: %s" % (candidate, error))
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=parent)
            except OSError:
                pass
        os.close(parent)


def unlink_file(root, candidate, expected_identity=None):
    _require_write_support()
    parent, name = _open_parent(root, candidate)
    quarantine = ".%s.docdna-delete-%s.tmp" % (name, secrets.token_hex(12))
    descriptor = None
    captured = False
    failure = None
    restore_error = None
    try:
        os.rename(name, quarantine, src_dir_fd=parent, dst_dir_fd=parent)
        captured = True
        descriptor = os.open(quarantine, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                             dir_fd=parent)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("repository deletion target is not a regular file: %s" % candidate)
        if details.st_nlink != 1:
            raise ValueError("refused multiply linked repository deletion: %s" % candidate)
        expected = tuple(expected_identity or ())
        actual = (details.st_dev, details.st_ino, details.st_size)
        if len(expected) != 4 or expected[:3] != actual:
            raise ValueError("repository deletion target changed after verification: %s"
                             % candidate)
        digest = hashlib.sha256()
        total = 0
        while total <= expected[2]:
            chunk = os.read(descriptor, min(65536, expected[2] + 1 - total))
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(descriptor)
        stable = ((details.st_size, details.st_mtime_ns, details.st_ctime_ns)
                  == (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
        if total != expected[2] or digest.hexdigest() != expected[3] or not stable:
            raise ValueError("repository deletion target changed after verification: %s"
                             % candidate)
        os.unlink(quarantine, dir_fd=parent)
        captured = False
    except OSError as error:
        failure = ValueError("refused unsafe repository deletion %s: %s" % (candidate, error))
    except ValueError as error:
        failure = error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if captured:
            try:
                os.link(quarantine, name, src_dir_fd=parent, dst_dir_fd=parent,
                        follow_symlinks=False)
                os.unlink(quarantine, dir_fd=parent)
            except OSError as error:
                restore_error = error
        os.close(parent)
    if restore_error is not None:
        raise ValueError("repository deletion was refused and the captured file remains at %s: %s"
                         % (quarantine, restore_error))
    if failure is not None:
        raise failure


class FileTooLarge(ValueError):
    def __init__(self, size):
        super().__init__("repository input is %d bytes" % size)
        self.size = size
