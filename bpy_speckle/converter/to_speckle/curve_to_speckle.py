from bpy.types import Object
from typing import Union, Optional, Tuple, List
from specklepy.objects.geometry import Polyline, Curve
from specklepy.objects.primitive import Interval
from specklepy.objects.base import Base
from mathutils import Matrix
from mathutils.geometry import interpolate_bezier

def curve_to_speckle(
    blender_obj: Object, scale_factor: float = 1.0
) -> Union[Base, None]:

    assert blender_obj.type == "CURVE", "Object must be a curve"
    assert blender_obj.data is not None, "Curve data cannot be None"

    curve_data = blender_obj.data
    matrix = blender_obj.matrix_world
    units = "m"  # TODO: Use the unit system from the scene
    
    base = Base()
    curves = []
    
    for spline in curve_data.splines:
        if spline.type == "BEZIER":
            curves.append(bezier_to_speckle(matrix, spline, blender_obj.name, scale_factor, units))
        elif spline.type == "NURBS":
            curves.append(nurbs_to_speckle(matrix, spline, blender_obj.name, scale_factor, units))
    
    if curves:
        base["@elements"] = curves
        base["name"] = blender_obj.name
        return base
    
    return None


def bezier_to_speckle(
    matrix: Matrix, 
    spline, 
    name: Optional[str] = None, 
    scale_factor: float = 1.0,
    units: str = "m"
) -> Curve:

    degree = 3
    closed = spline.use_cyclic_u
    points: List[Tuple[float, float, float]] = []
    
    for i, bp in enumerate(spline.bezier_points):
        if i > 0:
            transformed_point = matrix @ bp.handle_left * scale_factor
            points.append((transformed_point.x, transformed_point.y, transformed_point.z))
        
        transformed_point = matrix @ bp.co * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))
        
        if i < len(spline.bezier_points) - 1:
            transformed_point = matrix @ bp.handle_right * scale_factor
            points.append((transformed_point.x, transformed_point.y, transformed_point.z))

    if closed:
        transformed_point = matrix @ spline.bezier_points[-1].handle_right * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))
        
        transformed_point = matrix @ spline.bezier_points[0].handle_left * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))
        
        transformed_point = matrix @ spline.bezier_points[0].co * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))

    num_points = len(points)

    flattened_points = []
    for point in points:
        flattened_points.extend(point)

    knot_count = num_points + degree - 1
    knots = [0] * knot_count

    for i in range(1, len(knots)):
        knots[i] = i // 3

    length = spline.calc_length()
    
    domain = Interval(start=0, end=length)
    display_value = bezier_to_speckle_polyline(matrix, spline, length, scale_factor, units)
    
    curve = Curve(
        degree=degree,
        periodic=not spline.use_endpoint_u,
        rational=True,
        points=flattened_points,
        weights=[1] * num_points,
        knots=knots,
        closed=spline.use_cyclic_u,
        displayValue=display_value,
        units=units,
        bbox=None,
    )
    
    curve.__dict__["_length"] = length
    curve.__dict__["_area"] = 0.0
    
    curve["domain"] = domain
    
    if name:
        curve["name"] = name
        
    return curve

def bezier_to_speckle_polyline(
    matrix: Matrix, 
    spline, 
    length: Optional[float] = None,
    scale_factor: float = 1.0,
    units: str = "m"
) -> Optional[Polyline]:
    
    segments = len(spline.bezier_points)
    if segments < 2:
        return None

    resolution = spline.resolution_u + 1
    points: List[float] = []
    
    if not spline.use_cyclic_u:
        segments -= 1

    for i in range(segments):
        inext = (i + 1) % len(spline.bezier_points)

        knot1 = spline.bezier_points[i].co
        handle1 = spline.bezier_points[i].handle_right
        handle2 = spline.bezier_points[inext].handle_left
        knot2 = spline.bezier_points[inext].co

        sampled_points = interpolate_bezier(knot1, handle1, handle2, knot2, resolution)
        for p in sampled_points:
            scaled_point = matrix @ p * scale_factor
            points.append(scaled_point.x)
            points.append(scaled_point.y)
            points.append(scaled_point.z)

    length = length or spline.calc_length()
    
    polyline = Polyline(
        value=points,
        units=units
    )
    
    polyline["domain"] = { "start": 0, "end": length }
    polyline["closed"] = spline.use_cyclic_u
    
    return polyline

