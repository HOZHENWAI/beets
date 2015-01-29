# This file is part of beets.
# Copyright 2015, Bruno Cauet
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

from __future__ import (division, absolute_import, print_function,
                        unicode_literals)

import os.path
from mock import Mock, patch, call

from test._common import unittest
from test.helper import TestHelper

from beetsplug.thumbnails import (ThumbnailsPlugin, NORMAL_DIR, LARGE_DIR,
                                  write_metadata_im, write_metadata_pil)


class ThumbnailsTest(unittest.TestCase, TestHelper):
    def setUp(self):
        self.setup_beets()

    def tearDown(self):
        self.teardown_beets()

    @patch('beetsplug.thumbnails.BaseDirectory')
    def test_thumbnail_filter_name(self, mock_basedir):
        filename = b"/home/jens/photos/me.png"
        thumbnail = ThumbnailsPlugin.thumbnail_file_name(filename)
        self.assertEqual(thumbnail, b"c6ee772d9e49320e97ec29a7eb5b1697.png")

    @patch('beetsplug.thumbnails.util')
    def test_write_metadata_im(self, mock_util):
        metadata = {"a": "A", "b": "B"}
        write_metadata_im("foo", metadata)
        try:
            command = "convert foo -set a A -set b B foo".split(' ')
            mock_util.command_output.assert_called_once_with(command)
        except AssertionError:
            command = "convert foo -set b B -set a A foo".split(' ')
            mock_util.command_output.assert_called_once_with(command)

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    @patch('beetsplug.thumbnails.os.stat')
    def test_add_tags(self, mock_stat, _):
        plugin = ThumbnailsPlugin()
        plugin.write_metadata = Mock()
        album = Mock(artpath=b"/path/to/cover")
        plugin.add_tags(album, b"/path/to/thumbnail")

        metadata = {"Thumb::URI": b"file:///path/to/cover",
                    "Thumb::MTime": mock_stat.return_value.st_mtime}
        plugin.write_metadata.assert_called_once_with(b"/path/to/thumbnail",
                                                      metadata)
        mock_stat.assert_called_once_with(album.artpath)

    @patch('beetsplug.thumbnails.os')
    @patch('beetsplug.thumbnails.ArtResizer')
    @patch('beetsplug.thumbnails.has_IM')
    @patch('beetsplug.thumbnails.has_PIL')
    def test_check_local_ok(self, mock_pil, mock_im, mock_artresizer, mock_os):
        # test local resizing capability
        mock_artresizer.shared.local = False
        plugin = ThumbnailsPlugin()
        self.assertFalse(plugin._check_local_ok())

        # test dirs creation
        mock_artresizer.shared.local = True

        def exists(path):
            if path == NORMAL_DIR:
                return False
            if path == LARGE_DIR:
                return True
            raise ValueError("unexpected path {0!r}".format(path))
        mock_os.path.exists = exists
        plugin = ThumbnailsPlugin()
        mock_os.makedirs.assert_called_once_with(NORMAL_DIR)
        self.assertTrue(plugin._check_local_ok())

        # test metadata writer function
        mock_os.path.exists = lambda _: True
        mock_pil.return_value = False
        mock_im.return_value = False
        with self.assertRaises(AssertionError):
            ThumbnailsPlugin()

        mock_pil.return_value = True
        self.assertEqual(ThumbnailsPlugin().write_metadata, write_metadata_pil)

        mock_im.return_value = True
        self.assertEqual(ThumbnailsPlugin().write_metadata, write_metadata_im)

        mock_pil.return_value = False
        self.assertEqual(ThumbnailsPlugin().write_metadata, write_metadata_im)

        self.assertTrue(ThumbnailsPlugin()._check_local_ok())

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    @patch('beetsplug.thumbnails.ArtResizer')
    @patch('beetsplug.thumbnails.util')
    @patch('beetsplug.thumbnails.os')
    @patch('beetsplug.thumbnails.shutil')
    def test_make_cover_thumbnail(self, mock_shutils, mock_os, mock_util,
                                  mock_artresizer, _):
        mock_os.path.join = os.path.join  # don't mock that function
        plugin = ThumbnailsPlugin()
        plugin.add_tags = Mock()

        album = Mock(artpath=b"/path/to/art")
        mock_util.syspath.side_effect = lambda x: x
        plugin.thumbnail_file_name = Mock(return_value="md5")
        mock_os.path.exists.return_value = False

        def os_stat(target):
            if target == b"/thumbnail/dir/md5":
                return Mock(st_mtime=1)
            elif target == b"/path/to/art":
                return Mock(st_mtime=2)
            else:
                raise ValueError("invalid target {0}".format(target))
        mock_os.stat.side_effect = os_stat

        plugin.make_cover_thumbnail(album, 12345, b"/thumbnail/dir")

        mock_os.path.exists.assert_called_once_with(b"/thumbnail/dir/md5")
        mock_os.stat.has_calls([call(b"/thumbnail/dir/md5"),
                                call(b"/path/to/art")], any_order=True)

        resize = mock_artresizer.shared.resize
        resize.assert_called_once_with(12345, b"/path/to/art",
                                       b"/thumbnail/dir/md5")
        plugin.add_tags.assert_called_once_with(album, resize.return_value)
        mock_shutils.move.assert_called_once_with(resize.return_value,
                                                  b"/thumbnail/dir/md5")

        # now test with recent thumbnail & with force
        mock_os.path.exists.return_value = True
        plugin.force = False
        resize.reset_mock()

        def os_stat(target):
            if target == b"/thumbnail/dir/md5":
                return Mock(st_mtime=3)
            elif target == b"/path/to/art":
                return Mock(st_mtime=2)
            else:
                raise ValueError("invalid target {0}".format(target))
        mock_os.stat.side_effect = os_stat

        plugin.make_cover_thumbnail(album, 12345, b"/thumbnail/dir")
        self.assertEqual(resize.call_count, 0)

        # and with force
        plugin.force = True
        plugin.make_cover_thumbnail(album, 12345, b"/thumbnail/dir")
        resize.assert_called_once_with(12345, b"/path/to/art",
                                       b"/thumbnail/dir/md5")

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    @patch('beetsplug.thumbnails.ArtResizer')
    def test_process_album(self, mock_artresizer, _):
        get_size = mock_artresizer.shared.get_size

        plugin = ThumbnailsPlugin()
        make_cover = plugin.make_cover_thumbnail = Mock()

        # no art
        album = Mock(artpath=None)
        plugin.process_album(album)
        self.assertEqual(get_size.call_count, 0)

        # cannot get art size
        album.artpath = b"/path/to/art"
        get_size.return_value = None
        plugin.process_album(album)
        get_size.assert_called_once_with(b"/path/to/art")
        self.assertEqual(make_cover.call_count, 0)

        # small art
        get_size.return_value = 200, 200
        plugin.process_album(album)
        make_cover.assert_called_once_with(album, 128, NORMAL_DIR)

        # big art
        make_cover.reset_mock()
        get_size.return_value = 500, 500
        plugin.process_album(album)
        make_cover.has_calls([call(album, 128, NORMAL_DIR),
                              call(album, 256, LARGE_DIR)], any_order=True)

    @patch('beetsplug.thumbnails.ThumbnailsPlugin._check_local_ok')
    @patch('beetsplug.thumbnails.decargs')
    def test_invokations(self, mock_decargs, _):
        plugin = ThumbnailsPlugin()
        plugin.process_album = Mock()

        album = Mock()
        plugin.imported(None, album)
        plugin.process_album.assert_called_once_with(album)

        plugin.process_album.reset_mock()
        lib = Mock()
        album2 = Mock()
        lib.albums.return_value = [album, album2]
        plugin.process_query(lib, None, None)
        lib.albums.assert_called_once_with(mock_decargs.return_value)
        plugin.process_album.has_calls([call(album), call(album2)],
                                       any_order=True)


def suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == b'__main__':
    unittest.main(defaultTest='suite')
