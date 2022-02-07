# Copyright (C) 2022 -- svg2mod developers < GitHub.com / svg2mod >

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

'''
Helper classes to combine and calculate the points
from a svg object into a single continuous line
'''

import copy
#from typing import List, Tuple

from . import svg
from .coloredlogger import logger

#----------------------------------------------------------------------------

class LineSegment:
    '''Kicad can only draw straight lines.
    It is designed to have extra functions to help
    calculate intersections.
    '''

    #------------------------------------------------------------------------

    @staticmethod
    def _on_segment( p, q, r ):
        """ Given three collinear points p, q, and r, check if
            point q lies on line segment pr. """

        if (
            q.x <= max( p.x, r.x ) and
            q.x >= min( p.x, r.x ) and
            q.y <= max( p.y, r.y ) and
            q.y >= min( p.y, r.y )
        ):
            return True

        return False


    #------------------------------------------------------------------------

    @staticmethod
    def _orientation( p, q, r ):
        """ Find orientation of ordered triplet (p, q, r).
            Returns following values
            0 --> p, q and r are collinear
            1 --> Clockwise
            2 --> Counterclockwise
        """

        val = (
            ( q.y - p.y ) * ( r.x - q.x ) -
            ( q.x - p.x ) * ( r.y - q.y )
        )

        if val == 0: return 0
        if val > 0: return 1
        return 2

    #------------------------------------------------------------------------

    @staticmethod
    def vertical_intersection(p, q, r):
        '''This is used for the in-lining algorithm
        it finds a point on a line p -> q where x = r
        '''
        if p.x == q.x:
            return min([p,q], key=lambda v: v.y)
        if r == p.x: return p
        if r == q.x: return q
        return svg.Point(r, (p.y-q.y)*(r-q.x)/(p.x-q.x)+q.y)


    #------------------------------------------------------------------------

    def __init__( self, p = None, q = None ):

        self.p = p
        self.q = q


    #------------------------------------------------------------------------

    def connects( self, segment):
        ''' Return true if provided segment shares
        endpoints with the current segment
        '''

        if self.q == segment.p: return True
        if self.q == segment.q: return True
        if self.p == segment.p: return True
        if self.p == segment.q: return True
        return False

    #------------------------------------------------------------------------

    def on_line(self, point):
        '''Returns true if the point is on the line.
            Adapted from:
            https://stackoverflow.com/questions/36487156/javascript-determine-if-a-point-resides-above-or-below-a-line-defined-by-two-poi
        '''
        return not (self.p.x-self.q.x)*(point.y-self.q.y) - (self.p.y-self.q.y)*(point.x-self.q.x)

    #------------------------------------------------------------------------

    def intersects( self, segment):
        """ Return true if line segments 'p1q1' and 'p2q2' intersect.
            Adapted from:
              http://www.geeksforgeeks.org/check-if-two-given-line-segments-intersect/
        """

        # Find the four orientations needed for general and special cases:
        o1 = self._orientation( self.p, self.q, segment.p )
        o2 = self._orientation( self.p, self.q, segment.q )
        o3 = self._orientation( segment.p, segment.q, self.p )
        o4 = self._orientation( segment.p, segment.q, self.q )

        return (

            # General case:
            ( o1 != o2 and o3 != o4 )

            or

            # p1, q1 and p2 are collinear and p2 lies on segment p1q1:
            ( o1 == 0 and self._on_segment( self.p, segment.p, self.q ) )

            or

            # p1, q1 and p2 are collinear and q2 lies on segment p1q1:
            ( o2 == 0 and self._on_segment( self.p, segment.q, self.q ) )

            or

            # p2, q2 and p1 are collinear and p1 lies on segment p2q2:
            ( o3 == 0 and self._on_segment( segment.p, self.p, segment.q ) )

            or

            # p2, q2 and q1 are collinear and q1 lies on segment p2q2:
            ( o4 == 0 and self._on_segment( segment.p, self.q, segment.q ) )
        )


    #------------------------------------------------------------------------

    def q_next( self, q ):
        '''Shift segment endpoints so self.q is self.p
        and q is the new self.q
        '''

        self.p = self.q
        self.q = q

    #------------------------------------------------------------------------

    def __eq__(self, other):
        return (
            isinstance(other, LineSegment) and
            other.p.x == self.p.x and other.p.y == self.p.y and
            other.q.x == self.q.x and other.q.y == self.q.y
        )

    #------------------------------------------------------------------------

