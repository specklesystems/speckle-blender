import bpy, bmesh, struct

def export_curve(blender_object, scale=1.0):
    return None

def export_ngons_as_polylines(blender_object, scale=1.0):
	if blender_object.type != 'MESH':
		return None

	verts = blender_object.data.vertices
	polylines = []
	for poly in blender_object.data.polygons:
		value = []
		for v in poly.vertices:
			value.extend(verts[v].co * scale)

		speckle_polyline = {
			'type':'Polyline',
			'closed':True,
			'value':value,
			'domain': {
				'type':'Interval',
				'start':0.0,
				'end':1.0
			}
		}
		polylines.append(speckle_polyline)

	return polylines
