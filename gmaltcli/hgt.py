import os
import re
import struct


class HgtParser(object):
    """ A tool to parse a HGT file

    It is intended to be used in a context manager::

        with HgtParser('myhgtfile.hgt') as parser:
            parser.get_elevation((lat, lng))

    :param str filepath: the path to the HGT file to parse
    :param int sample_lat: the number of values on the latitude axis
    :param int sample_lng: the number of values on the latitude axis
    """

    def __init__(self, filepath, sample_lat=1201, sample_lng=1201):
        self.file = None
        self.filepath = filepath
        self.filename = os.path.basename(filepath)

        self.sample_lat = sample_lat
        self.sample_lng = sample_lng

        self.bottom_left_center = self._get_bottom_left_center(self.filename)
        self.corners = self._get_corners_from_filename(self.bottom_left_center)
        self.top_left_square = self._get_top_left_square()

    def __enter__(self):
        if not os.path.exists(self.filepath):
            raise Exception('file {} not found'.format(self.filepath))
        self.file = open(self.filepath, 'rb')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file:
            self.file.close()
            self.file = None

    def get_value_iterator(self):
        return HgtValueIterator(self)

    def get_sample_iterator(self, width, height):
        return HgtSampleIterator(self, width, height)

    def _get_top_left_square(self):
        """ Get the corners of the top left square in the HGT file

         .. note:: useful when iterating over all the values

        :return: tuple of 4 position tuples (bottom left, top left, top right, bottom right) with (lat, lng) for each
        position as float
        :rtype: ((float, float), (float, float), (float, float), (float, float))
        """
        return (
            (self.corners[1][0] - self.square_height, self.corners[1][1]),
            self.corners[1],
            (self.corners[1][0], self.corners[1][1] + self.square_width),
            (self.corners[1][0] - self.square_height, self.corners[1][1] + self.square_width)
        )

    def shift_first_square(self, line, col):
        """ Shift the top left square by the provided number of lines and columns

        :param int line: line number (from 0 to sample_lat - 1)
        :param int col: column number (from 0 to sample_lng - 1)
        :return: tuple of 4 position tuples (bottom left, top left, top right, bottom right) with (lat, lng) for each
        position as float
        :rtype: ((float, float), (float, float), (float, float), (float, float))
        """
        shifted = ()
        for corner in self.top_left_square:
            shifted += ((corner[0] - line * self.square_height, corner[1] + col * self.square_width),)
        return shifted

    @property
    def square_width(self):
        """ Provide the width (length on the longitude axis) of a square providing one elevation value

        :return: the width of a square with one elevation value
        :rtype: float
        """
        return 1.0 / (self.sample_lng - 1)

    @property
    def square_height(self):
        """ Provide the height (length on the latitude axis) of a square providing one elevation value

        :return: the height of a square with one elevation value
        :rtype: float
        """
        return 1.0 / (self.sample_lat - 1)

    @property
    def area_width(self):
        """ Provide the total width of the HGT file

        :return: the total width of the HGT file
        :rtype: float
        """
        return 1.0 + self.square_width

    @property
    def area_height(self):
        """ Provide the total height of the HGT file

        :return: the total height of the HGT file
        :rtype: float
        """
        return 1.0 + self.square_height

    @staticmethod
    def _get_bottom_left_center(filename):
        """ Extract the latitude and longitude of the center of the bottom left elevation
        square based on the filename

        :param str filename: name of the HGT file
        :return: tuple (latitude of the center of the bottom left square, longitude of the bottom left square)
        :rtype: tuple of float
        """
        filename_regex = re.compile('^([NS])([0-9]+)([WE])([0-9]+).*')
        result = filename_regex.match(filename)

        lat_order, lat_left_bottom_center, lng_order, lng_left_bottom_center = result.groups()

        lat_left_bottom_center = float(lat_left_bottom_center)
        lng_left_bottom_center = float(lng_left_bottom_center)
        if lat_order == 'S':
            lat_left_bottom_center *= -1
        if lng_order == 'W':
            lng_left_bottom_center *= -1

        return lat_left_bottom_center, lng_left_bottom_center

    def _get_corners_from_filename(self, bottom_left_corner):
        """ Based on the bottom left center latitude and longitude get the latitude and longitude of all the corner
         covered by the parsed HGT file

        :param tuple bottom_left_corner: position of the bottom left corner (lat, lng)
        :return: tuple of 4 position tuples (bottom left, top left, top right, bottom right) with (lat, lng) for each
        position as float
        :rtype: ((float, float), (float, float), (float, float), (float, float))
        """
        bottom_left = (bottom_left_corner[0] - self.square_height / 2, bottom_left_corner[1] - self.square_width / 2)
        top_left = (bottom_left[0] + self.area_height, bottom_left[1])
        top_right = (top_left[0], top_left[1] + self.area_width)
        bottom_right = (bottom_left[0], bottom_left[1] + self.area_width)

        return bottom_left, top_left, top_right, bottom_right

    def is_inside(self, point):
        """ Check if the point is inside the parsed HGT file

        :param tuple point: (lat, lng) of the point
        :return: True if the point is inside else False
        :rtype: bool
        """
        return \
            self.corners[0][0] < point[0] \
            and self.corners[0][1] < point[1] \
            and point[0] < self.corners[2][0] \
            and point[1] < self.corners[2][1]

    def get_idx(self, col, line):
        """ Calculate the index of the value based on the column and line numbers of the value

        :param int col: the column number (zero based)
        :param int line: the line number (zero based)
        :return: the index of the value
        :rtype: int
        """
        return line * self.sample_lng + col

    def get_value(self, idx):
        """ Get the elevation value at the provided index

        :param int idx: index of the value
        :return: the elevation value or None if no value at this index (instead of -32768)
        :rtype: int
        """
        self.file.seek(0)
        self.file.seek(idx * 2)
        buf = self.file.read(2)
        val, = struct.unpack('>h', buf)

        return val if not val == -32768 else None

    def get_idx_in_file(self, pos):
        """ From a position (lat, lng) as float. Get the index of the elevation value inside the HGT file

        :param tuple pos: (lat, lng) of the position
        :return: tuple (index on the latitude from the top, index on the longitude from the left, index in the file)
        :rtype: (int, int, int)
        """
        lat_idx = 1200 - int(round((pos[0] - self.bottom_left_center[0]) / self.square_height))
        lng_idx = int(round((pos[1] - self.bottom_left_center[1]) / self.square_width))
        idx = lat_idx * 1201 + lng_idx
        return lat_idx, lng_idx, idx

    def get_elevation(self, pos):
        """ Get the elevation for a position

        :param tuple pos: (lat, lng) of the position
        :return: tuple (index on the latitude from the top, index on the longitude from the left, elevation in meters)
        :rtype: (int, int, int)
        :raises Exception: if the point could not be found in the parsed HGT file
        """
        if not self.is_inside(pos):
            raise Exception('point {} is not inside HGT file {}'.format(pos, self.filename))

        lat_idx, lng_idx, idx = self.get_idx_in_file(pos)

        return lat_idx, lng_idx, self.get_value(idx)