#----------------------------------------------------------------------------

class PolygonSegment:
    ''' A polygon should be a collection of segments
    creating an enclosed or manifold shape.
    This class provides functionality to find overlap
    points between a segment and its self as well as
    identify if another polygon rests inside of the
    closed area of its self.

    When initializing this class it will remove duplicate points in a row.
    '''

    #------------------------------------------------------------------------

    def __init__( self, points):

        self.points = [points[0]]

        for point in points:
            if self.points[-1] != point:
                self.points.append(point)

        self.bbox = None
        self.calc_bbox()


    #------------------------------------------------------------------------

    def _set_points(self, points):
        self.points = points[:]

    #------------------------------------------------------------------------

    def _find_insertion_point( self, hole, holes, other_insertions ):
        ''' KiCad will not "pick up the pen" when moving between a polygon outline
        and holes within it, so we search for a pair of points connecting the
        outline (self) or other previously inserted points to the hole such
        that the connecting segment will not cross the visible inner space
        within any hole.
        '''

        highest_point = max(hole.points, key=lambda v: v.y)
        vertical_line = LineSegment(highest_point, svg.Point(highest_point.x, self.bbox[1].y+1))

        intersections = {self: self.intersects(vertical_line, False, count_intersections=True, get_points=True)}
        for _,h,__ in other_insertions:
            if h.bbox[0].x < highest_point.x and h.bbox[1].x > highest_point.x:
                intersections[h] = h.intersects(vertical_line, False, count_intersections=True, get_points=True)

        best = [self, intersections[self][0]]
        best.append(LineSegment.vertical_intersection(best[1][0], best[1][1], highest_point.x))
        for path in intersections:
            for p,q in intersections[path]:
                pnt = LineSegment.vertical_intersection(p, q, highest_point.x)
                if pnt.y < best[2].y:
                    best = [path, (p,q), pnt]

        if best[2] != best[1][0] and best[2] != best[1][1]:
            p = best[0].points.index(best[1][0])
            q = best[0].points.index(best[1][1])
            ip = p if p < q else q
            best[0]._set_points(best[0].points[:ip+1] + [best[2]] + best[0].points[ip+1:])

        return (best[2], hole, highest_point)

    #------------------------------------------------------------------------

    def points_starting_on_index( self, index ):
        ''' Return the list of ordered points starting on the given index, ensuring
        that the first and last points are the same.
        '''

        points = self.points

        if index > 0:

            # Strip off end point, which is a duplicate of the start point:
            points = points[ : -1 ]

            points = points[ index : ] + points[ : index ]

            points.append(
                svg.Point( points[ 0 ].x, points[ 0 ].y )
            )

        return points


    #------------------------------------------------------------------------

    def inline( self, segments ):
        ''' Return a list of points with the given polygon segments (paths) inlined. '''

        if len( segments ) < 1:
            return self.points

        logger.debug( "  Inlining {} segments...".format( len( segments ) ) )

        segments.sort(reverse=True, key=lambda h: h.bbox[1].y)

        all_segments = segments[ : ] + [ self ]
        insertions = []

        # Find the insertion point for each hole:
        for hole in segments:

            insertion = self._find_insertion_point(
                hole, all_segments, insertions
            )
            if insertion is not None:
                insertions.append( insertion )

        # Prevent returned points from affecting original object
        points = copy.deepcopy(self.points)

        for insertion in insertions:

            ip = points.index(insertion[0])
            hole = insertion[1].points_starting_on_index(insertion[1].points.index(insertion[2]))

            if (
                points[ ip ].x == hole[ 0 ].x and
                points[ ip ].y == hole[ 0 ].y
            ):
                # The point at the insertion point is duplicated so any action on that will affect both
                points = points[:ip] + [copy.copy(points[ip])] + hole[ 1 : -1 ] + points[ip:]
            else:
                # The point at the insertion point is duplicated so any action on that will affect both
                points = points[:ip] + [copy.copy(points[ip])] + hole + points[ip:]

        return points


    #------------------------------------------------------------------------

    def intersects( self, line_segment, check_connects , count_intersections=False, get_points=False):
        '''Check to see if line_segment intersects with any
        segments of the polygon. Default return True/False

        If check_connects is True then it will skip intersections
        that share endpoints with line_segment.

        count_intersections will return the number of intersections
        with the polygon.

        get_points returns a tuple of the line that intersects
        with line_segment. count_intersection in combination will
        return a list of tuples of line segments.
        '''

        hole_segment = LineSegment()

        intersections = 0
        intersect_segs = []
        virt_line = LineSegment()

        # Check each segment of other hole for intersection:
        for point in self.points:

            hole_segment.q_next( point )

            if hole_segment.p is not None:

                if ( check_connects and line_segment.connects( hole_segment )):
                    continue

                if line_segment.intersects( hole_segment ):

                    if count_intersections:
                        if get_points:
                            intersect_segs.append((hole_segment.p, hole_segment.q))
                        else:
                            # If a point is on the line segment we need to see if the
                            # simplified "virtual" line crosses the line segment.

                            # Set the endpoints if they are of the line segment
                            if line_segment.on_line(hole_segment.q):
                                if not line_segment.on_line(hole_segment.p):
                                    virt_line.p = hole_segment.p
                            elif line_segment.on_line(hole_segment.p):
                                virt_line.q = hole_segment.q

                            # No points are on the line segment
                            else:
                                intersections += 1
                                virt_line = LineSegment()

                            # The virtual line is complete check for intersections
                            if virt_line.p and virt_line.q:
                                if virt_line.intersects(line_segment):
                                    intersections += 1
                                virt_line = LineSegment()

                    elif get_points:
                        return hole_segment.p, hole_segment.q
                    else:
                        return True

        if count_intersections:
            return intersect_segs if get_points else intersections
        if get_points and not check_connects:
            return ()
        return False


    #------------------------------------------------------------------------

    def process( self, transformer, flip, fill ):
        ''' Apply all transformations, then remove duplicate
        consecutive points along the path.
        '''

        points = []
        for point in self.points:

            point = transformer.transform_point( point, flip )

            if (
                len( points ) < 1 or
                point.x != points[ -1 ].x or
                point.y != points[ -1 ].y
            ):
                points.append( point )

        if (
            points[ 0 ].x != points[ -1 ].x or
            points[ 0 ].y != points[ -1 ].y
        ):

            if fill:
                points.append( svg.Point(
                    points[ 0 ].x,
                    points[ 0 ].y,
                ) )

        self.points = points
        self.calc_bbox()


    #------------------------------------------------------------------------

    def calc_bbox(self):
        '''Calculate bounding box of self'''
        self.bbox =  (
            svg.Point(min(self.points, key=lambda v: v.x).x, min(self.points, key=lambda v: v.y).y),
            svg.Point(max(self.points, key=lambda v: v.x).x, max(self.points, key=lambda v: v.y).y),
        )

    #------------------------------------------------------------------------

    def are_distinct(self, polygon):
        ''' Checks if the supplied polygon either contains or insets our bounding box'''
        distinct = True

        smaller = min([self, polygon], key=lambda p: svg.Segment(p.bbox[0], p.bbox[1]).length())
        larger = self if smaller == polygon else polygon

        if (
            larger.bbox[0].x < smaller.bbox[0].x and
            larger.bbox[0].y < smaller.bbox[0].y and
            larger.bbox[1].x > smaller.bbox[1].x and
            larger.bbox[1].y > smaller.bbox[1].y
        ):
            distinct = False

        # Check number of horizontal intersections. If the number is odd then it the smaller polygon
        # is contained. If the number is even then the polygon is outside of the larger polygon
        if not distinct:
            tline = LineSegment(smaller.points[0], svg.Point(larger.bbox[1].x+1, smaller.points[0].y))
            distinct = bool((larger.intersects(tline, False, True) + 1)%2)

        return distinct
    #------------------------------------------------------------------------


#----------------------------------------------------------------------------