def make_knots(spline) -> List[float]:

    degree = spline.order_u - 1
    n_control_points = len(spline.points)
    
    # for open curves
    if not spline.use_cyclic_u:
        knot_count = n_control_points + degree + 1
        knots = [0.0] * knot_count
        
        for i in range(1, degree + 1):
            knots[i] = 0.0
            knots[knot_count - i - 1] = 1.0
            
        # internal knots
        internal_count = knot_count - 2 * (degree + 1) + 2
        for i in range(internal_count):
            knots[i + degree + 1] = (i + 1) / (internal_count + 1)
            
        return knots
    
    # for closed curves
    else:
        knot_count = n_control_points + 1
        knots = []
        
        for i in range(knot_count):
            knots.append(i / (knot_count - 1))
            
        return knots


def nurbs_to_speckle(
    matrix: Matrix, 
    spline, 
    name: Optional[str] = None,
    scale_factor: float = 1.0,
    units: str = "m"
) -> Curve:

    degree = spline.order_u - 1
    knots = make_knots(spline)
    
    length = spline.calc_length()
    domain = Interval(start=0, end=length)
    
    weights = [pt.weight for pt in spline.points]
    is_rational = not all(w == weights[0] for w in weights)
    
    points = []
    for pt in spline.points:
        transformed_point = matrix @ pt.co.xyz * scale_factor
        points.append((transformed_point.x, transformed_point.y, transformed_point.z))
    
    flattened_points = []
    for point in points:
        flattened_points.extend(point)
    
    if spline.use_cyclic_u:
        for i in range(0, degree * 3, 3):
            flattened_points.append(flattened_points[i + 0])
            flattened_points.append(flattened_points[i + 1])
            flattened_points.append(flattened_points[i + 2])
        
        for i in range(0, degree):
            weights.append(weights[i])
    
    display_value = nurbs_to_speckle_polyline(matrix, spline, length, scale_factor, units)
    
    curve = Curve(
        degree=degree,
        periodic=not spline.use_endpoint_u,
        rational=is_rational,
        points=flattened_points,
        weights=weights,
        knots=knots,
        closed=spline.use_cyclic_u,
        displayValue=display_value,
        units=units,
        bbox=None,
    )
    
    curve.__dict__["_length"] = length
    curve.__dict__["_area"] = 0.0
    
    curve["domain"] = domain
    
    if name:
        curve["name"] = name
        
    return curve


def nurbs_to_speckle_polyline(
    matrix: Matrix, 
    spline, 
    length: Optional[float] = None,
    scale_factor: float = 1.0,
    units: str = "m"
) -> Polyline:
    points: List[float] = []
    
    n_samples = spline.resolution_u * len(spline.points)
    
    if n_samples < 2:
        n_samples = 16
    
    for i in range(n_samples):
        t = i / (n_samples - 1)
        u = t * (len(spline.points) - 1)
        
        index = int(u)
        fract = u - index
        
        if index >= len(spline.points) - 1:
            point = spline.points[-1].co.xyz
        else:
            point = (1 - fract) * spline.points[index].co.xyz + fract * spline.points[index + 1].co.xyz
        
        transformed_point = matrix @ point * scale_factor
        
        points.append(transformed_point.x)
        points.append(transformed_point.y)
        points.append(transformed_point.z)
    
    length = length or spline.calc_length()
    
    polyline = Polyline(
        value=points,
        units=units
    )
    
    polyline["domain"] = { "start": 0, "end": length }
    polyline["closed"] = spline.use_cyclic_u
    
    return polyline