class HgtValueIterator(object):
    """ Iterator over all the elevation values in the file

    :param parser: a HgtParser instance
    :type parser: @TODO
    :return: tuple with (line number, column number, zero based index, square corners of the elevation value,
    elevation value)
    :rtype: (int, int, int, ((float, float), (float, float), (float, float), (float, float)), int)
    """
    def __init__(self, parser):
        self.parser = parser

    def __iter__(self):
        idx = 0
        while idx < self.parser.sample_lat * self.parser.sample_lng:
            line = idx / self.parser.sample_lng
            col = idx % self.parser.sample_lng
            square = self.parser.shift_first_square(line, col)
            yield line + 1, col + 1, idx, square, self.parser.get_value(idx)
            idx += 1
        raise StopIteration


class HgtSampleIterator(object):
    """ Iterator over samples. For example 50x50 values per 50x50

    :param parser: a HgtParser instance
    :type parser: @TODO
    :param int width: width of the sample area
    :param int height: height of the sample area
    """
    def __init__(self, parser, width, height):
        self.parser = parser
        self.width = width
        self.height = height

    def __iter__(self):
        for top_left_line_idx in range(0, self.parser.sample_lat, self.height):
            for top_left_col_idx in range(0, self.parser.sample_lng, self.width):
                yield self._get_square_values(top_left_col_idx, top_left_line_idx)
        raise StopIteration

    def _get_square_values(self, top_left_col_idx, top_left_line_idx):
        """ Get all the elevation values in the requested square knowing
        its top left corner line and column numbers

        :param int top_left_col_idx: column number of the top left corner of the requested square
        :param int top_left_line_idx: line number of the top left corner of the requested square
        :return: list of list of elevation values (grouped per line)
        :rtype: list[list[int]]
        """
        square_values = []
        for idx in range(top_left_line_idx, min(self.parser.sample_lat, top_left_line_idx + self.height)):
            square_values.append(self._read_line(top_left_col_idx, idx))
        return square_values

    def _read_line(self, col_idx, line_idx):
        """ Get a line of elevation values in the requested square knowing the starting
        column number and the line number

        :param int col_idx: the starting column number
        :param int line_idx: the line number
        :return: list of elevation values
        :rtype: list[int]
        """
        line_values = []
        for idx in range(col_idx, min(self.parser.sample_lng, col_idx + self.width)):
            value_idx = self.parser.get_idx(idx, line_idx)
            line_values.append(self.parser.get_value(value_idx))
        return line_values